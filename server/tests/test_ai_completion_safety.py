"""G07: isolated tests for completion baselines, CAS and HTTP audit atomicity."""

from __future__ import annotations

import json
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from threading import Barrier
from typing import Any

import pytest
from app.api.errors import install_error_handler
from app.api.v1 import ai
from app.api.v1.deps import authorize_business_request
from app.core import llm
from app.core.db import Base, get_session
from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.domain import ai_suggestion_service as service
from app.domain.account_service import issue_session
from app.domain.status_service import lock_resource_edit, publish_resource
from app.models.account import User
from app.models.ai_model import AiModelCapability
from app.models.asset_audit import AssetAuditLog
from app.models.domain import Ontology, OntologyResourceRef
from app.models.enums import ResourceKind, UserRole
from app.models.governance import AiSuggestion
from app.models.resource import ModelResource, Namespace
from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, delete, event, select, update
from sqlalchemy.orm import Session, sessionmaker

from ai_model_helpers import seed_model

API = "/api/v1/ai"


@dataclass
class Harness:
    engine: Engine
    sessions: sessionmaker[Session]
    client: TestClient
    ontology_id: int
    resource_ids: list[int]
    foreign_id: int
    published_id: int
    tokens: dict[str, str]
    editor_id: str

    def headers(self, role: str = "EDITOR") -> dict[str, str]:
        return {"Authorization": f"Bearer {self.tokens[role]}"}


@pytest.fixture()
def h(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Harness]:
    engine = create_engine(
        f"sqlite:///{tmp_path}/completion.db",
        connect_args={"check_same_thread": False, "timeout": 10},
    )

    @event.listens_for(engine, "connect")
    def foreign_keys(connection: Any, _: Any) -> None:
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)
    tokens: dict[str, str] = {}
    with sessions.begin() as session:
        for role in (UserRole.EDITOR, UserRole.VIEWER):
            user = User(
                username=role.value.lower(),
                email=f"{role.value.lower()}@example.org",
                password_hash="unused-test-hash",
                role=role,
            )
            session.add(user)
            session.flush()
            tokens[role.value] = issue_session(session, user).access_token
            if role == UserRole.EDITOR:
                editor_id = user.id
        namespace = Namespace(prefix="safe", iri="https://example.org/safe#")
        ontology = Ontology(name="CompletionSafety", iri="https://example.org/onto")
        session.add_all([namespace, ontology])
        session.flush()
        resources = [
            ModelResource(
                kind=ResourceKind.ENTITY,
                name=name,
                iri=f"https://example.org/safe#{name}",
                namespace_id=namespace.id,
                label_i18n={"en-US": "Existing English", "fr": "Existing French"},
                definition_i18n={"fr": "Existing definition"},
            )
            for name in ("First", "Second", "Foreign", "Published")
        ]
        session.add_all(resources)
        session.flush()
        publish_resource(session, resources[3])
        session.add_all(
            OntologyResourceRef(ontology_id=ontology.id, resource_id=res.id)
            for res in (resources[0], resources[1], resources[3])
        )
        seed_model(session, capability=AiModelCapability.CHAT, name="OfflineChat")
        ontology_id = ontology.id
        resource_ids = [res.id for res in resources[:2]]
        foreign_id, published_id = resources[2].id, resources[3].id

    def request_session() -> Iterator[Session]:
        with sessions() as session:
            yield session

    def no_llm(*args: Any, **kwargs: Any) -> list[dict]:
        raise AssertionError("Real model/network calls are forbidden in G07 tests")

    monkeypatch.setattr(llm, "chat_json", no_llm)
    app = FastAPI()
    install_error_handler(app)
    business = APIRouter(
        prefix="/api/v1", dependencies=[Depends(authorize_business_request)]
    )
    business.include_router(ai.router)
    app.include_router(business)
    app.dependency_overrides[get_session] = request_session
    with TestClient(app, raise_server_exceptions=False) as client:
        yield Harness(
            engine,
            sessions,
            client,
            ontology_id,
            resource_ids,
            foreign_id,
            published_id,
            tokens,
            editor_id,
        )
    engine.dispose()


