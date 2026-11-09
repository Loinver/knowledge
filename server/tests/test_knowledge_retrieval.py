"""Real temporary SQL/API pipeline; model outputs are explicit isolated test doubles."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Any

import pytest
from app.api.knowledge_runtime import KnowledgeRuntime
from app.api.v1 import knowledge_retrieval as api
from app.core import knowledge_ai
from app.core.db import Base, bound_scope, get_session
from app.domain import knowledge_retrieval as retrieval
from app.domain import knowledge_service as service
from app.domain.account_service import issue_session
from app.main import app
from app.models.account import User
from app.models.enums import UserRole
from app.models.knowledge import KnowledgeBase, KnowledgeChunk, KnowledgeDocument
from app.schemas.knowledge import KnowledgeEvidenceOut
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker

RetrievalSetup = tuple[TestClient, sessionmaker[Session], dict[str, dict[str, str]]]


@pytest.fixture()
def setup(tmp_path, monkeypatch):
    engine = create_engine(
        f"sqlite:///{tmp_path}/retrieval.sqlite",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def fk(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    tokens = {}
    with bound_scope(factory) as session:
        for role in (UserRole.ADMIN, UserRole.EDITOR, UserRole.VIEWER):
            user = User(
                username=role.value,
                email=role.value + "@example.org",
                role=role,
                password_hash="unused",
            )
            session.add(user)
            session.flush()
            tokens[role.value] = {
                "Authorization": "Bearer " + issue_session(session, user).access_token
            }

    def isolated():
        with factory() as session:
            yield session

    app.dependency_overrides[get_session] = isolated
    monkeypatch.setattr(knowledge_ai, "embedding_configured", lambda: False)
    monkeypatch.setattr(api, "embedding_configured", lambda: False)
    client = TestClient(app)
    try:
        yield client, factory, tokens
    finally:
        client.close()
        app.dependency_overrides.pop(get_session, None)
        engine.dispose()


def create(client, tokens, name="Operations"):
    response = client.post(
        "/api/v1/knowledge-bases", headers=tokens["EDITOR"], json={"name": name}
    )
    assert response.status_code == 201, response.text
    return response.json()


def upload(client, factory, tokens, kb, content, filename="operations.txt"):
    response = client.post(
        f"/api/v1/knowledge-bases/{kb['id']}/documents",
        headers={**tokens["EDITOR"], "Content-Type": "application/octet-stream"},
        params={"filename": filename, "content_type": "text/plain"},
        content=content.encode(),
    )
    assert response.status_code == 201, response.text
    with bound_scope(factory) as session:
        claim = service.claim_task(session, "test-worker")
    assert claim is not None
    asyncio.run(KnowledgeRuntime(factory).process_claim(claim))
    return response.json()


def search(client, tokens, kb, query="设备维护", mode="KEYWORD"):
    return client.post(
        f"/api/v1/knowledge-bases/{kb['id']}/search",
        headers=tokens["VIEWER"],
        json={"q": query, "mode": mode},
    )


def test_roles_and_exact_readonly_post_allowlist(setup):
    client, _factory, tokens = setup
    assert client.get("/api/v1/knowledge-bases").status_code == 401
    assert (
        client.post(
            "/api/v1/knowledge-bases", headers=tokens["VIEWER"], json={"name": "denied"}
        ).status_code
        == 403
    )
    kb = create(client, tokens)
    assert search(client, tokens, kb).status_code == 200
    result = client.post(
        f"/api/v1/knowledge-bases/{kb['id']}/answer",
        headers=tokens["VIEWER"],
        json={"q": "问题"},
    )
    assert result.json()["status"] == "INSUFFICIENT_EVIDENCE"
    for suffix in (
        "archive",
        "restore",
        "documents",
        "search/extra",
        "evidence/a/links",
    ):
        assert client.post(
            f"/api/v1/knowledge-bases/{kb['id']}/{suffix}",
            headers=tokens["VIEWER"],
            json={},
        ).status_code in (403, 404, 405)
    assert (
        client.post(
            f"/api/v1/knowledge-bases/{kb['id']}/archive",
            headers={**tokens["EDITOR"], "If-Match": "999"},
        ).status_code
        == 409
    )


def test_keyword_evidence_exact_location_archive_and_wrong_base(setup):
    client, factory, tokens = setup
    kb = create(client, tokens)
    other = create(client, tokens, "Other")
    document = upload(
        client, factory, tokens, kb, "设备维护周期三个月。\n\n会议每周一召开。"
    )
    result = search(client, tokens, kb)
    assert result.status_code == 200, result.text
    data = result.json()
    assert data["coverage"]["searchable_documents"] == 1
    assert data["coverage"]["semantic_documents"] == 0
    hit = data["items"][0]
    detail = client.get(
        f"/api/v1/knowledge-bases/{kb['id']}/evidence/{hit['chunk_id']}",
        headers=tokens["VIEWER"],
    ).json()
    location = hit["location"]
    assert (
        detail["normalized_text"][location["start_offset"] : location["end_offset"]]
        == hit["text"]
    )
    assert (
        client.get(
            f"/api/v1/knowledge-bases/{other['id']}/evidence/{hit['chunk_id']}",
            headers=tokens["VIEWER"],
        ).status_code
        == 404
    )
    archived = client.post(
        f"/api/v1/knowledge-bases/{kb['id']}/documents/{document['id']}/archive",
        headers={**tokens["EDITOR"], "If-Match": str(document["revision"])},
    )
    assert archived.status_code == 200
    assert search(client, tokens, kb).json()["items"] == []
    assert client.get(
        f"/api/v1/knowledge-bases/{kb['id']}/evidence/{hit['chunk_id']}",
        headers=tokens["VIEWER"],
    ).json()["archived"]


def configure_models(monkeypatch):
    class Model:
        endpoint = SimpleNamespace(model="isolated-test-model", configured=True)

        async def embed(self, texts):
            return [
                [1.0, 0.0] if ("维护" in text or "检修" in text) else [0.0, 1.0]
                for text in texts
            ]

        async def chat(self, system, user):
            evidence = json.loads(user)["evidence"]
            return json.dumps(
                {
                    "status": "ANSWERED",
                    "citations": [
                        {
                            "chunk_id": evidence[0]["chunk_id"],
                            "quote": evidence[0]["text"],
                        }
                    ],
                }
            )

    monkeypatch.setattr(knowledge_ai, "embedding_configured", lambda: True)
    monkeypatch.setattr(knowledge_ai, "embedding_client", Model)
    monkeypatch.setattr(knowledge_ai, "embedding_version", lambda: "test-v1")
    monkeypatch.setattr(api, "embedding_configured", lambda: True)
    monkeypatch.setattr(api, "embedding_client", Model)
    monkeypatch.setattr(api, "chat_client", Model)
    monkeypatch.setattr(retrieval, "embedding_version", lambda: "test-v1")


def test_semantic_hybrid_and_answer_citations_with_test_model(setup, monkeypatch):
    client, factory, tokens = setup
    configure_models(monkeypatch)
    kb = create(client, tokens)
    upload(client, factory, tokens, kb, "设备维护周期三个月。\n\n会议每周一召开。")
    assert search(client, tokens, kb, "检修", "KEYWORD").json()["items"] == []
    semantic = search(client, tokens, kb, "检修", "SEMANTIC").json()
    assert len(semantic["items"]) == 1 and semantic["items"][0]["similarity"] == 1
    hybrid = search(client, tokens, kb, "维护", "HYBRID").json()
    assert hybrid["items"][0]["keyword_score"] > 0
    assert hybrid["items"][0]["similarity"] == 1
    answer = client.post(
        f"/api/v1/knowledge-bases/{kb['id']}/answer",
        headers=tokens["VIEWER"],
        json={"q": "检修", "mode": "SEMANTIC"},
    )
    assert answer.status_code == 200, answer.text
    citation = answer.json()["citations"][0]
    assert citation["quote"] in citation["source"]["text"]
    assert citation["source"]["chunk_id"] == semantic["items"][0]["chunk_id"]


def test_semantic_missing_stale_and_corrupt_are_errors(setup, monkeypatch):
    client, factory, tokens = setup
    kb = create(client, tokens)
    upload(client, factory, tokens, kb, "设备维护周期三个月。")
    assert (
        search(client, tokens, kb, "检修", "SEMANTIC").json()["code"]
        == "KG.LLM_NOT_CONFIGURED"
    )
    configure_models(monkeypatch)
    failed = search(client, tokens, kb, "检修", "SEMANTIC")
    assert (
        failed.status_code == 400
        and failed.json()["params"]["reason"] == "knowledge_semantic_index_not_ready"
    )
    other = create(client, tokens, "Indexed")
    upload(client, factory, tokens, other, "设备维护周期六个月。")
    with bound_scope(factory) as session:
        chunk = session.scalar(
            select(KnowledgeChunk)
            .join(
                service.KnowledgeIndex,
                service.KnowledgeIndex.id == KnowledgeChunk.index_id,
            )
            .join(service.KnowledgeDocument)
            .where(service.KnowledgeDocument.kb_id == other["id"])
        )
        chunk.vector = [0.0, 0.0]
    failed = search(client, tokens, other, "检修", "SEMANTIC")
    assert (
        failed.status_code == 400
        and failed.json()["params"]["reason"] == "knowledge_index_corrupt"
    )


def test_archive_during_answer_rejects_stale_evidence(setup, monkeypatch):
    client, factory, tokens = setup
    configure_models(monkeypatch)
    kb = create(client, tokens)
    upload(client, factory, tokens, kb, "设备维护周期三个月。")

    class ArchiveModel:
        async def chat(self, system, user):
            evidence = json.loads(user)["evidence"][0]
            with bound_scope(factory) as session:
                base = session.get(KnowledgeBase, kb["id"])
                service.set_base_archived(session, base.id, True, base.revision)
            return json.dumps(
                {
                    "status": "ANSWERED",
                    "citations": [
                        {"chunk_id": evidence["chunk_id"], "quote": evidence["text"]}
                    ],
                }
            )

    monkeypatch.setattr(api, "chat_client", ArchiveModel)
    result = client.post(
        f"/api/v1/knowledge-bases/{kb['id']}/answer",
        headers=tokens["VIEWER"],
        json={"q": "维护"},
    )
    assert result.status_code == 400
    assert result.json()["params"]["reason"] == "knowledge_archived"


def test_manual_graph_reference_is_version_pinned_and_not_a_new_fact(setup):
    from app.models.data_access import Mapping, MappingRevision
    from app.models.domain import Ontology
    from app.models.extraction import (
        EntityIdentity,
        ExtractionRun,
        GraphRevision,
        GraphTriple,
    )

    client, factory, tokens = setup
    kb = create(client, tokens)
    document = upload(client, factory, tokens, kb, "设备维护由运营部门负责。")
    hit = search(client, tokens, kb).json()["items"][0]
    with bound_scope(factory) as session:
        ontology = Ontology(name="LinkOntology", iri="https://example.org/onto/")
        session.add(ontology)
        session.flush()
        mapping = Mapping(name="LinkMapping", ontology_id=ontology.id)
        session.add(mapping)
        session.flush()
        revision = MappingRevision(mapping_id=mapping.id, revision=1, onto_version=1)
        session.add(revision)
        session.flush()
        run = ExtractionRun(mapping_revision_id=revision.id, cfg_snapshot={})
        session.add(run)
        session.flush()
        graph = GraphRevision(run_id=run.id, publishable=True)
        session.add(graph)
        session.flush()
        iri = "https://example.org/entity/maintenance"
        session.add(
            EntityIdentity(
                graph_revision_id=graph.id,
                iri=iri,
                type_iri="https://example.org/Type",
                row_key="1",
                attrs={},
            )
        )
        session.add(
            EntityIdentity(
                graph_revision_id=graph.id,
                iri="https://example.org/operations",
                type_iri="https://example.org/Type",
                row_key="2",
                attrs={},
            )
        )
        fact = GraphTriple(
            graph_revision_id=graph.id,
            subject=iri,
            predicate="https://example.org/OwnedBy",
            object_="https://example.org/operations",
        )
        session.add(fact)
        session.flush()
        graph_id, fact_id = graph.id, fact.id
    path = f"/api/v1/knowledge-bases/{kb['id']}/evidence/{hit['chunk_id']}/links"
    payload = {"graph_revision_id": graph_id, "entity_iri": iri, "fact_id": fact_id}
    headers = {**tokens["EDITOR"], "If-Match": str(document["revision"])}
    assert client.post(path, headers=tokens["VIEWER"], json=payload).status_code == 403
    linked = client.post(path, headers=headers, json=payload)
    assert linked.status_code == 201, linked.text
    assert linked.json()["source"] == "MANUAL"
    assert linked.json()["predicate"] == "https://example.org/OwnedBy"
    incoming = client.post(
        path,
        headers={**tokens["EDITOR"], "If-Match": str(document["revision"] + 1)},
        json={**payload, "entity_iri": "https://example.org/operations"},
    )
    assert incoming.status_code == 400
    assert incoming.json()["params"]["reason"] == "graph_fact_mismatch"
    assert (
        client.post(path, headers=headers, json=payload).json()["id"]
        == linked.json()["id"]
    )
    references = client.get(
        "/api/v1/knowledge-bases/graph-evidence",
        headers=tokens["VIEWER"],
        params=payload,
    ).json()
    assert references[0]["chunk_id"] == hit["chunk_id"]
    assert (
        client.get(
            "/api/v1/knowledge-bases/graph-evidence",
            headers=tokens["VIEWER"],
            params={**payload, "graph_revision_id": graph_id + 1},
        ).json()
        == []
    )
    with factory() as session:
        assert len(list(session.scalars(select(GraphTriple)))) == 1


def test_ranking_does_not_block_event_loop_and_cancellation_joins_worker(
    monkeypatch,
):
    import threading

    started, finished, release = threading.Event(), threading.Event(), threading.Event()
    sentinel = object()

    def blocking_search(*args):
        started.set()
        release.wait(2)
        finished.set()
        return sentinel

    monkeypatch.setattr(api, "search_knowledge", blocking_search)

    async def exercise():
        task = asyncio.create_task(api._rank_in_worker(None, 1, None, None))
        assert await asyncio.to_thread(started.wait, 1)
        # The coroutine resumed while work still ran in another thread.
        assert not finished.is_set()
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert finished.is_set()

    asyncio.run(exercise())


@pytest.fixture()
def linked_reference(
    setup: RetrievalSetup,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, int | str]]:
    from app.models.data_access import Mapping, MappingRevision
    from app.models.domain import Ontology
    from app.models.extraction import EntityIdentity, ExtractionRun, GraphRevision

    client, factory, tokens = setup
    kb = create(client, tokens)
    document = upload(client, factory, tokens, kb, "设备维护由运营部门负责。")
    hit = search(client, tokens, kb).json()["items"][0]
    iri = "https://example.org/entity/maintenance"
    with bound_scope(factory) as session:
        ontology = Ontology(name="HistoricalLink", iri="https://example.org/history/")
        session.add(ontology)
        session.flush()
        mapping = Mapping(name="HistoricalLink", ontology_id=ontology.id)
        session.add(mapping)
        session.flush()
        revision = MappingRevision(mapping_id=mapping.id, revision=1, onto_version=1)
        session.add(revision)
        session.flush()
        run = ExtractionRun(mapping_revision_id=revision.id, cfg_snapshot={})
        session.add(run)
        session.flush()
        graph = GraphRevision(run_id=run.id, publishable=True)
        session.add(graph)
        session.flush()
        session.add(
            EntityIdentity(
                graph_revision_id=graph.id,
                iri=iri,
                type_iri="https://example.org/Type",
                row_key="1",
                attrs={},
            )
        )
        payload: dict[str, int | str] = {
            "graph_revision_id": graph.id,
            "entity_iri": iri,
        }
    response = client.post(
        f"/api/v1/knowledge-bases/{kb['id']}/evidence/{hit['chunk_id']}/links",
        headers={**tokens["EDITOR"], "If-Match": str(document["revision"])},
        json=payload,
    )
    assert response.status_code == 201, response.text
    return kb, hit, payload


@pytest.mark.parametrize(
    "transition", ["reprocess", "document_archive", "base_archive"]
)
@pytest.mark.parametrize("after_snapshot", [False, True])
def test_graph_references_recheck_historical_and_archived_state(
    setup: RetrievalSetup,
    linked_reference: tuple[dict[str, Any], dict[str, Any], dict[str, int | str]],
    monkeypatch: pytest.MonkeyPatch,
    transition: str,
    after_snapshot: bool,
) -> None:
    client, factory, tokens = setup
    kb, hit, payload = linked_reference
    path = "/api/v1/knowledge-bases/graph-evidence"
    initial = client.get(path, headers=tokens["VIEWER"], params=payload).json()
    assert len(initial) == 1
    assert initial[0]["historical"] is False
    original_detail = retrieval.evidence_detail

    def change_state() -> None:
        with bound_scope(factory) as session:
            base = session.get(KnowledgeBase, kb["id"])
            document = session.get(KnowledgeDocument, hit["document_id"])
            assert base is not None and document is not None
            if transition == "base_archive":
                service.set_base_archived(session, base.id, True, base.revision)
            elif transition == "document_archive":
                service.set_document_archived(
                    session, base.id, document.id, True, document.revision
                )
            else:
                service.queue_document(session, base.id, document.id, document.revision)
        if transition == "reprocess":
            with bound_scope(factory) as session:
                claim = service.claim_task(session, "historical-test-worker")
            assert claim is not None
            asyncio.run(KnowledgeRuntime(factory).process_claim(claim))

    rechecks: list[str] = []

    def changed_detail(
        session: Session, kb_id: int, chunk_id: str
    ) -> KnowledgeEvidenceOut:
        # Keep cached objects alive to catch stale identity-map reads, too.
        base = session.get(KnowledgeBase, kb_id)
        document = session.get(KnowledgeDocument, hit["document_id"])
        assert base is not None and not base.archived
        assert document is not None and not document.archived
        assert document.active_generation == hit["generation"]
        change_state()  # Separate transaction after the initial reference query.
        rechecks.append(chunk_id)
        return original_detail(session, kb_id, chunk_id)

    if after_snapshot:
        monkeypatch.setattr(retrieval, "evidence_detail", changed_detail)
    else:
        change_state()
    response = client.get(path, headers=tokens["VIEWER"], params=payload)
    assert response.status_code == 200, response.text
    references = response.json()
    assert rechecks == ([hit["chunk_id"]] if after_snapshot else [])
    if transition == "reprocess":
        assert len(references) == 1
        reference = references[0]
        assert reference["historical"] is True
        for field in ("chunk_id", "index_id", "generation", "text", "location"):
            assert reference[field] == hit[field]
        current = search(client, tokens, kb).json()["items"][0]
        assert current["generation"] > reference["generation"]
        assert current["chunk_id"] != reference["chunk_id"]
    else:
        assert references == []
    # Historical and archived evidence still has a direct, pinned detail endpoint.
    detail = client.get(
        f"/api/v1/knowledge-bases/{kb['id']}/evidence/{hit['chunk_id']}",
        headers=tokens["VIEWER"],
    ).json()
    assert detail["historical"] is (transition == "reprocess")
    assert detail["archived"] is (transition != "reprocess")
    assert detail["hit"]["text"] == hit["text"]
