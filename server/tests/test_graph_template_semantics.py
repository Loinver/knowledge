"""PC15: frozen semantic fields, compatible JSON and stale application guards."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from app.api.errors import install_error_handler
from app.api.v1.graph_templates import router
from app.core.db import Base, get_session
from app.models.domain import Ontology, OntologyRevision
from app.models.resource import ModelResource, Namespace, ResourceRevision
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db
    engine.dispose()


@pytest.fixture()
def client(session: Session) -> Iterator[TestClient]:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    install_error_handler(app)
    app.dependency_overrides[get_session] = lambda: session
    with TestClient(app) as value:
        yield value


def seed(session: Session, suffix: str = "A") -> tuple[Ontology, dict[str, str]]:
    namespace = Namespace(prefix=f"ex{suffix}", iri=f"https://example.org/{suffix}/")
    session.add(namespace)
    session.flush()
    props = [
        {
            "role": "data_prop",
            "name": f"{name}{suffix}",
            "iri": f"https://example.org/{suffix}/{name}",
            "datatype": datatype,
            "nullable": True,
        }
        for name, datatype in [
            ("weight", "decimal"),
            ("when", "date"),
            ("north", "decimal"),
            ("east", "decimal"),
            ("title", "string"),
        ]
    ]
    pins = {}
    for name, kind in [("Unit", "ENTITY"), ("Parent", "OBJECT_PROP")]:
        resource = ModelResource(
            namespace_id=namespace.id,
            name=f"{name}{suffix}",
            iri=f"https://example.org/{suffix}/{name}",
            kind=kind,
        )
        session.add(resource)
        session.flush()
        session.add(
            ResourceRevision(
                resource_id=resource.id,
                revision=1,
                checksum="pc15",
                payload={
                    "name": resource.name,
                    "iri": resource.iri,
                    "kind": kind,
                    "namespace": {"prefix": namespace.prefix, "iri": namespace.iri},
                    "parent_ids": [],
                    "resource_refs": [
                        {"target_id": 0, "role": "data_prop"} for _ in props
                    ]
                    if kind == "ENTITY"
                    else [],
                    "datatype_props": props if kind == "ENTITY" else [],
                },
            )
        )
        pins[str(resource.id)] = 1
    onto = Ontology(
        name=f"o{suffix}",
        iri=f"https://example.org/{suffix}/onto",
        status="PUBLISHED",
        current_revision=1,
    )
    session.add(onto)
    session.flush()
    session.add(
        OntologyRevision(
            ontology_id=onto.id,
            revision=1,
            ref_domains=[],
            ref_types=[int(key) for key in pins],
            rules=[],
            resource_versions=pins,
        )
    )
    session.commit()
    return onto, {
        "hierarchy_relation_iri": f"https://example.org/{suffix}/Parent",
        "measure_property_iri": props[0]["iri"],
        "time_property_iri": props[1]["iri"],
        "latitude_property_iri": props[2]["iri"],
        "longitude_property_iri": props[3]["iri"],
    }


def payload(onto: Ontology, config: dict) -> dict:
    return {
        "name_i18n": {"zh-CN": "视图", "en-US": "View"},
        "layout_id": "timeline",
        "ontology_id": onto.id,
        "ontology_revision": 1,
        "config": config,
    }


@pytest.mark.parametrize("suffix", ["A", "B"])
def test_fields_roundtrip_and_frozen_names(
    client: TestClient, session: Session, suffix: str
) -> None:
    onto, config = seed(session, suffix)
    catalog = client.get(
        "/api/v1/view-templates/semantic-fields",
        params={"ontology_id": onto.id, "ontology_revision": 1},
    ).json()
    assert catalog["stale"] is False
    assert {field["iri"] for field in catalog["fields"]} >= set(config.values())
    assert (
        next(
            field
            for field in catalog["fields"]
            if field["iri"] == config["time_property_iri"]
        )["name"]
        == f"when{suffix}"
    )
    config.update(
        {
            "semantic_version": 1,
            "depth": 2,
            "custom_option": {"keep": True},
            "custom_null": None,
        }
    )
    created = client.post("/api/v1/view-templates", json=payload(onto, config))
    assert created.status_code == 201, created.text
    template_id = created.json()["id"]
    loaded = client.get(f"/api/v1/view-templates/{template_id}").json()
    assert loaded["config"] == config
    assert (
        client.get(
            f"/api/v1/view-templates/{template_id}/applicable",
            params={"ontology_id": onto.id, "ontology_revision": 1},
        ).status_code
        == 200
    )
    # Live resource changes never replace names from the pinned revision.
    for resource in session.query(ModelResource).all():
        resource.name += "Changed"
    session.commit()
    reloaded = client.get(
        "/api/v1/view-templates/semantic-fields",
        params={"ontology_id": onto.id, "ontology_revision": 1},
    ).json()
    assert reloaded == catalog


@pytest.mark.parametrize(
    "key,value",
    [
        ("hierarchy_relation_iri", "https://example.org/A/weight"),
        ("measure_property_iri", "https://example.org/A/title"),
        ("time_property_iri", "https://example.org/A/weight"),
        ("latitude_property_iri", "https://example.org/A/when"),
        ("longitude_property_iri", "https://example.org/A/missing"),
    ],
)
def test_rejects_unknown_or_wrong_datatype(
    client: TestClient, session: Session, key: str, value: str
) -> None:
    onto, config = seed(session)
    config[key] = value
    result = client.post("/api/v1/view-templates", json=payload(onto, config))
    assert result.status_code == 422
    assert result.json()["params"]["reason"] == "invalid_semantic_field"


def test_requires_coordinate_pair(client: TestClient, session: Session) -> None:
    onto, config = seed(session)
    del config["longitude_property_iri"]
    result = client.post("/api/v1/view-templates", json=payload(onto, config))
    assert result.status_code == 422
    assert result.json()["params"]["reason"] == "coordinate_pair_required"


def test_strict_pin_stale_and_graph_mismatch(
    client: TestClient, session: Session
) -> None:
    onto, config = seed(session)
    created = client.post("/api/v1/view-templates", json=payload(onto, config)).json()
    path = f"/api/v1/view-templates/{created['id']}/applicable"
    for pin in [
        {"ontology_id": onto.id + 1, "ontology_revision": 1},
        {"ontology_id": onto.id, "ontology_revision": 2},
    ]:
        assert client.get(path, params=pin).status_code == 409
    onto.current_revision = 2
    session.commit()
    assert (
        client.get(
            path, params={"ontology_id": onto.id, "ontology_revision": 1}
        ).status_code
        == 409
    )
    assert client.get(f"/api/v1/view-templates/{created['id']}").json()["stale"] is True
    for revision in [1, 3]:
        request = {**payload(onto, config), "ontology_revision": revision}
        assert client.post("/api/v1/view-templates", json=request).status_code == 409
    missing_snapshot = {**payload(onto, config), "ontology_revision": 2}
    assert (
        client.post("/api/v1/view-templates", json=missing_snapshot).status_code == 404
    )


def test_legacy_config_remains_readable_and_missing_snapshot_fails_closed(
    client: TestClient, session: Session
) -> None:
    onto, _ = seed(session)
    created = client.post(
        "/api/v1/view-templates", json=payload(onto, {"threshold": 5})
    ).json()
    assert created["config"]["threshold"] == 5
    assert created["config"]["semantic_version"] is None
    session.query(ResourceRevision).delete()
    session.commit()
    response = client.get(
        "/api/v1/view-templates/semantic-fields",
        params={"ontology_id": onto.id, "ontology_revision": 1},
    )
    assert response.status_code == 404