def _candidate(resource_id: object) -> dict:
    return {
        "resource_id": resource_id,
        "label_zh": "建议名称",
        "label_en": "Model must not overwrite English",
        "definition_zh": "建议定义",
        "definition_en": "Suggested definition",
        "explanation": "Offline fixture",
    }


def _generate(
    h: Harness, monkeypatch: pytest.MonkeyPatch, *, both: bool = False
) -> list[int]:
    ids = h.resource_ids if both else h.resource_ids[:1]
    monkeypatch.setattr(llm, "chat_json", lambda *a, **kw: [_candidate(i) for i in ids])
    with h.sessions.begin() as session:
        return [
            item.id
            for item in service.suggest_ontology_completion(session, h.ontology_id)
        ]


def _assert_pending(h: Harness, suggestion_id: int) -> None:
    with h.sessions() as session:
        item = session.get(AiSuggestion, suggestion_id)
        resource = session.get(ModelResource, h.resource_ids[0])
        assert (
            item is not None and item.status == "PENDING" and item.resolved_at is None
        )
        assert resource is not None and not resource.label_i18n.get("zh-CN")
        assert list(session.scalars(select(AssetAuditLog))) == []


def test_server_baselines_ignore_model_metadata_and_unscoped_ids(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    def reply(system: str, user: str, **kwargs: Any) -> list[dict]:
        sent = {item["resource_id"] for item in json.loads(user)}
        assert sent == set(h.resource_ids)
        valid = _candidate(
            str(h.resource_ids[0])
        )  # Preserve integer-string compatibility.
        valid.update({"_context": {"forged": True}, "_context_id": "forged"})
        return [
            valid,
            _candidate(h.foreign_id),
            _candidate(h.published_id),
            _candidate(True),
            _candidate(float(h.resource_ids[0])),
            _candidate(999999),
        ]

    monkeypatch.setattr(llm, "chat_json", reply)
    with h.sessions.begin() as session:
        items = service.suggest_ontology_completion(session, h.ontology_id)
        assert len(items) == 1
        payload = items[0].payload
        baseline = payload["_context"]
        assert baseline["ontology"]["id"] == h.ontology_id
        assert baseline["resource"]["id"] == h.resource_ids[0]
        assert baseline["resource"]["edit_revision"] == 0
        assert baseline["resource"]["label_i18n"]["en-US"] == "Existing English"
        assert payload["_context_id"] != "forged"
        assert len(payload["_context_id"]) == 64


@pytest.mark.parametrize("change", ["edit", "legacy_edit", "remove", "pin", "ontology"])
def test_generation_rechecks_committed_changes_before_persisting(
    h: Harness, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    def reply(*args: Any, **kwargs: Any) -> list[dict]:
        with h.sessions.begin() as other:
            _change_context(other, h, change)
        return [_candidate(h.resource_ids[0])]

    monkeypatch.setattr(llm, "chat_json", reply)
    with h.sessions() as session:
        with pytest.raises(KGError) as exc:
            service.suggest_ontology_completion(session, h.ontology_id)
        assert exc.value.params["reason"] == "context_changed_regenerate"
        session.rollback()
    with h.sessions() as session:
        assert list(session.scalars(select(AiSuggestion))) == []


def _change_context(session: Session, h: Harness, change: str) -> None:
    resource_id = h.resource_ids[0]
    if change in {"edit", "legacy_edit"}:
        resource = session.get(ModelResource, resource_id)
        assert resource is not None
        if change == "edit":
            resource = lock_resource_edit(
                session, resource, resource.current_revision, resource.edit_revision
            )
        resource.label_i18n = {"en-US": "Human update"}
    elif change == "remove":
        session.execute(
            delete(OntologyResourceRef).where(
                OntologyResourceRef.ontology_id == h.ontology_id,
                OntologyResourceRef.resource_id == resource_id,
            )
        )
    elif change == "pin":
        session.execute(
            update(OntologyResourceRef)
            .where(
                OntologyResourceRef.ontology_id == h.ontology_id,
                OntologyResourceRef.resource_id == resource_id,
            )
            .values(pinned_revision=1)
        )
    else:
        session.execute(
            update(Ontology).where(Ontology.id == h.ontology_id).values(edit_revision=1)
        )


@pytest.mark.parametrize(
    "change", ["edit", "legacy_edit", "remove", "pin", "ontology", "publish"]
)
def test_apply_rejects_changed_context_even_in_old_session(
    h: Harness, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    suggestion_id = _generate(h, monkeypatch)[0]
    with h.sessions() as stale:
        stale.get(AiSuggestion, suggestion_id)
        stale.get(ModelResource, h.resource_ids[0])
        stale.get(Ontology, h.ontology_id)
        with h.sessions.begin() as other:
            if change == "publish":
                resource = other.get(ModelResource, h.resource_ids[0])
                assert resource is not None
                publish_resource(other, resource)
            else:
                _change_context(other, h, change)
        with pytest.raises(KGError) as exc:
            service.apply_suggestion(stale, suggestion_id)
        assert exc.value.code == ErrorCode.SUGGESTION_NOT_APPLICABLE
        assert exc.value.params["reason"] == "context_changed_regenerate"
        stale.rollback()
    _assert_pending(h, suggestion_id)


@pytest.mark.parametrize(
    "tamper", ["missing", "fingerprint", "resource_id", "target_id"]
)
def test_old_or_corrupted_suggestions_require_regeneration(
    h: Harness, monkeypatch: pytest.MonkeyPatch, tamper: str
) -> None:
    suggestion_id = _generate(h, monkeypatch)[0]
    with h.sessions.begin() as session:
        item = session.get(AiSuggestion, suggestion_id)
        assert item is not None
        payload = dict(item.payload)
        if tamper == "missing":
            payload.pop("_context")
        elif tamper == "fingerprint":
            payload["_context_id"] = "bad"
        elif tamper == "resource_id":
            payload["resource_id"] = h.foreign_id
        else:
            item.target_id = h.ontology_id + 1000
        item.payload = payload
    response = h.client.post(
        f"{API}/suggestions/{suggestion_id}/apply", headers=h.headers()
    )
    assert response.status_code == 409
    assert response.json()["code"] == ErrorCode.SUGGESTION_NOT_APPLICABLE
    assert response.json()["params"]["reason"] == (
        "context_missing_regenerate"
        if tamper == "missing"
        else "context_changed_regenerate"
    )
    _assert_pending(h, suggestion_id)


def test_editor_applies_only_missing_fields_and_commits_resource_audit(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    suggestion_ids = _generate(h, monkeypatch, both=True)
    for suggestion_id, resource_id in zip(suggestion_ids, h.resource_ids, strict=True):
        response = h.client.post(
            f"{API}/suggestions/{suggestion_id}/apply", headers=h.headers()
        )
        assert response.status_code == 200, response.text
        assert response.json()["kind"] == "ONTOLOGY_COMPLETION"
        assert response.json()["status"] == "APPLIED"
        with h.sessions() as session:
            resource = session.get(ModelResource, resource_id)
            assert resource is not None
            assert resource.label_i18n == {
                "zh-CN": "建议名称",
                "en-US": "Existing English",
                "fr": "Existing French",
            }
            assert resource.definition_i18n["fr"] == "Existing definition"
            assert resource.definition_i18n["en-US"] == "Suggested definition"
            assert resource.edit_revision == 1 and resource.current_revision == 0
            audit = session.scalar(
                select(AssetAuditLog).where(AssetAuditLog.object_id == resource_id)
            )
            assert audit is not None
            assert audit.actor_id == h.editor_id
            assert audit.object_type == "ENTITY_TYPE" and audit.action == "EDIT"
            assert audit.result == "OK"
            assert audit.version_before == {"current_revision": 0, "edit_revision": 0}
            assert audit.version_after == {"current_revision": 0, "edit_revision": 1}
            assert audit.correlation_id == response.headers["X-Correlation-ID"]
    listed = h.client.get(f"{API}/suggestions", headers=h.headers()).json()
    assert isinstance(listed, list) and len(listed) == 2


@pytest.mark.parametrize("operation", ["apply", "discard", "generate"])
def test_viewer_cannot_write_suggestions_or_assets(h: Harness, operation: str) -> None:
    with h.sessions.begin() as session:
        item = AiSuggestion(
            kind="ONTOLOGY_COMPLETION",
            target_id=h.ontology_id,
            title="Legacy",
            payload=_candidate(h.resource_ids[0]),
        )
        session.add(item)
        session.flush()
        suggestion_id = item.id
    path = (
        f"{API}/ontologies/{h.ontology_id}/suggest-completion"
        if operation == "generate"
        else f"{API}/suggestions/{suggestion_id}/{operation}"
    )
    response = h.client.post(path, headers=h.headers("VIEWER"))
    assert (
        response.status_code == 403 and response.json()["code"] == ErrorCode.FORBIDDEN
    )
    _assert_pending(h, suggestion_id)


@pytest.mark.parametrize(
    "first,second",
    [
        ("apply", "apply"),
        ("discard", "discard"),
        ("apply", "discard"),
        ("discard", "apply"),
    ],
)
def test_stale_sessions_cannot_resolve_suggestion_twice(
    h: Harness, monkeypatch: pytest.MonkeyPatch, first: str, second: str
) -> None:
    suggestion_id = _generate(h, monkeypatch)[0]
    functions = {
        "apply": service.apply_suggestion,
        "discard": service.discard_suggestion,
    }
    with h.sessions() as stale:
        cached = stale.get(AiSuggestion, suggestion_id)
        assert cached is not None and cached.status == "PENDING"
        with h.sessions.begin() as current:
            functions[first](current, suggestion_id)
        with pytest.raises(KGError) as exc:
            functions[second](stale, suggestion_id)
        assert exc.value.code == ErrorCode.SUGGESTION_NOT_APPLICABLE
        stale.rollback()
    with h.sessions() as session:
        item = session.get(AiSuggestion, suggestion_id)
        assert item is not None and item.status == (
            "APPLIED" if first == "apply" else "DISCARDED"
        )


def test_simultaneous_apply_and_discard_have_exactly_one_winner(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    suggestion_id = _generate(h, monkeypatch)[0]
    barrier = Barrier(2)

    def resolve(operation: str) -> str:
        with h.sessions() as session:
            cached = session.get(AiSuggestion, suggestion_id)
            assert cached is not None and cached.status == "PENDING"
            barrier.wait(timeout=10)
            try:
                if operation == "apply":
                    service.apply_suggestion(
                        session, suggestion_id, actor_id=h.editor_id
                    )
                else:
                    service.discard_suggestion(session, suggestion_id)
                session.commit()
                return operation
            except KGError as exc:
                session.rollback()
                assert exc.code == ErrorCode.SUGGESTION_NOT_APPLICABLE
                return "rejected"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(resolve, ("apply", "discard")))
    assert results.count("rejected") == 1
    with h.sessions() as session:
        item = session.get(AiSuggestion, suggestion_id)
        resource = session.get(ModelResource, h.resource_ids[0])
        assert item is not None and resource is not None
        applied = "apply" in results
        assert item.status == ("APPLIED" if applied else "DISCARDED")
        assert bool(resource.label_i18n.get("zh-CN")) == applied
        assert len(list(session.scalars(select(AssetAuditLog)))) == int(applied)


@pytest.mark.parametrize("failure", ["audit", "commit", "resource_lock"])
def test_api_failure_rolls_back_status_resource_token_and_audit(
    h: Harness, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    suggestion_id = _generate(h, monkeypatch)[0]

    def fail(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("Injected transaction failure")

    if failure == "audit":
        monkeypatch.setattr(service, "record_asset_audit", fail)
    elif failure == "resource_lock":
        monkeypatch.setattr(service, "lock_resource_edit", fail)
    else:
        event.listen(h.sessions, "before_commit", fail)
    try:
        response = h.client.post(
            f"{API}/suggestions/{suggestion_id}/apply", headers=h.headers()
        )
    finally:
        if failure == "commit":
            event.remove(h.sessions, "before_commit", fail)
    assert response.status_code == 500
    _assert_pending(h, suggestion_id)
    with h.sessions() as session:
        resource = session.get(ModelResource, h.resource_ids[0])
        assert resource is not None and resource.edit_revision == 0


def test_outer_rollback_cannot_leave_applied_suggestion_or_success_audit(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    suggestion_id = _generate(h, monkeypatch)[0]
    with h.sessions() as session:
        service.apply_suggestion(session, suggestion_id, actor_id=h.editor_id)
        session.rollback()
    _assert_pending(h, suggestion_id)
