"""DB-selected model calls, captured retrieval identity and worker failure fences."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator

import httpx
import pytest
from app.core import knowledge_ai, llm
from app.core.config import get_settings
from app.core.db import bound_scope
from app.core.errors import KGError
from app.domain import ai_model_service, knowledge_service
from app.domain.knowledge_parser import ParsedDocument
from app.models.ai_model import AiModelCapability, AiModelDefault
from app.models.knowledge import KnowledgeChunk, KnowledgeIndex
from app.schemas.ai_model import AiModelConfigUpdate
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

import test_knowledge_retrieval as retrieval_tests
import test_knowledge_service as ingestion_tests
from ai_model_helpers import (
    FAKE_KEY,
    embedding_response,
    mock_transport,
    seed_model,
    select_model,
)

factory = ingestion_tests.factory
setup = retrieval_tests.setup


@pytest.fixture
def inherited_model_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    # Make the old ENV path genuinely usable, so accidental fallback is detected.
    for prefix in ("KG_LLM", "KG_EMBEDDING"):
        monkeypatch.setenv(prefix + "_BASE_URL", "https://env.example.test/v1")
        monkeypatch.setenv(prefix + "_API_KEY", "inherited-env-key")
        monkeypatch.setenv(prefix + "_MODEL", "inherited-model")
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.llm_model == settings.embedding_model == "inherited-model"
    try:
        yield
    finally:
        get_settings.cache_clear()


@pytest.mark.parametrize("unselected_rows", [False, True])
def test_env_and_unselected_models_never_enable_runtime(
    setup: retrieval_tests.RetrievalSetup,
    inherited_model_env: None,
    monkeypatch: pytest.MonkeyPatch,
    unselected_rows: bool,
) -> None:
    client, factory, tokens = setup
    if unselected_rows:
        with bound_scope(factory) as session:
            seed_model(session, select_default=False)
            seed_model(
                session,
                capability=AiModelCapability.CHAT,
                name="Chat",
                select_default=False,
            )
    calls: list[httpx.Request] = []

    def forbidden(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        raise AssertionError("Unselected models must never call any endpoint")

    mock_transport(monkeypatch, forbidden)
    kb = retrieval_tests.create(client, tokens)
    document = retrieval_tests.upload(
        client, factory, tokens, kb, "设备维护周期三个月。"
    )
    capabilities = client.get(
        "/api/v1/knowledge-bases/capabilities", headers=tokens["VIEWER"]
    ).json()
    assert {
        name: capabilities[name]
        for name in (
            "chat_configured",
            "embedding_configured",
            "embedding_model",
            "embedding_version",
        )
    } == {
        "chat_configured": False,
        "embedding_configured": False,
        "embedding_model": None,
        "embedding_version": None,
    }
    semantic = retrieval_tests.search(client, tokens, kb, "检修", "SEMANTIC")
    assert semantic.json()["code"] == "KG.LLM_NOT_CONFIGURED"
    answer = client.post(
        f"/api/v1/knowledge-bases/{kb['id']}/answer",
        headers=tokens["VIEWER"],
        json={"q": "维护", "mode": "KEYWORD"},
    )
    assert answer.json()["code"] == "KG.LLM_NOT_CONFIGURED"
    detail = client.get(
        f"/api/v1/knowledge-bases/{kb['id']}/documents/{document['id']}",
        headers=tokens["VIEWER"],
    ).json()
    assert detail["semantic_status"] == "NOT_CONFIGURED"
    assert detail["latest_task"]["status"] == "SUCCESS"
    assert detail["searchable"]
    assert not knowledge_ai.embedding_configured()
    with pytest.raises(KGError, match=r"KG\.LLM_NOT_CONFIGURED"):
        asyncio.run(knowledge_ai.embedding_client().embed(["query"]))
    with pytest.raises(KGError, match=r"KG\.LLM_NOT_CONFIGURED"):
        llm.chat_json("system", "user")
    assert calls == []


def test_database_defaults_drive_embedding_and_chat_transport(
    setup: retrieval_tests.RetrievalSetup,
    inherited_model_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, factory, tokens = setup
    with bound_scope(factory) as session:
        seed_model(
            session, model="database-embedding", base_url="https://db.example.test/e"
        )
        seed_model(
            session,
            capability=AiModelCapability.CHAT,
            name="Chat",
            model="database-chat",
            base_url="https://db.example.test/c",
            key="db-chat-key",
        )
        selected = ai_model_service.resolve_default(session, "EMBEDDING")
        assert selected is not None
        fingerprint = knowledge_ai.embedding_version(selected.endpoint)
    calls: list[tuple[str, str]] = []

    def respond(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert request.url.host == "db.example.test"
        calls.append((request.url.path, payload["model"]))
        if payload["model"] == "database-embedding":
            assert request.headers["Authorization"] == "Bearer " + FAKE_KEY
            return embedding_response([[1.0, 0.0] for _ in payload["input"]])
        assert request.headers["Authorization"] == "Bearer db-chat-key"
        evidence = json.loads(payload["messages"][1]["content"])["evidence"][0]
        content = json.dumps(
            {
                "status": "ANSWERED",
                "citations": [
                    {"chunk_id": evidence["chunk_id"], "quote": evidence["text"]}
                ],
            }
        )
        return httpx.Response(
            200, json={"choices": [{"message": {"content": content}}]}
        )

    mock_transport(monkeypatch, respond)
    kb = retrieval_tests.create(client, tokens)
    document = retrieval_tests.upload(
        client, factory, tokens, kb, "设备维护周期三个月。"
    )
    answer = client.post(
        f"/api/v1/knowledge-bases/{kb['id']}/answer",
        headers=tokens["VIEWER"],
        json={"q": "维护", "mode": "SEMANTIC"},
    )
    assert answer.status_code == 200, answer.text
    assert answer.json()["status"] == "ANSWERED"
    assert answer.json()["retrieval"]["embedding_version"] == fingerprint
    assert calls == [
        ("/e/embeddings", "database-embedding"),
        ("/e/embeddings", "database-embedding"),
        ("/c/chat/completions", "database-chat"),
    ]
    with factory() as session:
        state = knowledge_service.document_out(
            session, knowledge_service.get_document(session, kb["id"], document["id"])
        )
        assert state.active_index is not None
        assert state.active_index.embedding_version == fingerprint
        assert state.active_index.embedding_model == "database-embedding"


@pytest.mark.parametrize("same_model", [False, True])
def test_query_await_switch_uses_captured_fingerprint_for_candidates_and_response(
    setup: retrieval_tests.RetrievalSetup,
    monkeypatch: pytest.MonkeyPatch,
    same_model: bool,
) -> None:
    client, factory, tokens = setup
    with bound_scope(factory) as session:
        old = seed_model(session, model="old-embedding")
        new = seed_model(
            session,
            name="New",
            model="old-embedding" if same_model else "new-embedding",
            version="test-v2",
            select_default=False,
        )
        captured = ai_model_service.resolve_default(session, "EMBEDDING")
        assert captured is not None
        fingerprint = knowledge_ai.embedding_version(captured.endpoint)
    calls: list[str] = []

    def initial(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        calls.append(payload["model"])
        return embedding_response([[1.0, 0.0] for _ in payload["input"]])

    mock_transport(monkeypatch, initial)
    kb = retrieval_tests.create(client, tokens)
    old_document = retrieval_tests.upload(
        client, factory, tokens, kb, "旧版本维护资料。"
    )
    with bound_scope(factory) as session:
        select_model(session, new)
    new_document = retrieval_tests.upload(
        client, factory, tokens, kb, "新版本维护资料。"
    )
    with bound_scope(factory) as session:
        select_model(session, old)
    calls.clear()
    switched: list[bool] = []

    async def switch_during_await(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        calls.append(payload["model"])
        assert payload["model"] == "old-embedding"
        await asyncio.sleep(0)
        # A separate committed transaction while query inference is awaited.
        with bound_scope(factory) as session:
            select_model(session, new)
        switched.append(True)
        return embedding_response([[1.0, 0.0]])

    mock_transport(monkeypatch, switch_during_await)
    result = retrieval_tests.search(client, tokens, kb, "维护", "SEMANTIC")
    assert result.status_code == 200, result.text
    response = result.json()
    assert switched == [True] and calls == ["old-embedding"]
    assert response["embedding_version"] == fingerprint
    assert response["coverage"]["semantic_documents"] == 1
    assert [hit["document_id"] for hit in response["items"]] == [old_document["id"]]
    assert new_document["id"] != old_document["id"]
    assert all(hit["similarity"] == 1 for hit in response["items"])
    with factory() as session:
        current = ai_model_service.resolve_default(session, "EMBEDDING")
        assert current is not None and current.config_id == new.id
        assert knowledge_ai.embedding_version(current.endpoint) != fingerprint


@pytest.mark.parametrize("paragraphs", [1, 40])
@pytest.mark.parametrize(
    "transition", ["selection", "version", "disabled", "credential"]
)
def test_worker_switch_fails_before_next_batch_or_publish_and_keeps_old_index(
    factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
    paragraphs: int,
    transition: str,
) -> None:
    document = ingestion_tests.upload(
        factory, "\n\n".join(f"Paragraph {i}" for i in range(paragraphs)).encode()
    )
    ingestion_tests.process(factory)  # A real successful keyword generation.
    before = ingestion_tests.output(factory, document.id)
    assert before.searchable and before.active_index is not None
    with bound_scope(factory) as session:
        old = seed_model(session, model="old-embedding")
        new = seed_model(
            session, name="New", model="new-embedding", select_default=False
        )
        knowledge_service.queue_document(session, 1, document.id, before.revision)
    calls: list[tuple[str, int]] = []

    async def changed(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        calls.append((payload["model"], len(payload["input"])))
        assert payload["model"] == "old-embedding"
        await asyncio.sleep(0)
        with bound_scope(factory) as session:
            if transition == "selection":
                select_model(session, new)
            else:
                changes = {
                    "version": {"model_version": "next-version"},
                    "disabled": {"enabled": False},
                    "credential": {"api_key": "rotated-runtime-key"},
                }
                ai_model_service.update_config(
                    session,
                    old.id,
                    AiModelConfigUpdate.model_validate(changes[transition]),
                    1,
                )
        return embedding_response([[1.0, 0.0] for _ in payload["input"]])

    mock_transport(monkeypatch, changed)
    ingestion_tests.process(factory)
    after = ingestion_tests.output(factory, document.id)
    assert calls == [("old-embedding", min(32, paragraphs))]
    assert after.searchable and after.active_generation == before.active_generation
    assert after.active_index == before.active_index
    assert after.latest_task is not None and after.latest_task.status == "FAILED"
    assert after.latest_task.error_code == "KG.REVISION_CONFLICT"
    assert after.latest_task.error_reason == "model_configuration_changed"
    with factory() as session:
        staged = session.scalar(
            select(KnowledgeIndex).where(
                KnowledgeIndex.document_id == document.id,
                KnowledgeIndex.generation == after.generation,
            )
        )
        assert staged is not None and staged.id != before.active_index.id
        assert staged.embedding_model == "old-embedding"
        assert staged.semantic_status != "READY"
        chunks = session.scalars(
            select(KnowledgeChunk).where(KnowledgeChunk.index_id == staged.id)
        ).all()
        assert all(chunk.vector is None for chunk in chunks)


@pytest.mark.parametrize("configured", [False, True])
def test_default_changes_after_staging_fence_first_batch_and_publication(
    factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch, configured: bool
) -> None:
    document = ingestion_tests.upload(factory)
    ingestion_tests.process(factory)
    before = ingestion_tests.output(factory, document.id)
    with bound_scope(factory) as session:
        if configured:
            seed_model(session, name="Old")
        new = seed_model(session, select_default=False)
        knowledge_service.queue_document(session, 1, document.id, before.revision)
    original = knowledge_service.stage_index

    def stage_then_select(
        session: Session,
        claim: knowledge_service.ClaimedTask,
        parsed: ParsedDocument,
        *,
        embedding_version: str | None,
        embedding_model: str | None,
    ) -> str | None:
        result = original(
            session,
            claim,
            parsed,
            embedding_version=embedding_version,
            embedding_model=embedding_model,
        )
        # Use this transaction: stage writes already own SQLite's write lock.
        select_model(session, new)
        return result

    calls: list[httpx.Request] = []

    def unexpected(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(500)

    mock_transport(monkeypatch, unexpected)
    monkeypatch.setattr(knowledge_service, "stage_index", stage_then_select)
    ingestion_tests.process(factory)
    after = ingestion_tests.output(factory, document.id)
    assert after.active_generation == before.active_generation
    assert after.active_index == before.active_index
    assert after.latest_task is not None and after.latest_task.status == "FAILED"
    assert after.latest_task.error_reason == "model_configuration_changed"
    assert calls == []


def test_json_suggestions_use_explicit_resolved_database_chat_endpoint(
    factory: sessionmaker[Session],
    inherited_model_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with bound_scope(factory) as session:
        seed_model(
            session,
            capability=AiModelCapability.CHAT,
            name="Chat",
            model="db-suggestion-chat",
            base_url="https://chat.example.test/v1",
        )
        selected = ai_model_service.resolve_default(session, "CHAT")
        assert selected is not None
    calls: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        payload = json.loads(request.content)
        assert payload["model"] == "db-suggestion-chat"
        assert request.headers["Authorization"] == "Bearer " + FAKE_KEY
        assert payload["temperature"] == 0.2 and "max_tokens" not in payload
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": '[{"name":"Explicit database model"}]'}}
                ]
            },
        )

    mock_transport(monkeypatch, respond)
    assert llm.chat_json("system", "user", endpoint=selected.endpoint) == [
        {"name": "Explicit database model"}
    ]
    assert calls == ["https://chat.example.test/v1/chat/completions"]


@pytest.mark.parametrize("transition", ["selection", "version", "disabled", "cleared"])
def test_document_base_and_capabilities_follow_current_default_without_secrets(
    setup: retrieval_tests.RetrievalSetup,
    monkeypatch: pytest.MonkeyPatch,
    transition: str,
) -> None:
    client, factory, tokens = setup
    with bound_scope(factory) as session:
        old = seed_model(session, model="old-embedding")
        new = seed_model(
            session, name="New", model="new-embedding", select_default=False
        )
    mock_transport(
        monkeypatch,
        lambda request: embedding_response(
            [[1.0, 0.0] for _ in json.loads(request.content)["input"]]
        ),
    )
    kb = retrieval_tests.create(client, tokens)
    document = retrieval_tests.upload(
        client, factory, tokens, kb, "设备维护周期三个月。"
    )
    base_path = f"/api/v1/knowledge-bases/{kb['id']}"
    doc_path = base_path + f"/documents/{document['id']}"
    assert (
        client.get(doc_path, headers=tokens["VIEWER"]).json()["semantic_status"]
        == "READY"
    )
    assert client.get(base_path, headers=tokens["VIEWER"]).json()["semantic_count"] == 1
    with bound_scope(factory) as session:
        if transition == "selection":
            select_model(session, new)
        elif transition == "cleared":
            default = session.get(AiModelDefault, AiModelCapability.EMBEDDING)
            assert default is not None
            ai_model_service.set_default(session, "EMBEDDING", None, default.revision)
        else:
            payload = (
                AiModelConfigUpdate(model_version="next-version")
                if transition == "version"
                else AiModelConfigUpdate(enabled=False)
            )
            ai_model_service.update_config(session, old.id, payload, 1)
    responses = [
        client.get(path, headers=tokens["VIEWER"])
        for path in (doc_path, base_path, "/api/v1/knowledge-bases/capabilities")
    ]
    for response in responses:
        assert response.status_code == 200, response.text
        assert FAKE_KEY not in response.text
        assert (
            "credential_cipher" not in response.text and "api_key" not in response.text
        )
        assert "aesgcm:v1:" not in response.text
    detail, summary, capabilities = [response.json() for response in responses]
    assert (
        detail["semantic_status"]
        == detail["active_index"]["semantic_status"]
        == "STALE"
    )
    assert detail["active_generation"] == 1 and detail["searchable"]
    assert summary["semantic_count"] == 0 and summary["searchable_count"] == 1
    assert capabilities["embedding_configured"] == (
        transition in {"selection", "version"}
    )
    assert capabilities["embedding_model"] == (
        "new-embedding"
        if transition == "selection"
        else "old-embedding"
        if transition == "version"
        else None
    )
