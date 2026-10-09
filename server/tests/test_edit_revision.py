"""编辑令牌与发布修订号分离，覆盖 API、真实 SQL 竞争及迁移回放。"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest
from app.api.errors import install_error_handler
from app.api.v1.domains import router as domains_router
from app.api.v1.mappings import router as mappings_router
from app.api.v1.ontologies import router as ontologies_router
from app.core.db import Base, get_session
from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.domain.domain_service import get_domain, update_domain
from app.domain.iri_service import register_namespace
from app.domain.mapping_service import (
    get_draft_revision,
    get_mapping,
    publish_mapping,
    save_draft,
)
from app.domain.ontology_service import (
    create_ontology,
    get_ontology,
    publish_ontology,
    update_ontology,
)
from app.domain.status_service import publish_resource
from app.domain.type_service import create_entity_type
from app.models.data_access import Mapping, MappingPreview, MappingRevision
from app.models.domain import DomainRevision, Ontology, OntologyRevision
from app.schemas.domain import DomainUpdate
from app.schemas.mapping import MappingRevisionCreate
from app.schemas.ontology import OntologyCreate, OntologyUpdate
from app.schemas.type import EntityTypeCreate
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, inspect, select, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def sessions(tmp_path: Path) -> Iterator[sessionmaker[Session]]:
    engine = create_engine(
        f"sqlite:///{tmp_path}/edits.db", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    yield sessionmaker(engine, expire_on_commit=False)
    engine.dispose()


@pytest.fixture()
def client(sessions: sessionmaker[Session]) -> Iterator[TestClient]:
    app = FastAPI()
    for router in (domains_router, mappings_router, ontologies_router):
        app.include_router(router, prefix="/api/v1")
    install_error_handler(app)

    def get_test_session() -> Iterator[Session]:
        with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = get_test_session
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def published_resource_id(sessions: sessionmaker[Session]) -> int:
    with sessions.begin() as session:
        ns = register_namespace(session, "ex", "https://example.org/kg#")
        resource = create_entity_type(
            session,
            EntityTypeCreate(
                name="Employee", namespace_id=ns.id, label_i18n={"en-US": "Employee"}
            ),
        )
        publish_resource(session, resource)
        return resource.id


def _draft(source: str) -> dict[str, Any]:
    return {
        "entity_maps": [
            {
                "entity_type": "Employee",
                "table": "employees",
                "field_maps": [{"target_attr": "name", "source_field": source}],
            }
        ]
    }


def _aggregate(client: TestClient, kind: str) -> dict[str, Any]:
    response = client.post(
        f"/api/v1/{kind}",
        json={
            "name": "Catalog",
            "iri": "https://example.org/catalog",
            "label_i18n": {"en-US": "Initial"},
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["edit_revision"] == 0
    return response.json()


def _mapping(client: TestClient, *, with_draft: bool = True) -> dict[str, Any]:
    onto = _aggregate(client, "ontologies")
    response = client.post(
        f"/api/v1/ontologies/{onto['id']}/publish",
        headers={"If-Edit-Match": "0"},
    )
    assert response.status_code == 200, response.text
    response = client.post(
        "/api/v1/mappings",
        json={
            "name": "EmployeeMap",
            "ontology_id": onto["id"],
            "draft": _draft("initial") if with_draft else None,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _edit(session: Session, kind: str, resource_id: int) -> None:
    if kind == "mappings":
        save_draft(
            session,
            resource_id,
            MappingRevisionCreate.model_validate(_draft("changed")),
            if_match=0,
            if_edit_match=0,
        )
    elif kind == "domains":
        update_domain(
            session,
            get_domain(session, resource_id),
            DomainUpdate(label_i18n={"en-US": "Changed"}, if_match=0, if_edit_match=0),
        )
    else:
        update_ontology(
            session,
            get_ontology(session, resource_id),
            OntologyUpdate(
                label_i18n={"en-US": "Changed"}, if_match=0, if_edit_match=0
            ),
        )


@pytest.mark.parametrize("kind", ["mappings", "domains", "ontologies"])
def test_two_clients_with_same_token_have_one_winner(
    client: TestClient, kind: str
) -> None:
    resource = _mapping(client) if kind == "mappings" else _aggregate(client, kind)
    url = f"/api/v1/{kind}/{resource['id']}"
    write_url = f"{url}/draft" if kind == "mappings" else url

    def write(value: str) -> Any:
        content = (
            {"draft": _draft(value)}
            if kind == "mappings"
            else {"label_i18n": {"en-US": value}}
        )
        return client.put(
            write_url, json={**content, "if_match": 0, "if_edit_match": 0}
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(write, ["First", "Second"]))
    assert sorted(response.status_code for response in responses) == [200, 409]
    winner = next(
        response.json() for response in responses if response.status_code == 200
    )
    conflict = next(
        response.json() for response in responses if response.status_code == 409
    )
    assert conflict["code"] == "KG.REVISION_CONFLICT"
    assert conflict["params"]["expected"] == 0
    assert conflict["params"]["actual"] == 1
    current = client.get(url).json()
    assert current["current_revision"] == 0
    assert current["edit_revision"] == 1
    content = client.get(write_url).json()
    field = "entity_maps" if kind == "mappings" else "label_i18n"
    assert content[field] == winner[field]


@pytest.mark.parametrize("kind", ["mappings", "domains", "ontologies"])
def test_cached_orm_state_cannot_bypass_database_cas(
    client: TestClient, sessions: sessionmaker[Session], kind: str
) -> None:
    resource = _mapping(client) if kind == "mappings" else _aggregate(client, kind)
    getter = {
        "mappings": get_mapping,
        "domains": get_domain,
        "ontologies": get_ontology,
    }[kind]
    with sessions() as stale:
        cached = getter(stale, resource["id"])
        with sessions.begin() as fresh:
            _edit(fresh, kind, resource["id"])
        assert cached.edit_revision == 0
        with pytest.raises(KGError) as error:
            _edit(stale, kind, resource["id"])
        assert error.value.code == ErrorCode.REVISION_CONFLICT
        assert error.value.params["actual"] == 1


def test_mapping_publish_guards_last_saved_edit_and_keeps_frozen_revision(
    client: TestClient, sessions: sessionmaker[Session]
) -> None:
    mapping = _mapping(client)
    url = f"/api/v1/mappings/{mapping['id']}"
    first = client.get(f"{url}/draft").json()
    saved = client.put(
        f"{url}/draft",
        json={
            "draft": _draft("updated"),
            "if_match": 0,
            "if_edit_match": first["edit_revision"],
        },
    ).json()
    assert saved["revision"] == 0
    assert saved["edit_revision"] == 1
    conflict = client.post(f"{url}/publish", json={"if_match": 0, "if_edit_match": 0})
    assert conflict.status_code == 409
    assert client.get(url).json()["current_revision"] == 0
    response = client.post(f"{url}/publish", json={"if_match": 0, "if_edit_match": 1})
    assert response.status_code == 200, response.text
    frozen = response.json()
    assert (frozen["revision"], frozen["edit_revision"], frozen["onto_version"]) == (
        1,
        2,
        1,
    )
    assert frozen["entity_maps"] == saved["entity_maps"]
    with sessions.begin() as session:
        onto = get_ontology(session, mapping["ontology_id"])
        publish_ontology(session, onto, if_edit_match=onto.edit_revision)
    assert client.get(f"{url}/published").json() == frozen
    current = client.get(url).json()
    assert (current["current_revision"], current["edit_revision"]) == (1, 2)


def test_mapping_legacy_api_remains_compatible_but_advances_edit_token(
    client: TestClient,
) -> None:
    mapping = _mapping(client)
    url = f"/api/v1/mappings/{mapping['id']}"
    for edit, value in enumerate(["first", "second"], start=1):
        response = client.put(
            f"{url}/draft", json={"draft": _draft(value), "if_match": 0}
        )
        assert response.status_code == 200
        assert response.json()["edit_revision"] == edit
        assert response.json()["revision"] == 0
    stale = client.put(
        f"{url}/draft",
        json={"draft": _draft("stale"), "if_match": 0, "if_edit_match": 0},
    )
    assert stale.status_code == 409
    published = client.post(f"{url}/publish", json={"if_match": 0})
    assert published.status_code == 200
    assert published.json()["edit_revision"] == 3


def test_mapping_repeated_save_with_edit_token_overwrites_previous_draft(
    client: TestClient,
    sessions: sessionmaker[Session],
) -> None:
    mapping = _mapping(client)
    url = f"/api/v1/mappings/{mapping['id']}/draft"
    first = client.put(
        url, json={"draft": _draft("first"), "if_match": 0, "if_edit_match": 0}
    )
    assert first.status_code == 200, first.text
    with sessions.begin() as session:
        draft = get_draft_revision(session, mapping["id"])
        assert draft is not None
        session.add(MappingPreview(mapping_revision_id=draft.id, results={}, errors=[]))
    second = client.put(
        url,
        json={
            "draft": _draft("second"),
            "if_match": 0,
            "if_edit_match": first.json()["edit_revision"],
        },
    )
    assert second.status_code == 200, second.text
    assert second.json()["edit_revision"] == first.json()["edit_revision"] + 1
    with sessions() as session:
        previews = list(
            session.execute(
                select(MappingPreview).where(
                    MappingPreview.mapping_revision_id == first.json()["id"]
                )
            ).scalars()
        )
    assert previews == []


def test_mapping_save_response_token_is_captured_before_commit(
    client: TestClient, sessions: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    mapping = _mapping(client)
    url = f"/api/v1/mappings/{mapping['id']}"
    original_commit = Session.commit
    interleaved = False

    def commit_then_edit(session: Session) -> None:
        nonlocal interleaved
        original_commit(session)
        if not interleaved:
            interleaved = True
            with sessions() as other:
                save_draft(
                    other,
                    mapping["id"],
                    MappingRevisionCreate.model_validate(_draft("later")),
                    if_match=0,
                    if_edit_match=1,
                )
                original_commit(other)

    monkeypatch.setattr(Session, "commit", commit_then_edit)
    response = client.put(
        f"{url}/draft",
        json={"draft": _draft("mine"), "if_match": 0, "if_edit_match": 0},
    )
    assert response.status_code == 200, response.text
    assert response.json()["edit_revision"] == 1
    assert response.json()["entity_maps"][0]["field_maps"][0]["source_field"] == "mine"
    latest = client.get(f"{url}/draft").json()
    assert latest["edit_revision"] == 2
    assert latest["entity_maps"][0]["field_maps"][0]["source_field"] == "later"


def test_mapping_snapshot_refreshes_body_and_token_together(
    client: TestClient, sessions: sessionmaker[Session]
) -> None:
    mapping = _mapping(client)
    with sessions() as stale:
        initial = get_draft_revision(stale, mapping["id"])
        assert initial is not None and initial.edit_revision == 0
        with sessions.begin() as other:
            _edit(other, "mappings", mapping["id"])
        latest = get_draft_revision(stale, mapping["id"])
        assert latest is not None and latest.edit_revision == 1
        assert latest.entity_maps[0]["field_maps"][0]["source_field"] == "changed"


def test_mapping_publish_refreshes_a_cached_draft_after_locking(
    client: TestClient, sessions: sessionmaker[Session]
) -> None:
    mapping = _mapping(client)
    with sessions() as stale:
        initial = get_draft_revision(stale, mapping["id"])
        assert initial is not None and initial.edit_revision == 0
        with sessions.begin() as other:
            _edit(other, "mappings", mapping["id"])
        published = publish_mapping(stale, mapping["id"], if_match=0, if_edit_match=1)
        stale.commit()
        assert published.entity_maps[0]["field_maps"][0]["source_field"] == "changed"


def test_missing_mapping_parent_is_reported_as_a_missing_snapshot(
    client: TestClient, sessions: sessionmaker[Session]
) -> None:
    mapping = _mapping(client)
    # Legacy SQLite databases may contain revisions whose parent was removed.
    with sessions.begin() as session:
        session.execute(delete(Mapping).where(Mapping.id == mapping["id"]))
    url = f"/api/v1/mappings/{mapping['id']}"
    response = client.get(f"{url}/draft")
    assert response.status_code == 200 and response.json() is None
    response = client.get(f"{url}/published")
    assert response.status_code == 404
    assert response.json()["code"] == "KG.REVISION_NOT_FOUND"


@pytest.mark.parametrize(
    "kind,member_path", [("domains", "members"), ("ontologies", "refs")]
)
def test_membership_and_publish_share_edit_token_without_rewriting_snapshots(
    client: TestClient,
    sessions: sessionmaker[Session],
    published_resource_id: int,
    kind: str,
    member_path: str,
) -> None:
    resource = _aggregate(client, kind)
    url = f"/api/v1/{kind}/{resource['id']}"
    response = client.put(
        url, json={"label_i18n": {"en-US": "Saved"}, "if_match": 0, "if_edit_match": 0}
    )
    assert response.status_code == 200
    assert response.json()["edit_revision"] == 1
    member = client.post(
        f"{url}/{member_path}",
        json={"resource_id": published_resource_id, "if_edit_match": 1},
    )
    assert member.status_code == 201
    member_url = f"{url}/{member_path}/{member.json()['id']}"
    assert client.delete(member_url, headers={"If-Edit-Match": "1"}).status_code == 409
    assert (
        client.post(f"{url}/publish", headers={"If-Edit-Match": "1"}).status_code == 409
    )
    current = client.get(url).json()
    assert (current["current_revision"], current["edit_revision"]) == (0, 2)
    published = client.post(f"{url}/publish", headers={"If-Edit-Match": "2"})
    assert published.status_code == 200, published.text
    assert published.json() == {"revision": 1, "edit_revision": 3}
    update = client.put(
        url, json={"label_i18n": {"en-US": "Next"}, "if_match": 1, "if_edit_match": 3}
    )
    assert update.status_code == 200
    assert client.delete(member_url, headers={"If-Edit-Match": "4"}).status_code == 200
    current = client.get(url).json()
    assert (current["current_revision"], current["edit_revision"]) == (1, 5)
    with sessions() as session:
        if kind == "domains":
            frozen_domain = session.scalar(select(DomainRevision))
            assert frozen_domain is not None
            assert frozen_domain.payload["label_i18n"] == {"en-US": "Saved"}
            assert frozen_domain.payload["members"] == [
                {"resource_id": published_resource_id, "as_ref": False}
            ]
        else:
            frozen_onto = session.scalar(select(OntologyRevision))
            assert frozen_onto is not None
            assert frozen_onto.metadata_snapshot["label_i18n"] == {"en-US": "Saved"}
            assert frozen_onto.resource_versions == {str(published_resource_id): 1}


@pytest.mark.parametrize(
    "kind,member_path", [("domains", "members"), ("ontologies", "refs")]
)
def test_aggregate_legacy_api_remains_compatible(
    client: TestClient, published_resource_id: int, kind: str, member_path: str
) -> None:
    resource = _aggregate(client, kind)
    url = f"/api/v1/{kind}/{resource['id']}"
    for value in ["First", "Second"]:
        response = client.put(url, json={"label_i18n": {"en-US": value}, "if_match": 0})
        assert response.status_code == 200
    member = client.post(
        f"{url}/{member_path}", json={"resource_id": published_resource_id}
    )
    assert member.status_code == 201
    assert (
        client.delete(f"{url}/{member_path}/{member.json()['id']}").status_code == 200
    )
    published = client.post(f"{url}/publish")
    assert published.status_code == 200
    assert published.json() == {"revision": 1, "edit_revision": 5}


def test_canvas_layout_does_not_consume_ontology_edit_token(client: TestClient) -> None:
    ontology = _aggregate(client, "ontologies")
    url = f"/api/v1/ontologies/{ontology['id']}"
    assert client.get(f"{url}/canvas").status_code == 200
    response = client.put(
        f"{url}/canvas", json={"positions": {"1": {"x": 30, "y": 40}}}
    )
    assert response.status_code == 200
    current = client.get(url).json()
    assert (current["current_revision"], current["edit_revision"]) == (0, 0)
    assert (
        client.post(f"{url}/publish", headers={"If-Edit-Match": "0"}).status_code == 200
    )


@pytest.mark.parametrize("snapshot", ["missing", "stale", "ahead"])
def test_mapping_publish_uses_only_the_current_ontology_snapshot(
    client: TestClient, sessions: sessionmaker[Session], snapshot: str
) -> None:
    mapping = _mapping(client)
    with sessions.begin() as session:
        ontology = get_ontology(session, mapping["ontology_id"])
        if snapshot == "missing":
            session.execute(delete(OntologyRevision))
        elif snapshot == "stale":
            ontology.current_revision = 2
        else:
            session.add(OntologyRevision(ontology_id=ontology.id, revision=2))
    url = f"/api/v1/mappings/{mapping['id']}"
    response = client.post(f"{url}/publish", json={"if_match": 0, "if_edit_match": 0})
    if snapshot == "ahead":
        assert response.status_code == 200, response.text
        assert response.json()["onto_version"] == 1
    else:
        assert response.status_code == 404
        assert response.json()["params"]["reason"] == "no_ontology_revision"
        current = client.get(url).json()
        assert (current["current_revision"], current["edit_revision"]) == (0, 0)
        with sessions() as session:
            assert (
                session.scalar(
                    select(MappingRevision).where(MappingRevision.revision > 0)
                )
                is None
            )


def test_missing_mapping_draft_cannot_publish_or_consume_token(
    client: TestClient,
) -> None:
    mapping = _mapping(client, with_draft=False)
    url = f"/api/v1/mappings/{mapping['id']}"
    assert client.get(f"{url}/draft").json() is None
    response = client.post(f"{url}/publish", json={"if_match": 0, "if_edit_match": 0})
    assert response.status_code == 422
    assert response.json()["params"]["reason"] == "no_draft_to_publish"
    assert client.get(url).json()["edit_revision"] == 0


def test_failed_mapping_validation_preserves_draft_and_token(
    client: TestClient,
) -> None:
    mapping = _mapping(client)
    url = f"/api/v1/mappings/{mapping['id']}"
    before = client.get(f"{url}/draft").json()
    invalid = _draft("invalid")
    invalid["entity_maps"][0]["field_maps"] = []
    response = client.put(
        f"{url}/draft", json={"draft": invalid, "if_match": 0, "if_edit_match": 0}
    )
    assert response.status_code == 400
    assert client.get(f"{url}/draft").json() == before


def test_publish_ontology_keeps_uncommitted_rows_on_a_shared_connection() -> None:
    engine = create_engine("sqlite://", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        ontology = create_ontology(
            session,
            OntologyCreate(
                name="Draft",
                iri="https://example.org/draft",
                label_i18n={"en-US": "Draft"},
            ),
        )
        assert publish_ontology(session, ontology, if_edit_match=0) == 1
        session.commit()
    with Session(engine) as session:
        saved = session.scalar(select(Ontology))
        assert saved is not None
        assert (saved.current_revision, saved.edit_revision) == (1, 1)
        assert session.scalar(select(OntologyRevision.revision)) == 1
    engine.dispose()


def test_edit_revision_migration_preserves_rows_and_replays(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path}/migration.db"
    environment = {**os.environ, "KG_DATABASE_URL": url}

    def migrate(*args: str) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "alembic", *args],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        assert result.returncode == 0, result.stderr

    migrate("upgrade", "0010_ontology_rule_ids")
    engine = create_engine(url)
    draft_json = '[{"entity_type": "Legacy"}]'
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO ontology (id, name, iri, status, current_revision) "
                "VALUES (1, 'LegacyOntology', 'https://example.org/onto', "
                "'PUBLISHED', 2)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO business_domain "
                "(id, name, iri, status, current_revision) "
                "VALUES (1, 'LegacyDomain', 'https://example.org/domain', "
                "'PUBLISHED', 3)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO mapping (id, name, ontology_id, status, current_revision) "
                "VALUES (1, 'LegacyMapping', 1, 'DRAFT', 0)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO mapping_revision "
                "(mapping_id, revision, onto_version, entity_maps, rel_maps) "
                "VALUES (1, 0, 0, :entity_maps, '[]')"
            ),
            {"entity_maps": draft_json},
        )

    tables = {"ontology": 2, "business_domain": 3, "mapping": 0}
    migrate("upgrade", "head")
    with engine.connect() as connection:
        for table, revision in tables.items():
            columns = {
                column["name"]: column
                for column in inspect(connection).get_columns(table)
            }
            assert columns["edit_revision"]["nullable"] is False
            assert connection.execute(
                text(f"SELECT current_revision, edit_revision FROM {table}")
            ).one() == (revision, 0)
        assert (
            connection.scalar(text("SELECT entity_maps FROM mapping_revision"))
            == draft_json
        )
    with engine.begin() as connection:
        connection.execute(text("UPDATE mapping SET edit_revision = 5"))
    migrate("downgrade", "0010_ontology_rule_ids")
    with engine.connect() as connection:
        for table, revision in tables.items():
            assert "edit_revision" not in {
                column["name"] for column in inspect(connection).get_columns(table)
            }
            assert (
                connection.scalar(text(f"SELECT current_revision FROM {table}"))
                == revision
            )
    migrate("upgrade", "head")
    with Session(engine) as session:
        mapping = session.get(Mapping, 1)
        assert mapping is not None
        assert mapping.name == "LegacyMapping" and mapping.edit_revision == 0
    engine.dispose()
