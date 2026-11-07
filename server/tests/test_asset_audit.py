"""PC14: real HTTP writes, transaction failures, admin reads and payload exclusion."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from warnings import catch_warnings, filterwarnings

import pytest
from app.api.errors import install_error_handler
from app.api.v1 import (
    accounts,
    clauses,
    datasources,
    domains,
    enum_dictionaries,
    extraction,
    governance,
    mappings,
    namespaces,
    ontologies,
    relations,
    templates,
    types,
)
from app.api.v1.deps import authorize_business_request
from app.api.v1.ontology_restore import router as ontology_restore_router
from app.core.db import Base, get_session
from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.domain.account_service import issue_session
from app.models.account import AuthToken, User
from app.models.asset_audit import AssetAuditLog
from app.models.data_access import Mapping, MappingRevision
from app.models.domain import Ontology
from app.models.enums import RunResult, UserRole, UserStatus
from app.models.extraction import ExtractionRun, GraphRevision
from app.models.resource import Namespace
from fastapi import APIRouter, Depends, FastAPI
from fastapi.openapi.utils import get_openapi
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, delete, event, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

API = "/api/v1"
SENTINEL = "private-payload-do-not-audit"


@dataclass
class Harness:
    client: TestClient
    engine: Engine
    sessions: sessionmaker[Session]
    tokens: dict[str, str]
    users: dict[str, str]

    def headers(self, role: str = "EDITOR") -> dict[str, str]:
        return {"Authorization": f"Bearer {self.tokens[role]}"}

    def call(self, method: str, path: str, **kwargs: Any) -> Any:
        return self.client.request(
            method, f"{API}{path}", headers=self.headers(), **kwargs
        )

    def logs(self, **params: Any) -> dict:
        response = self.client.get(
            f"{API}/asset-audit-logs", headers=self.headers("ADMIN"), params=params
        )
        assert response.status_code == 200, response.text
        return response.json()


@pytest.fixture()
def h(tmp_path: Path) -> Iterator[Harness]:
    engine = create_engine(
        f"sqlite:///{tmp_path}/asset-audit.db",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def enable_fk(connection: Any, _: Any) -> None:
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)
    tokens, users = {}, {}
    with sessions.begin() as session:
        for role in UserRole:
            user = User(
                username=role.value.lower(),
                email=f"{role.value}@example.org",
                password_hash="unused-test-hash",
                role=role,
            )
            session.add(user)
            session.flush()
            tokens[role.value] = issue_session(session, user).access_token
            users[role.value] = user.id

    def request_session() -> Iterator[Session]:
        with sessions() as session:
            yield session

    app = FastAPI()
    install_error_handler(app)
    business = APIRouter(prefix=API, dependencies=[Depends(authorize_business_request)])
    for module in (
        namespaces,
        types,
        relations,
        domains,
        ontologies,
        mappings,
        datasources,
        governance,
        templates,
        enum_dictionaries,
        clauses,
        extraction,
    ):
        business.include_router(module.router)
    business.include_router(enum_dictionaries.legacy_router)
    business.include_router(ontology_restore_router)
    app.include_router(business)
    app.include_router(accounts.router, prefix=API)
    app.dependency_overrides[get_session] = request_session
    try:
        yield Harness(
            TestClient(app, raise_server_exceptions=False),
            engine,
            sessions,
            tokens,
            users,
        )
    finally:
        engine.dispose()


def create_ontology(h: Harness, name: str = "AuditOntology") -> dict:
    response = h.call(
        "POST",
        "/ontologies",
        json={
            "name": name,
            "iri": f"https://example.org/{name}",
            "label_i18n": {"en-US": SENTINEL},
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def create_entity(h: Harness) -> dict:
    ns = h.call(
        "POST",
        "/namespaces",
        json={
            "prefix": "audit",
            "iri": "https://example.org/audit#",
        },
    )
    assert ns.status_code == 201, ns.text
    result = h.call(
        "POST",
        "/entity-types",
        json={
            "name": "AuditEntity",
            "namespace_id": ns.json()["id"],
            "label_i18n": {"en-US": SENTINEL},
        },
    )
    assert result.status_code == 201, result.text
    return result.json()


def test_edit_assemble_publish_delete_and_versions(h: Harness) -> None:
    entity = create_entity(h)
    published = h.call("POST", f"/entity-types/{entity['id']}/publish")
    assert published.status_code == 200, published.text
    onto = create_ontology(h)
    path = f"/ontologies/{onto['id']}"
    edited = h.call(
        "PUT",
        path,
        json={
            "if_match": 0,
            "if_edit_match": 0,
            "definition_i18n": {"en-US": SENTINEL},
        },
    )
    assert edited.status_code == 200, edited.text
    added = h.call(
        "POST",
        f"{path}/refs",
        json={
            "resource_id": entity["id"],
            "pinned_revision": 1,
            "if_edit_match": edited.json()["edit_revision"],
        },
    )
    assert added.status_code == 201, added.text
    latest = h.call("GET", path).json()
    response = h.client.post(
        f"{API}{path}/publish",
        headers={**h.headers(), "If-Edit-Match": str(latest["edit_revision"])},
    )
    assert response.status_code == 200, response.text
    rows = h.logs(object_type="ONTOLOGY", object_id=onto["id"], sort="created_at")[
        "items"
    ]
    assert [row["action"] for row in rows] == ["CREATE", "EDIT", "ASSEMBLE", "PUBLISH"]
    assert rows[0]["version_before"] is None
    assert rows[1]["version_before"]["edit_revision"] == 0
    assert rows[1]["version_after"]["edit_revision"] == 1
    assert rows[2]["version_before"]["edit_revision"] == 1
    assert rows[2]["version_after"]["edit_revision"] == 2
    assert rows[-1]["version_after"]["current_revision"] == 1
    assert rows[-1]["correlation_id"] == response.headers["X-Correlation-ID"]
    assert all(
        row["actor_id"] == h.users["EDITOR"] and row["result"] == "OK" for row in rows
    )
    draft = create_ontology(h, "DeleteMe")
    removed = h.call("DELETE", f"/ontologies/{draft['id']}")
    assert removed.status_code == 200, removed.text
    deleted = h.logs(object_type="ONTOLOGY", object_id=draft["id"], action="DELETE")[
        "items"
    ][0]
    assert deleted["version_before"]["current_revision"] == 0
    assert deleted["version_after"] is None


def test_business_failure_is_rolled_back_before_independent_failed_event(
    h: Harness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    onto = create_ontology(h)

    def fail(session: Session, target: Ontology, payload: Any) -> None:
        target.label_i18n = {"en-US": "mutation-that-must-rollback"}
        session.flush()
        raise KGError(ErrorCode.REVISION_CONFLICT, {"password": SENTINEL}, SENTINEL)

    monkeypatch.setattr(ontologies, "update_ontology", fail)
    response = h.call("PUT", f"/ontologies/{onto['id']}", json={"if_match": 0})
    assert response.status_code == 409
    with h.sessions() as session:
        saved = session.get(Ontology, onto["id"])
        assert saved is not None and saved.label_i18n == {"en-US": SENTINEL}
    rows = h.logs(action="EDIT")["items"]
    assert len(rows) == 1
    assert rows[0]["result"] == "FAILED"
    assert rows[0]["version_after"] is None
    assert rows[0]["error_code"] == "KG.REVISION_CONFLICT"
    assert rows[0]["correlation_id"] == response.headers["X-Correlation-ID"]
    assert SENTINEL not in str(rows)


def test_audit_insert_failure_cannot_commit_business_change(h: Harness) -> None:
    attempts = []

    def fail_audit(_: Any, __: Any, sql: str, params: Any, ___: Any, ____: Any) -> None:
        if sql.startswith("INSERT INTO asset_audit_log"):
            attempts.append(sql)
            raise OperationalError("audit write unavailable", {}, Exception(SENTINEL))

    event.listen(h.engine, "before_cursor_execute", fail_audit)
    try:
        response = h.call(
            "POST",
            "/namespaces",
            json={
                "prefix": "failed",
                "iri": "https://example.org/failed#",
            },
        )
    finally:
        event.remove(h.engine, "before_cursor_execute", fail_audit)
    assert response.status_code == 503, response.text
    assert (
        len(attempts) == 2
    )  # one success insert, one bounded independent failure attempt
    with h.sessions() as session:
        assert session.scalar(select(Namespace.id)) is None
        assert session.scalar(select(AssetAuditLog.id)) is None


def test_database_commit_failure_removes_success_event(h: Harness) -> None:
    attempts = 0

    def fail_first_commit(_: Any) -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise OperationalError("commit unavailable", {}, Exception(SENTINEL))

    event.listen(h.engine, "commit", fail_first_commit)
    try:
        response = h.call(
            "POST",
            "/namespaces",
            json={
                "prefix": "rollback",
                "iri": "https://example.org/rollback#",
            },
        )
    finally:
        event.remove(h.engine, "commit", fail_first_commit)
    assert response.status_code == 503, response.text
    with h.sessions() as session:
        assert session.scalar(select(Namespace.id)) is None
    rows = h.logs()["items"]
    assert len(rows) == 1 and rows[0]["result"] == "FAILED"
    assert rows[0]["object_id"] is None


@pytest.mark.parametrize(
    "role,status", [(None, 401), ("VIEWER", 403), ("EDITOR", 403), ("ADMIN", 200)]
)
def test_asset_history_is_admin_only(h: Harness, role: str | None, status: int) -> None:
    response = h.client.get(
        f"{API}/asset-audit-logs", headers=h.headers(role) if role else {}
    )
    assert response.status_code == status


@pytest.mark.parametrize("state", ["invalid", "expired", "disabled"])
def test_invalid_admin_session_cannot_read_history(h: Harness, state: str) -> None:
    headers = h.headers("ADMIN")
    with h.sessions.begin() as session:
        if state == "disabled":
            user = session.get(User, h.users["ADMIN"])
            assert user is not None
            user.status = UserStatus.DISABLED
        elif state == "expired":
            token = session.scalar(
                select(AuthToken).where(AuthToken.user_id == h.users["ADMIN"])
            )
            assert token is not None
            token.expires_at = datetime.now(UTC) - timedelta(seconds=5)
        else:
            headers = {"Authorization": "Bearer invalid"}
    response = h.client.get(f"{API}/asset-audit-logs", headers=headers)
    assert response.status_code == (403 if state == "disabled" else 401)
    assert response.json()["code"] == (
        "AUTH.USER_DISABLED" if state == "disabled" else "AUTH.TOKEN_EXPIRED"
    )


def test_retains_actor_id_after_account_deletion_and_no_delete_api(h: Harness) -> None:
    create_ontology(h)
    with h.sessions.begin() as session:
        session.execute(delete(AuthToken).where(AuthToken.user_id == h.users["EDITOR"]))
        user = session.get(User, h.users["EDITOR"])
        assert user is not None
        session.delete(user)
    row = h.logs()["items"][0]
    assert row["actor_id"] == h.users["EDITOR"]
    for method in ("POST", "PUT", "PATCH", "DELETE"):
        response = h.client.request(
            method, f"{API}/asset-audit-logs", headers=h.headers("ADMIN")
        )
        assert response.status_code == 405
    assert h.logs()["total"] == 1


def test_filters_pagination_time_range_and_no_secret_capture(h: Harness) -> None:
    for i in range(3):
        create_ontology(h, f"Audit{i}")
    invalid = h.client.post(
        f"{API}/ontologies",
        headers={**h.headers(), "X-Correlation-ID": SENTINEL},
        json={"password": SENTINEL, "params": {"secret": SENTINEL}},
    )
    assert invalid.status_code == 422
    denied = h.client.post(f"{API}/ontologies", headers=h.headers("VIEWER"), json={})
    assert denied.status_code == 403
    first, second = h.logs(page_size=2), h.logs(page=2, page_size=2)
    assert first["total"] == 5 and second["total"] == 5
    assert {r["id"] for r in first["items"]}.isdisjoint(
        r["id"] for r in second["items"]
    )
    assert h.logs(result="FAILED")["total"] == 2
    assert (
        h.logs(actor_id=h.users["VIEWER"])["items"][0]["error_code"] == "AUTH.FORBIDDEN"
    )
    assert h.logs(q=h.users["EDITOR"])["total"] == 4
    assert h.logs(q="%")["total"] == 0
    cid = first["items"][0]["correlation_id"]
    assert h.logs(correlation_id=cid)["total"] == 1
    assert h.logs(q=cid)["total"] == 1
    assert SENTINEL not in str(h.logs())
    assert h.logs(since="2099-01-01T00:00:00Z")["total"] == 0
    assert h.logs(until="2000-01-01T00:00:00Z")["total"] == 0
    assert h.logs()["items"][0]["created_at"].endswith("Z")
    for params in (
        {"page_size": 201},
        {"page": 0},
        {"since": "2026-01-01"},
        {
            "since": "2026-01-02T00:00:00Z",
            "until": "2026-01-01T00:00:00Z",
        },
    ):
        response = h.client.get(
            f"{API}/asset-audit-logs", headers=h.headers("ADMIN"), params=params
        )
        assert response.status_code in (400, 422)


def test_graph_switch_records_previous_current_and_failed_attempt(h: Harness) -> None:
    onto = create_ontology(h)
    with h.sessions.begin() as session:
        mapping = Mapping(name="audit-map", ontology_id=onto["id"])
        session.add(mapping)
        session.flush()
        revision = MappingRevision(mapping_id=mapping.id, revision=1, onto_version=1)
        session.add(revision)
        session.flush()
        graphs = []
        for current, success in ((True, True), (False, True), (False, False)):
            run = ExtractionRun(
                mapping_revision_id=revision.id,
                status=RunResult.SUCCESS if success else RunResult.FAILED,
            )
            session.add(run)
            session.flush()
            graph = GraphRevision(
                run_id=run.id, is_current=current, publishable=success
            )
            session.add(graph)
            session.flush()
            graphs.append(graph.id)
    response = h.call("POST", f"/extraction/graph/{graphs[1]}/switch")
    assert response.status_code == 200, response.text
    failed = h.call("POST", f"/extraction/graph/{graphs[2]}/switch")
    assert failed.status_code == 422, failed.text
    rows = h.logs(action="SWITCH_CURRENT", sort="created_at")["items"]
    assert len(rows) == 2
    assert rows[0]["version_before"]["current_graph_revision_id"] == graphs[0]
    assert rows[0]["version_after"]["current_graph_revision_id"] == graphs[1]
    assert rows[1]["result"] == "FAILED" and rows[1]["version_after"] is None
    with h.sessions() as session:
        assert (
            session.scalar(select(GraphRevision.id).where(GraphRevision.is_current))
            == graphs[1]
        )


def test_template_assembly_and_copy_capture_new_target_before_commit(
    h: Harness,
) -> None:
    payload = {
        "name": "AuditTemplate",
        "label_i18n": {"zh-CN": "审计模板"},
        "source": "ENTERPRISE",
        "basis": SENTINEL,
    }
    created = h.call("POST", "/governance/templates", json=payload)
    assert created.status_code == 201, created.text
    tid = created.json()["id"]
    headers = {**h.headers(), "If-Match": "1"}
    copied = h.client.post(
        f"{API}/governance/templates/{tid}/copy",
        headers=headers,
        json={**payload, "name": "CopiedTemplate"},
    )
    assert copied.status_code == 201, copied.text
    response = h.client.post(
        f"{API}/governance/templates/{tid}/instantiate",
        headers=headers,
        json={
            "name": "Assembled",
            "iri": "https://example.org/assembled",
            "label_i18n": {"zh-CN": "装配测试"},
        },
    )
    assert response.status_code == 201, response.text
    rows = h.logs(action="ASSEMBLE")["items"]
    assert len(rows) == 1 and rows[0]["object_id"] == response.json()["id"]
    assert rows[0]["object_type"] == "ONTOLOGY"
    assert rows[0]["version_before"] is None
    assert rows[0]["version_after"]["current_revision"] == 0
    creates = h.logs(object_type="ASSEMBLY_TEMPLATE", sort="created_at")["items"]
    assert [row["object_id"] for row in creates] == [tid, copied.json()["id"]]
    assert SENTINEL not in str(h.logs())


def test_datasource_credentials_and_draft_mapping_payload_never_enter_audit(
    h: Harness,
) -> None:
    datasource = h.call(
        "POST",
        "/datasources",
        json={
            "name": "AuditSource",
            "kind": "sqlite",
            "params": {"database": "/unused/isolated.db"},
            "credential": SENTINEL,
        },
    )
    assert datasource.status_code == 201, datasource.text
    onto = create_ontology(h)
    mapped = h.call(
        "POST", "/mappings", json={"name": "AuditMapping", "ontology_id": onto["id"]}
    )
    assert mapped.status_code == 201, mapped.text
    mapping_id = mapped.json()["id"]
    draft = h.call(
        "PUT",
        f"/mappings/{mapping_id}/draft",
        json={
            "if_match": 0,
            "if_edit_match": 0,
            "draft": {"onto_version": 0, "entity_maps": [], "rel_maps": []},
        },
    )
    assert draft.status_code == 200, draft.text
    logs = h.logs(object_type="MAPPING", action="EDIT")["items"]
    assert logs[0]["object_id"] == mapping_id
    assert logs[0]["version_before"]["edit_revision"] == 0
    assert logs[0]["version_after"]["edit_revision"] == 1
    with h.sessions() as session:
        serialized = str(
            [
                {
                    column.name: getattr(row, column.name)
                    for column in AssetAuditLog.__table__.columns
                }
                for row in session.scalars(select(AssetAuditLog))
            ]
        )
    assert SENTINEL not in serialized
    assert "isolated.db" not in serialized


def test_post_commit_response_failure_does_not_invent_failed_mutation(
    h: Harness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    onto = create_ontology(h)

    def fail_response(*args: Any) -> Any:
        raise RuntimeError(SENTINEL)

    monkeypatch.setattr(ontologies, "_out", fail_response)
    response = h.call(
        "PUT",
        f"/ontologies/{onto['id']}",
        json={
            "if_match": 0,
            "if_edit_match": 0,
            "definition_i18n": {"en-US": "committed-description"},
        },
    )
    assert response.status_code == 500
    rows = h.logs(action="EDIT")["items"]
    assert len(rows) == 1 and rows[0]["result"] == "OK"
    with h.sessions() as session:
        saved = session.get(Ontology, onto["id"])
        assert saved is not None
        assert saved.definition_i18n == {"en-US": "committed-description"}


def test_independent_requests_do_not_share_actor_or_correlation(h: Harness) -> None:
    from concurrent.futures import ThreadPoolExecutor

    def create(role: str) -> Any:
        return h.client.post(
            f"{API}/ontologies",
            headers=h.headers(role),
            json={
                "name": f"Concurrent{role}",
                "iri": f"https://example.org/{role}",
                "label_i18n": {"en-US": role},
            },
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(create, ["ADMIN", "EDITOR"]))
    assert [response.status_code for response in responses] == [201, 201]
    rows = h.logs()["items"]
    assert len({row["correlation_id"] for row in rows}) == 2
    for response, role in zip(responses, ["ADMIN", "EDITOR"], strict=True):
        matched = next(row for row in rows if row["object_id"] == response.json()["id"])
        assert matched["actor_id"] == h.users[role]
        assert matched["correlation_id"] == response.headers["X-Correlation-ID"]


def test_same_asset_concurrent_edits_record_serialized_previous_versions(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from itertools import count
    from threading import Event

    from app.api.v1 import asset_audit_context
    from app.models.asset_audit import AssetType
    from sqlalchemy import Connection

    onto = create_ontology(h)
    captured_first, attempted_second, release_first = Event(), Event(), Event()
    order = count()
    original = asset_audit_context.read_asset_version

    def hold_first_capture(
        connection: Connection,
        object_type: AssetType,
        object_id: int | None,
        *,
        lock: bool = False,
    ) -> dict[str, int | None] | None:
        if not lock:
            return original(connection, object_type, object_id)
        number = next(order)
        if number == 1:
            attempted_second.set()
        result = original(connection, object_type, object_id, lock=lock)
        if number == 0:
            captured_first.set()
            assert release_first.wait(5)
        return result

    monkeypatch.setattr(asset_audit_context, "read_asset_version", hold_first_capture)

    def edit(value: str) -> Any:
        return h.call(
            "PUT",
            f"/ontologies/{onto['id']}",
            json={
                "if_match": 0,
                "definition_i18n": {"en-US": value},
            },
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(edit, "first")
        try:
            assert captured_first.wait(5)
            second = executor.submit(edit, "second")
            assert attempted_second.wait(5)
        finally:
            release_first.set()
        responses = [first.result(timeout=10), second.result(timeout=10)]
    assert [response.status_code for response in responses] == [200, 200]
    rows = h.logs(action="EDIT", object_id=onto["id"], sort="created_at")["items"]
    assert [
        (row["version_before"]["edit_revision"], row["version_after"]["edit_revision"])
        for row in rows
    ] == [(0, 1), (1, 2)]


def test_restore_creation_and_publish_share_audit_transaction(
    h: Harness, tmp_path: Path
) -> None:
    # Reuse the two-database transfer fixture without changing the restore service.
    from app.schemas.ontology import OntologyExportFormat

    from test_ontology_restore_apply import source_content

    content = source_content(tmp_path, OntologyExportFormat.TURTLE)
    preview = h.call(
        "POST",
        "/ontologies/import/restore-preview",
        json={
            "format": "turtle",
            "content": content,
        },
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["can_apply"]
    payload = {
        "format": "turtle",
        "content": content,
        "preview_digest": preview.json()["preview_digest"],
    }
    response = h.call("POST", "/ontologies/import/restore", json=payload)
    assert response.status_code == 200, response.text
    rows = h.logs()["items"]
    assert len(rows) == 1
    assert rows[0]["action"] == "CREATE" and rows[0]["object_type"] == "ONTOLOGY"
    assert rows[0]["object_id"] == response.json()["ontology_id"]
    assert rows[0]["version_before"] is None
    assert (
        rows[0]["version_after"]["current_revision"]
        == response.json()["current_revision"]
        == 1
    )
    assert content not in str(rows)
    again = h.call("POST", "/ontologies/import/restore", json=payload)
    assert again.status_code == 409, again.text
    failed = h.logs(result="FAILED")["items"]
    assert len(failed) == 1 and failed[0]["action"] == "CREATE"
    assert failed[0]["object_id"] is None and failed[0]["version_after"] is None


def test_main_exposes_audit_once_and_requires_admin(h: Harness) -> None:
    from app.main import app

    # Generate afresh so duplicate registration cannot hide in the schema cache.
    with catch_warnings():
        filterwarnings("error", message="Duplicate Operation ID.*")
        schema = get_openapi(title=app.title, version=app.version, routes=app.routes)
    operation_ids = [
        operation["operationId"]
        for path, methods in schema["paths"].items()
        if path == f"{API}/asset-audit-logs"
        for operation in methods.values()
    ]
    assert operation_ids == ["list_asset_audit_logs_api_v1_asset_audit_logs_get"]

    def request_session() -> Iterator[Session]:
        with h.sessions() as session:
            yield session

    previous = app.dependency_overrides.get(get_session)
    app.dependency_overrides[get_session] = request_session
    try:
        client = TestClient(app)
        assert (
            client.get(
                f"{API}/asset-audit-logs", headers=h.headers("ADMIN")
            ).status_code
            == 200
        )
        assert (
            client.get(
                f"{API}/asset-audit-logs", headers=h.headers("EDITOR")
            ).status_code
            == 403
        )
        assert client.get(f"{API}/asset-audit-logs").status_code == 401
    finally:
        if previous is None:
            app.dependency_overrides.pop(get_session, None)
        else:
            app.dependency_overrides[get_session] = previous
