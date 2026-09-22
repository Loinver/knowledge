"""H-40：1/2 度、隐藏类型不桥接、派生边组合、孤立点及多事实不去重。"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from app.api.v1.extraction import router
from app.core.db import Base, get_session
from app.core.errors import install_error_handler
from app.domain.graph_view_service import graph_view
from app.models.data_access import Mapping, MappingRevision
from app.models.domain import Ontology
from app.models.extraction import (
    DerivedEdge,
    EntityIdentity,
    ExtractionRun,
    GraphRevision,
    GraphTriple,
    Quarantine,
)
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
        ontology = Ontology(name="graph-view", iri="https://example.org/ontology/")
        db.add(ontology)
        db.flush()
        mapping = Mapping(name="graph-view", ontology_id=ontology.id)
        db.add(mapping)
        db.flush()
        revision = MappingRevision(mapping_id=mapping.id, revision=1, onto_version=1)
        db.add(revision)
        db.flush()
        run = ExtractionRun(mapping_revision_id=revision.id, status="SUCCESS")
        db.add(run)
        db.flush()
        graph = GraphRevision(run_id=run.id, is_current=True, publishable=True)
        db.add(graph)
        db.flush()
        for iri, type_iri in [
            ("a", "Person"),
            ("b", "Participation"),
            ("c", "Project"),
            ("alone", "Person"),
        ]:
            db.add(
                EntityIdentity(
                    graph_revision_id=graph.id,
                    iri=iri,
                    type_iri=type_iri,
                    row_key=iri,
                    attrs={},
                )
            )
        for subject, target in [("a", "b"), ("a", "b"), ("b", "c")]:
            db.add(
                GraphTriple(
                    graph_revision_id=graph.id,
                    subject=subject,
                    predicate="rel",
                    object_=target,
                )
            )
        db.add(
            DerivedEdge(
                graph_revision_id=graph.id,
                subject="a",
                predicate="derived",
                object_="c",
            )
        )
        db.commit()
        yield db
    engine.dispose()


def test_overview_includes_isolates_and_parallel_facts(session: Session) -> None:
    data = graph_view(session)
    assert {node["iri"] for node in data["nodes"]} == {"a", "b", "c", "alone"}
    assert data["entity_total"] == 4
    assert len(data["edges"]) == 4
    parallel = [
        edge
        for edge in data["edges"]
        if edge["subject"] == "a" and edge["object_"] == "b"
    ]
    assert len(parallel) == 2 and parallel[0]["id"] != parallel[1]["id"]
    assert data["truncated"] is False


def test_one_and_two_degree_neighborhood(session: Session) -> None:
    first = graph_view(session, center="a", depth=1, include_derived=False)
    assert {node["iri"]: node["distance"] for node in first["nodes"]} == {
        "a": 0,
        "b": 1,
    }
    second = graph_view(session, center="a", depth=2, include_derived=False)
    assert {node["iri"]: node["distance"] for node in second["nodes"]} == {
        "a": 0,
        "b": 1,
        "c": 2,
    }
    assert len(second["edges"]) == 3


def test_hidden_types_never_bridge_and_derived_toggle_is_independent(
    session: Session,
) -> None:
    hidden = graph_view(
        session,
        center="a",
        depth=2,
        excluded_types=["Participation"],
        include_derived=False,
    )
    assert [node["iri"] for node in hidden["nodes"]] == ["a"]
    assert hidden["edges"] == []
    derived = graph_view(session, center="a", depth=2, excluded_types=["Participation"])
    assert {node["iri"] for node in derived["nodes"]} == {"a", "c"}
    assert [edge["kind"] for edge in derived["edges"]] == ["DERIVED"]
    assert graph_view(session, center="a", excluded_types=["Person"])["nodes"] == []


def test_truncation_is_explicit_and_endpoints_are_visible(session: Session) -> None:
    for query in [
        {"node_limit": 1},
        {"edge_limit": 1},
        {"center": "a", "node_limit": 2},
        {"center": "a", "edge_limit": 1},
    ]:
        data = graph_view(session, **query)
        assert data["truncated"] is True
        iris = {node["iri"] for node in data["nodes"]}
        assert all(
            edge["subject"] in iris and edge["object_"] in iris
            for edge in data["edges"]
        )
    assert graph_view(session, center="alone", node_limit=1)["truncated"] is False


def test_graph_and_quarantine_are_revision_scoped(session: Session) -> None:
    first = graph_view(session)
    session.add(
        Quarantine(
            run_id=first["run_id"],
            table_name="source",
            row_key="1",
            field="name",
            rule_id="required",
        )
    )
    old_graph = session.get(GraphRevision, first["graph_revision_id"])
    assert old_graph is not None
    old_graph.is_current = False
    session.flush()
    old_run = session.get(ExtractionRun, first["run_id"])
    assert old_run is not None
    run = ExtractionRun(
        mapping_revision_id=old_run.mapping_revision_id, status="SUCCESS"
    )
    session.add(run)
    session.flush()
    new_graph = GraphRevision(run_id=run.id, is_current=True, publishable=True)
    session.add(new_graph)
    session.flush()
    session.add(
        EntityIdentity(
            graph_revision_id=new_graph.id,
            iri="a",
            type_iri="Other",
            row_key="a",
            attrs={},
        )
    )
    session.commit()
    current = graph_view(session)
    historical = graph_view(session, graph_revision_id=first["graph_revision_id"])
    assert current["entity_total"] == 1 and current["edges"] == []
    assert current["quarantine_count"] == 0
    assert historical["entity_total"] == 4 and len(historical["edges"]) == 4
    assert historical["quarantine_count"] == 1


def test_graph_view_api_validation_and_shape(session: Session) -> None:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    install_error_handler(app)
    app.dependency_overrides[get_session] = lambda: session
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/extraction/graph-view",
            params={
                "center": "a",
                "excluded_types": ["Participation"],
                "include_derived": False,
            },
        )
        assert response.status_code == 200
        assert response.json()["nodes"][0]["distance"] == 0
        assert response.json()["edges"] == []
        for params in [
            {"depth": 3},
            {"node_limit": 501},
            {"edge_limit": 2001},
            {"graph_revision_id": 0},
        ]:
            assert (
                client.get("/api/v1/extraction/graph-view", params=params).status_code
                == 422
            )
        assert (
            client.get(
                "/api/v1/extraction/graph-view", params={"graph_revision_id": 999}
            ).status_code
            == 404
        )
