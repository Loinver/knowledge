"""M-04 模板完整生命周期、固定版本、引用删除竞态与迁移。"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from typing import Any

import pytest
from app.api.v1.ontologies import router as ontology_router
from app.api.v1.templates import router
from app.core.db import Base, get_session
from app.core.errors import install_error_handler
from app.domain import template_service as service
from app.domain.iri_service import register_namespace
from app.domain.status_service import publish_resource
from app.domain.type_service import create_entity_type
from app.models.domain import AssemblyTemplate, Ontology
from app.models.enums import ResourceStatus
from app.models.resource import ModelResource
from app.schemas.template import TemplateCreate
from app.schemas.type import EntityTypeCreate
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import Session, sessionmaker

URL = "/api/v1/governance/templates"
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def sessions(tmp_path: Path) -> Iterator[sessionmaker[Session]]:
    engine = create_engine(
        f"sqlite:///{tmp_path}/templates.db", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    yield sessionmaker(engine, expire_on_commit=False)
    engine.dispose()


@pytest.fixture()
def client(sessions: sessionmaker[Session]) -> Iterator[TestClient]:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.include_router(ontology_router, prefix="/api/v1")
    app.dependency_overrides[get_session] = lambda: sessions()
    install_error_handler(app)
    with TestClient(app) as client:
        yield client


@pytest.fixture()
def resource_id(sessions: sessionmaker[Session]) -> int:
    with sessions.begin() as session:
        ns = register_namespace(session, "ex", "https://example.org/")
        resource = create_entity_type(
            session,
            EntityTypeCreate(
                name="Person",
                namespace_id=ns.id,
                label_i18n={"zh-CN": "人员", "en-US": "Person"},
            ),
        )
        publish_resource(session, resource)
        return resource.id


def metadata(name: str = "Enterprise") -> dict[str, Any]:
    return {
        "name": name,
        "label_i18n": {"zh-CN": "企业模板", "en-US": "Enterprise template"},
        "source": "Enterprise policy",
        "basis": "Self-authored enterprise model",
    }


def payload(resource_id: int, **overrides: Any) -> dict[str, Any]:
    return {
        **metadata(),
        "resources": [{"resource_id": resource_id, "pinned_revision": 1}],
        **overrides,
    }


def ontology_payload(name: str = "NewOntology") -> dict[str, Any]:
    return {
        "name": name,
        "iri": f"https://example.org/ontology/{name}",
        "label_i18n": {"zh-CN": "新本体", "en-US": "New ontology"},
    }


def create(client: TestClient, resource_id: int) -> dict[str, Any]:
    response = client.post(URL, json=payload(resource_id))
    assert response.status_code == 201, response.text
    assert response.headers["etag"] == '"1"'
    return response.json()


def test_lifecycle_pins_resources_and_renames_reference_display(
    client: TestClient, sessions: sessionmaker[Session], resource_id: int
) -> None:
    template = create(client, resource_id)
    tid = template["id"]
    result = client.post(
        f"{URL}/{tid}/instantiate", headers={"If-Match": "1"}, json=ontology_payload()
    )
    assert result.status_code == 201, result.text
    onto = result.json()
    assert onto["template"]["source"] == "Enterprise policy"
    assert client.get(f"{URL}/{tid}").json()["reference_count"] == 1
    with sessions.begin() as session:
        resource = session.get(ModelResource, resource_id)
        assert resource is not None
        resource.status = ResourceStatus.DRAFT
        publish_resource(session, resource)
    update = client.put(
        f"{URL}/{tid}",
        headers={"If-Match": '"1"'},
        json=payload(
            resource_id,
            name="Renamed",
            resources=[{"resource_id": resource_id, "pinned_revision": 2}],
        ),
    )
    assert update.status_code == 200, update.text
    assert update.json()["revision"] == 2
    current = client.get(f"/api/v1/ontologies/{onto['id']}").json()
    assert current["template"]["name"] == "Renamed"
    assert (
        client.get(f"/api/v1/ontologies/{onto['id']}/refs").json()[0]["pinned_revision"]
        == 1
    )
    assert client.post(f"/api/v1/ontologies/{onto['id']}/publish").status_code == 200
    saved = client.post(
        f"{URL}/from-ontology",
        json={**metadata("Saved"), "ontology_id": onto["id"], "ontology_revision": 1},
    )
    assert saved.status_code == 201, saved.text
    assert saved.json()["resources"] == template["resources"]
    denied = client.delete(f"{URL}/{tid}", headers={"If-Match": "2"})
    assert denied.status_code == 422
    assert denied.json()["params"]["reason"] == "template_in_use"


def test_builtin_readonly_and_copy_creates_independent_custom(
    client: TestClient, sessions: sessionmaker[Session], resource_id: int
) -> None:
    template = create(client, resource_id)
    with sessions.begin() as session:
        item = session.get(AssemblyTemplate, template["id"])
        assert item is not None
        item.builtin = True
    url = f"{URL}/{template['id']}"
    for response in (
        client.put(url, headers={"If-Match": "1"}, json=payload(resource_id)),
        client.delete(url, headers={"If-Match": "1"}),
    ):
        assert response.status_code == 422
        assert response.json()["params"]["reason"] == "template_builtin_readonly"
    copied = client.post(
        url + "/copy", headers={"If-Match": "1"}, json=metadata("Copy")
    )
    assert copied.status_code == 201, copied.text
    assert copied.json()["builtin"] is False
    assert copied.json()["resources"] == template["resources"]
    assert (
        client.delete(
            f"{URL}/{copied.json()['id']}", headers={"If-Match": "1"}
        ).status_code
        == 204
    )
    assert client.get(url).status_code == 200
    assert (
        client.get(URL, params={"builtin": True, "q": "Enter", "page_size": 1}).json()[
            "total"
        ]
        == 1
    )


@pytest.mark.parametrize("field", ["source", "basis", "name", "label_i18n"])
def test_required_metadata(client: TestClient, resource_id: int, field: str) -> None:
    body = payload(resource_id)
    body[field] = {} if field == "label_i18n" else " "
    response = client.post(URL, json=body)
    assert response.status_code == 400
    assert response.json()["code"] == "KG.INVALID_REQUEST"


def test_revision_validation_conflict_and_original_create_path(
    client: TestClient, resource_id: int
) -> None:
    invalid = client.post(
        URL,
        json=payload(
            resource_id,
            resources=[{"resource_id": resource_id, "pinned_revision": 999}],
        ),
    )
    assert invalid.status_code == 404
    assert client.get(URL).json()["total"] == 0
    template = create(client, resource_id)
    url = f"{URL}/{template['id']}"
    assert client.put(url, json=payload(resource_id)).status_code == 400
    assert (
        client.put(
            url, headers={"If-Match": "9"}, json=payload(resource_id)
        ).status_code
        == 409
    )
    assert (
        client.post(
            url + "/copy", headers={"If-Match": "9"}, json=metadata()
        ).status_code
        == 409
    )
    # Existing ontology creation also participates in the reference lock protocol.
    failed = client.post(
        "/api/v1/ontologies",
        json={
            **ontology_payload(),
            "template_id": template["id"],
            "ref_resource_ids": [99999],
        },
    )
    assert failed.status_code == 404
    assert client.get(f"{URL}/{template['id']}").json()["reference_count"] == 0
    created = client.post(
        "/api/v1/ontologies", json={**ontology_payload(), "template_id": template["id"]}
    )
    assert created.status_code == 201, created.text
    assert created.json()["template"]["name"] == template["name"]
    assert client.delete(url, headers={"If-Match": "1"}).status_code == 422
    assert (
        client.post(
            "/api/v1/ontologies",
            json={**ontology_payload("Missing"), "template_id": 9999},
        ).status_code
        == 404
    )


def test_atomic_competing_updates(client: TestClient, resource_id: int) -> None:
    template = create(client, resource_id)
    barrier = Barrier(2)

    def write(name: str) -> int:
        barrier.wait(timeout=5)
        return client.put(
            f"{URL}/{template['id']}",
            headers={"If-Match": "1"},
            json=payload(resource_id, name=name),
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(write, ("First", "Second")))
    assert sorted(results) == [200, 409]
    assert client.get(f"{URL}/{template['id']}").json()["revision"] == 2


def test_delete_and_attach_cannot_leave_dangling_reference(
    client: TestClient, sessions: sessionmaker[Session], resource_id: int
) -> None:
    template = create(client, resource_id)
    barrier = Barrier(2)

    def operation(delete: bool) -> int:
        barrier.wait(timeout=5)
        if delete:
            return client.delete(
                f"{URL}/{template['id']}", headers={"If-Match": "1"}
            ).status_code
        return client.post(
            f"{URL}/{template['id']}/instantiate",
            headers={"If-Match": "1"},
            json=ontology_payload(),
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        deleted, created = list(pool.map(operation, (True, False)))
    assert (deleted, created) in {(204, 404), (422, 201)}
    with sessions() as session:
        for onto in session.scalars(select(Ontology)):
            assert session.get(AssemblyTemplate, onto.template_id) is not None


def test_outer_rollback_create_and_update(
    sessions: sessionmaker[Session], resource_id: int
) -> None:
    with pytest.raises(RuntimeError), sessions.begin() as session:
        service.create_template(session, TemplateCreate(**payload(resource_id)))
        raise RuntimeError("rollback")
    with sessions.begin() as session:
        assert session.scalar(select(AssemblyTemplate)) is None
        tid = service.create_template(
            session, TemplateCreate(**payload(resource_id))
        ).id
    with pytest.raises(RuntimeError), sessions.begin() as session:
        service.update_template(
            session, tid, 1, TemplateCreate(**payload(resource_id, name="Changed"))
        )
        raise RuntimeError("rollback")
    with sessions() as session:
        item = service.get_template(session, tid)
        assert (item.name, item.revision) == ("Enterprise", 1)


def test_catalog_includes_only_real_published_revisions(
    client: TestClient, resource_id: int
) -> None:
    result = client.get(URL + "/resources", params={"q": "Person"})
    assert result.status_code == 200
    assert result.json()["items"][0]["resource_id"] == resource_id
    assert result.json()["items"][0]["revisions"] == [1]


def test_migration_preserves_legacy_template(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path}/migration.db"
    env = {**os.environ, "KG_DATABASE_URL": url}

    def migrate(*args: str) -> None:
        subprocess.run(
            [sys.executable, "-m", "alembic", *args],
            cwd=ROOT,
            env=env,
            check=True,
            capture_output=True,
        )

    migrate("upgrade", "0003_ontology_metadata")
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO assembly_template (name, source, basis, builtin, payload) "
                "VALUES ('Legacy', 'Enterprise', 'Own description', 1, '{}')"
            )
        )
    migrate("upgrade", "head")
    with Session(engine) as session:
        item = session.scalar(select(AssemblyTemplate))
        assert item is not None
        assert (item.name, item.builtin, item.revision, item.label_i18n) == (
            "Legacy",
            True,
            1,
            {},
        )
    migrate("downgrade", "0003_ontology_metadata")
    assert "revision" not in {
        column["name"] for column in inspect(engine).get_columns("assembly_template")
    }
    migrate("upgrade", "head")
    with Session(engine) as session:
        assert session.scalar(select(AssemblyTemplate.name)) == "Legacy"
    engine.dispose()
