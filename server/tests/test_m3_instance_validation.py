"""实例层校验报告（H-51）。

验收：四态统计不失真，规则命中清单可定位到焦点节点。
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from app.api.v1.validation import router
from app.core.db import Base, get_session
from app.core.errors import install_error_handler
from app.domain.instance_validation_service import run_instance_validation
from app.models.data_access import Mapping, MappingRevision
from app.models.domain import Ontology, OntologyResourceRef
from app.models.enums import ResourceKind, ResourceStatus, ValidationState
from app.models.extraction import (
    DerivedEdge,
    EntityIdentity,
    ExtractionRun,
    FactEvidence,
    GraphRevision,
    GraphTriple,
    Quarantine,
)
from app.models.resource import ModelResource, Namespace
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

NS = "https://example.org/kg/"


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db
    engine.dispose()


def _seed(db: Session) -> dict:
    """建本体 + 映射 + 图谱骨架，返回 fixture 句柄。"""
    ns = Namespace(prefix="kg", iri=NS, protected=False)
    db.add(ns)
    db.flush()
    employee = ModelResource(
        kind=ResourceKind.ENTITY,
        name="Employee",
        iri=f"{NS}Employee",
        namespace_id=ns.id,
        label_i18n={"zh-CN": "员工"},
        status=ResourceStatus.PUBLISHED,
        current_revision=1,
    )
    enterprise = ModelResource(
        kind=ResourceKind.ENTITY,
        name="Enterprise",
        iri=f"{NS}Enterprise",
        namespace_id=ns.id,
        label_i18n={"zh-CN": "企业"},
        status=ResourceStatus.PUBLISHED,
        current_revision=1,
    )
    name_prop = ModelResource(
        kind=ResourceKind.DATATYPE_PROP,
        name="name",
        iri=f"{NS}name",
        namespace_id=ns.id,
        label_i18n={"zh-CN": "名称"},
        definition_i18n={"datatype": "string"},
        status=ResourceStatus.PUBLISHED,
        current_revision=1,
    )
    works_for = ModelResource(
        kind=ResourceKind.OBJECT_PROP,
        name="works_for",
        iri=f"{NS}works_for",
        namespace_id=ns.id,
        label_i18n={"zh-CN": "就职于"},
        definition_i18n={
            "domain_iri": f"{NS}Employee",
            "range_iri": f"{NS}Enterprise",
        },
        status=ResourceStatus.PUBLISHED,
        current_revision=1,
    )
    db.add_all([employee, enterprise, name_prop, works_for])
    db.flush()
    onto = Ontology(name="inst-val", iri=NS)
    db.add(onto)
    db.flush()
    for res in [employee, enterprise, name_prop, works_for]:
        db.add(OntologyResourceRef(ontology_id=onto.id, resource_id=res.id))
    mapping = Mapping(name="inst-val", ontology_id=onto.id)
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
    db.commit()
    return {"graph": graph, "run": run, "onto": onto, "ns": ns}


def _add_entity(db, gr, iri, type_iri, attrs=None):
    db.add(
        EntityIdentity(
            graph_revision_id=gr.id,
            iri=iri,
            type_iri=type_iri,
            row_key=iri,
            attrs=attrs or {},
        )
    )


def _add_triple(db, gr, s, p, o):
    db.add(GraphTriple(graph_revision_id=gr.id, subject=s, predicate=p, object_=o))


def _add_evidence(db, gr, run, s, p, o):
    db.add(
        FactEvidence(
            graph_revision_id=gr.id,
            subject=s,
            predicate=p,
            object_=o,
            source_id=1,
            table_name="t",
            row_key="r",
            columns=["c"],
            run_id=run.id,
            evidence_type="RELATION",
        )
    )


def test_all_pass_when_graph_matches_ontology(session: Session) -> None:
    h = _seed(session)
    gr = h["graph"]
    run = h["run"]
    _add_entity(session, gr, f"{NS}Employee/1", f"{NS}Employee", {"name": "Alice"})
    _add_entity(session, gr, f"{NS}Enterprise/100", f"{NS}Enterprise")
    _add_triple(session, gr, f"{NS}Employee/1", "works_for", f"{NS}Enterprise/100")
    _add_evidence(
        session, gr, run, f"{NS}Employee/1", "works_for", f"{NS}Enterprise/100"
    )
    session.commit()
    report = run_instance_validation(session, gr.id)
    assert report.summary["violation"] == 0
    assert report.summary["pass"] >= 4
    states = {r.check_code: r.state for r in report.results}
    assert states["I01"] == ValidationState.PASS
    assert states["I02"] == ValidationState.PASS
    assert states["I03"] == ValidationState.PASS
    assert states["I04"] == ValidationState.PASS
    assert states["I05"] == ValidationState.PASS


def test_i01_violation_when_entity_type_undefined(session: Session) -> None:
    h = _seed(session)
    gr = h["graph"]
    _add_entity(session, gr, f"{NS}Ghost/1", f"{NS}Ghost")
    session.commit()
    report = run_instance_validation(session, gr.id)
    i01 = next(r for r in report.results if r.check_code == "I01")
    assert i01.state == ValidationState.VIOLATION
    assert i01.focus_node == f"{NS}Ghost/1"


def test_i02_violation_when_relation_type_undefined(session: Session) -> None:
    h = _seed(session)
    gr = h["graph"]
    _add_entity(session, gr, f"{NS}Employee/1", f"{NS}Employee")
    _add_entity(session, gr, f"{NS}Enterprise/100", f"{NS}Enterprise")
    _add_triple(session, gr, f"{NS}Employee/1", "unknown_rel", f"{NS}Enterprise/100")
    session.commit()
    report = run_instance_validation(session, gr.id)
    i02 = next(r for r in report.results if r.check_code == "I02")
    assert i02.state == ValidationState.VIOLATION
    assert i02.focus_node == "unknown_rel"


def test_i02_violation_when_endpoint_type_mismatches(session: Session) -> None:
    h = _seed(session)
    gr = h["graph"]
    _add_entity(session, gr, f"{NS}Enterprise/100", f"{NS}Enterprise")
    _add_entity(session, gr, f"{NS}Employee/1", f"{NS}Employee")
    _add_triple(session, gr, f"{NS}Enterprise/100", "works_for", f"{NS}Employee/1")
    session.commit()
    report = run_instance_validation(session, gr.id)
    i02 = next(r for r in report.results if r.check_code == "I02")
    assert i02.state == ValidationState.VIOLATION
    assert "expected_domain" in (i02.detail or {})


def test_i03_violation_when_attr_value_type_mismatches(session: Session) -> None:
    h = _seed(session)
    gr = h["graph"]
    _add_entity(session, gr, f"{NS}Employee/1", f"{NS}Employee", {"name": 12345})
    session.commit()
    report = run_instance_validation(session, gr.id)
    i03 = next(r for r in report.results if r.check_code == "I03")
    assert i03.state == ValidationState.VIOLATION
    assert i03.focus_node == f"{NS}Employee/1"


def test_i04_violation_when_fact_has_no_evidence(session: Session) -> None:
    h = _seed(session)
    gr = h["graph"]
    _add_entity(session, gr, f"{NS}Employee/1", f"{NS}Employee")
    _add_entity(session, gr, f"{NS}Enterprise/100", f"{NS}Enterprise")
    _add_triple(session, gr, f"{NS}Employee/1", "works_for", f"{NS}Enterprise/100")
    session.commit()
    report = run_instance_validation(session, gr.id)
    i04 = next(r for r in report.results if r.check_code == "I04")
    assert i04.state == ValidationState.VIOLATION
    assert i04.focus_node is not None


def test_i05_violation_when_quarantine_exists(session: Session) -> None:
    h = _seed(session)
    gr = h["graph"]
    run = h["run"]
    session.add(
        Quarantine(
            run_id=run.id,
            table_name="t",
            row_key="r",
            field="f",
            rule_id="required",
        )
    )
    session.commit()
    report = run_instance_validation(session, gr.id)
    i05 = next(r for r in report.results if r.check_code == "I05")
    assert i05.state == ValidationState.VIOLATION


def test_i06_violation_when_derived_edge_refs_missing(session: Session) -> None:
    h = _seed(session)
    gr = h["graph"]
    _add_entity(session, gr, f"{NS}Employee/1", f"{NS}Employee")
    session.add(
        DerivedEdge(
            graph_revision_id=gr.id,
            subject=f"{NS}Employee/1",
            predicate="derived",
            object_=f"{NS}Ghost/9",
        )
    )
    session.commit()
    report = run_instance_validation(session, gr.id)
    i06 = next(r for r in report.results if r.check_code == "I06")
    assert i06.state == ValidationState.VIOLATION


def test_graph_revision_not_found_raises(session: Session) -> None:
    from app.core.error_codes import ErrorCode
    from app.core.errors import KGError

    with pytest.raises(KGError) as exc:
        run_instance_validation(session, 99999)
    assert exc.value.code == ErrorCode.RESOURCE_NOT_FOUND


def test_api_validate_graph_and_results(session: Session) -> None:
    h = _seed(session)
    gr = h["graph"]
    _add_entity(session, gr, f"{NS}Employee/1", f"{NS}Employee", {"name": "Alice"})
    _add_entity(session, gr, f"{NS}Enterprise/100", f"{NS}Enterprise")
    _add_triple(session, gr, f"{NS}Employee/1", "works_for", f"{NS}Enterprise/100")
    _add_evidence(
        session, gr, h["run"], f"{NS}Employee/1", "works_for", f"{NS}Enterprise/100"
    )
    session.commit()
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    install_error_handler(app)
    app.dependency_overrides[get_session] = lambda: session
    with TestClient(app) as client:
        resp = client.post(f"/api/v1/validation/graph/{gr.id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["scope"] == "instance"
        assert body["target_id"] == gr.id
        rid = body["report_id"]
        results = client.get(f"/api/v1/validation/reports/{rid}/results").json()
        codes = {r["check_code"] for r in results}
        assert codes == {"I01", "I02", "I03", "I04", "I05", "I06"}
        for r in results:
            assert r["state"] in ("PASS", "VIOLATION", "NA", "NOT_RUN")
        not_found = client.post("/api/v1/validation/graph/99999")
        assert not_found.status_code == 404
