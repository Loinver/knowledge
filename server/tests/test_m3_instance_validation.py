"""实例层校验报告（H-51）。

验收：四态统计不失真，规则命中清单可定位到焦点节点。
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from app.api.errors import install_error_handler
from app.api.v1.validation import router
from app.core.db import Base, get_session
from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.domain.enum_dictionary_service import create_dictionary, update_dictionary
from app.domain.instance_validation_service import run_instance_validation
from app.domain.ontology_service import add_ref, publish_ontology, remove_ref
from app.domain.status_service import get_revision, publish_resource
from app.domain.type_service import set_data_props
from app.domain.validation_service import run_ontology_validation
from app.models.data_access import Mapping, MappingRevision
from app.models.domain import Ontology, OntologyResourceRef, OntologyRevision
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
from app.models.resource import ModelResource, Namespace, ResourceRef
from app.models.validation import ValidationReport
from app.schemas.enum_dictionary import EnumDictionaryInput
from app.schemas.ontology import OntologyRefAdd
from app.schemas.type import DataTypePropCreate
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

NS = "https://example.org/kg/"


@pytest.fixture()
def session(tmp_path: Path) -> Iterator[Session]:
    engine = create_engine(
        f"sqlite:///{tmp_path}/validation.db",
        connect_args={"check_same_thread": False},
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
        status=ResourceStatus.DRAFT,
    )
    enterprise = ModelResource(
        kind=ResourceKind.ENTITY,
        name="Enterprise",
        iri=f"{NS}Enterprise",
        namespace_id=ns.id,
        label_i18n={"zh-CN": "企业"},
        status=ResourceStatus.DRAFT,
    )
    name_prop = ModelResource(
        kind=ResourceKind.DATATYPE_PROP,
        name="name",
        iri=f"{NS}name",
        namespace_id=ns.id,
        label_i18n={"zh-CN": "名称"},
        definition_i18n={"datatype": "string"},
        status=ResourceStatus.DRAFT,
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
        status=ResourceStatus.DRAFT,
    )
    db.add_all([employee, enterprise, name_prop, works_for])
    db.flush()
    onto = Ontology(name="inst-val", iri=NS)
    db.add(onto)
    db.flush()
    for res in [employee, enterprise, name_prop, works_for]:
        publish_resource(db, res)
        db.add(OntologyResourceRef(ontology_id=onto.id, resource_id=res.id))
    publish_ontology(db, onto)
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
    return {
        "graph": graph,
        "run": run,
        "onto": onto,
        "ns": ns,
        "revision": revision,
        "employee": employee,
        "enterprise": enterprise,
        "name_prop": name_prop,
        "relation": works_for,
    }


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
    with pytest.raises(KGError) as exc:
        run_instance_validation(session, 99999)
    assert exc.value.code == ErrorCode.RESOURCE_NOT_FOUND


def _report_content(report: ValidationReport) -> tuple[dict, list[tuple]]:
    return report.summary, [
        (r.check_code, r.state, r.focus_node, r.rule_id, r.detail, r.message)
        for r in report.results
    ]


def test_historical_graph_uses_mapping_ontology_version(session: Session) -> None:
    h = _seed(session)
    graph = h["graph"]
    _add_entity(session, graph, f"{NS}Employee/1", f"{NS}Employee", {"name": "Alice"})
    _add_entity(session, graph, f"{NS}Enterprise/1", f"{NS}Enterprise")
    _add_triple(session, graph, f"{NS}Employee/1", "works_for", f"{NS}Enterprise/1")
    session.flush()
    before = _report_content(run_instance_validation(session, graph.id))

    prop = h["name_prop"]
    prop.status = ResourceStatus.DRAFT
    prop.definition_i18n = {"datatype": "integer"}
    publish_resource(session, prop)
    relation = h["relation"]
    relation.status = ResourceStatus.DRAFT
    relation.definition_i18n = {
        "domain_iri": f"{NS}Enterprise",
        "range_iri": f"{NS}Employee",
    }
    publish_resource(session, relation)
    assert _report_content(run_instance_validation(session, graph.id)) == before

    ref = session.scalar(
        select(OntologyResourceRef).where(
            OntologyResourceRef.ontology_id == h["onto"].id,
            OntologyResourceRef.resource_id == h["employee"].id,
        )
    )
    assert ref is not None
    remove_ref(session, h["onto"].id, ref.id)
    assert _report_content(run_instance_validation(session, graph.id)) == before
    assert publish_ontology(session, h["onto"]) == 2
    assert h["revision"].onto_version == 1
    assert _report_content(run_instance_validation(session, graph.id)) == before


def _structured_seed(session: Session) -> dict:
    h = _seed(session)
    dictionary = create_dictionary(
        session,
        EnumDictionaryInput(
            name="Status",
            label_i18n={"zh-CN": "状态"},
            definition_i18n={"zh-CN": "业务状态"},
            entries=[{"value": "OPEN", "label_i18n": {"zh-CN": "开启"}}],
        ),
    )
    employee = h["employee"]
    employee.status = ResourceStatus.DRAFT
    set_data_props(
        session,
        employee,
        [
            DataTypePropCreate(name="aliases", datatype="string"),
            DataTypePropCreate(
                name="status",
                datatype="enum",
                enum_dict_id=dictionary.id,
                enum_dict_revision=1,
                nullable=False,
            ),
        ],
    )
    publish_resource(session, employee)
    association = ModelResource(
        kind=ResourceKind.ASSOC,
        name="Employment",
        iri=f"{NS}Employment",
        namespace_id=h["ns"].id,
        label_i18n={"zh-CN": "任职"},
    )
    session.add(association)
    session.flush()
    set_data_props(
        session,
        association,
        [DataTypePropCreate(name="weight", datatype="decimal")],
        "assoc_attribute",
    )
    publish_resource(session, association)
    add_ref(session, h["onto"].id, OntologyRefAdd(resource_id=association.id))
    relation = h["relation"]
    relation.status = ResourceStatus.DRAFT
    relation.definition_i18n = None
    session.add_all(
        [
            ResourceRef(
                source_id=relation.id, target_id=employee.id, role="relation_domain"
            ),
            ResourceRef(
                source_id=relation.id,
                target_id=h["enterprise"].id,
                role="relation_range",
            ),
        ]
    )
    publish_resource(session, relation)
    h["revision"].onto_version = publish_ontology(session, h["onto"])
    session.flush()
    return {**h, "dictionary": dictionary, "association": association}


def test_structured_snapshots_keep_association_multivalue_and_enum_checks_frozen(
    session: Session,
) -> None:
    h = _structured_seed(session)
    graph = h["graph"]
    _add_entity(
        session,
        graph,
        f"{NS}Employee/1",
        f"{NS}Employee",
        {"aliases": ["Alice", "A"], "status": "OPEN"},
    )
    _add_entity(session, graph, f"{NS}Enterprise/1", f"{NS}Enterprise")
    _add_triple(session, graph, f"{NS}Employee/1", "works_for", f"{NS}Enterprise/1")
    _add_evidence(
        session, graph, h["run"], f"{NS}Employee/1", "works_for", f"{NS}Enterprise/1"
    )
    for key in ("1", "2"):
        _add_entity(
            session,
            graph,
            f"{NS}Employment/{key}",
            f"{NS}Employment",
            {"weight": [1, 2.5]},
        )
    session.flush()
    report = run_instance_validation(session, graph.id)
    assert report.summary["violation"] == report.summary["not_run"] == 0
    before = _report_content(report)

    dictionary = h["dictionary"]
    update_dictionary(
        session,
        dictionary.id,
        EnumDictionaryInput(
            name="Status",
            label_i18n={"zh-CN": "状态"},
            definition_i18n={"zh-CN": "新状态"},
            entries=[{"value": "CLOSED", "label_i18n": {"zh-CN": "关闭"}}],
        ),
        revision=1,
    )
    h["employee"].status = ResourceStatus.DRAFT
    set_data_props(
        session, h["employee"], [DataTypePropCreate(name="aliases", datatype="integer")]
    )
    publish_resource(session, h["employee"])
    endpoint = session.scalar(
        select(ResourceRef).where(
            ResourceRef.source_id == h["relation"].id,
            ResourceRef.role == "relation_domain",
        )
    )
    assert endpoint is not None
    endpoint.target_id = h["enterprise"].id
    session.flush()
    assert _report_content(run_instance_validation(session, graph.id)) == before
    assert (
        session.scalar(
            select(func.count())
            .select_from(EntityIdentity)
            .where(EntityIdentity.type_iri == f"{NS}Employment")
        )
        == 2
    )


@pytest.mark.parametrize(
    ("attrs", "state"),
    [
        ({"aliases": ["Alice", "A"]}, ValidationState.PASS),
        ({"aliases": ["Alice", 42]}, ValidationState.VIOLATION),
        ({"aliases": None}, ValidationState.PASS),
        ({"status": ["OPEN"]}, ValidationState.PASS),
        ({"status": ["OPEN", "CLOSED"]}, ValidationState.VIOLATION),
        ({"status": None}, ValidationState.VIOLATION),
        ({"status": []}, ValidationState.VIOLATION),
    ],
)
def test_i03_checks_values_against_owner_snapshot(
    session: Session, attrs: dict, state: ValidationState
) -> None:
    h = _structured_seed(session)
    _add_entity(session, h["graph"], f"{NS}Employee/1", f"{NS}Employee", attrs)
    session.flush()
    report = run_instance_validation(session, h["graph"].id)
    assert next(r.state for r in report.results if r.check_code == "I03") == state


def test_i02_checks_frozen_structural_endpoints(session: Session) -> None:
    h = _structured_seed(session)
    graph = h["graph"]
    _add_entity(session, graph, f"{NS}Employee/1", f"{NS}Employee")
    _add_entity(session, graph, f"{NS}Enterprise/1", f"{NS}Enterprise")
    _add_triple(session, graph, f"{NS}Enterprise/1", "works_for", f"{NS}Employee/1")
    session.flush()
    report = run_instance_validation(session, graph.id)
    result = next(r for r in report.results if r.check_code == "I02")
    assert result.state == ValidationState.VIOLATION
    assert result.detail["expected_domain"] == f"{NS}Employee"


@pytest.mark.parametrize(
    ("resource", "definition", "check_code"),
    [
        ("relation", None, "I02"),
        ("name_prop", {"datatype": "unsupported"}, "I03"),
        ("name_prop", {"datatype": "enum"}, "I03"),
    ],
)
def test_checks_without_required_constraints_are_not_run(
    session: Session, resource: str, definition: dict | None, check_code: str
) -> None:
    h = _seed(session)
    revision = get_revision(session, h[resource].id, 1)
    revision.payload = {**revision.payload, "definition_i18n": definition}
    graph = h["graph"]
    _add_entity(session, graph, f"{NS}Employee/1", f"{NS}Employee", {"name": "Alice"})
    _add_entity(session, graph, f"{NS}Enterprise/1", f"{NS}Enterprise")
    _add_triple(session, graph, f"{NS}Employee/1", "works_for", f"{NS}Enterprise/1")
    session.flush()
    report = run_instance_validation(session, graph.id)
    assert next(r.state for r in report.results if r.check_code == check_code) == (
        ValidationState.NOT_RUN
    )
    assert report.summary["not_run"] == 1


@pytest.mark.parametrize(
    "missing", ["mapping_revision", "ontology", "resource", "structure", "pin"]
)
def test_missing_frozen_data_never_falls_back_to_current_resources(
    session: Session, missing: str
) -> None:
    h = _seed(session)
    if missing == "mapping_revision":
        session.delete(h["revision"])
    elif missing == "ontology":
        h["revision"].onto_version = 999
    elif missing == "resource":
        session.delete(get_revision(session, h["employee"].id, 1))
    elif missing == "structure":
        revision = get_revision(session, h["employee"].id, 1)
        revision.payload = {
            key: value
            for key, value in revision.payload.items()
            if key != "resource_refs"
        }
    else:
        published = session.scalar(select(OntologyRevision))
        assert published is not None
        published.resource_versions = {}
    session.flush()
    with pytest.raises(KGError) as exc:
        run_instance_validation(session, h["graph"].id)
    assert exc.value.code == (
        ErrorCode.REVISION_NOT_FOUND
        if missing in {"mapping_revision", "ontology", "resource"}
        else ErrorCode.VALIDATION_VIOLATION
    )
    assert session.scalar(select(func.count()).select_from(ValidationReport)) == 0


def test_missing_embedded_enum_snapshot_is_rejected(session: Session) -> None:
    h = _structured_seed(session)
    revision = get_revision(session, h["employee"].id, 2)
    revision.payload = {
        **revision.payload,
        "datatype_props": [
            {**prop, "enum_dictionary": None}
            for prop in revision.payload["datatype_props"]
        ],
    }
    session.flush()
    with pytest.raises(KGError) as exc:
        run_instance_validation(session, h["graph"].id)
    assert exc.value.code == ErrorCode.VALIDATION_VIOLATION
    assert exc.value.params["reason"] == "missing_or_invalid_enum_snapshot"
    assert session.scalar(select(func.count()).select_from(ValidationReport)) == 0


@pytest.mark.parametrize(
    "missing", ["list", "property", "duplicate_property", "nullable"]
)
def test_incomplete_owner_properties_never_use_same_named_legacy_property(
    session: Session, missing: str
) -> None:
    h = _seed(session)  # The ontology also contains the legacy name:string property.
    employee = h["employee"]
    employee.status = ResourceStatus.DRAFT
    set_data_props(
        session,
        employee,
        [
            DataTypePropCreate(name="name", datatype="integer", nullable=False),
            DataTypePropCreate(name="alias", datatype="string"),
        ],
    )
    frozen = publish_resource(session, employee)
    h["revision"].onto_version = publish_ontology(session, h["onto"])
    graph = h["graph"]
    _add_entity(session, graph, f"{NS}Employee/1", employee.iri, {"name": "Alice"})
    session.flush()
    report = run_instance_validation(session, graph.id)
    result = next(r for r in report.results if r.check_code == "I03")
    assert result.state == ValidationState.VIOLATION
    assert result.detail["datatype"] == "integer"

    props = frozen.payload["datatype_props"]
    assert len(props) == len(frozen.payload["resource_refs"]) == 2
    if missing == "list":
        frozen.payload = {
            key: value
            for key, value in frozen.payload.items()
            if key != "datatype_props"
        }
    else:
        remaining = [prop for prop in props if prop["name"] != "name"]
        if missing == "duplicate_property":
            remaining *= 2
        elif missing == "nullable":
            remaining = [
                {key: value for key, value in prop.items() if key != "nullable"}
                for prop in props
            ]
        frozen.payload = {**frozen.payload, "datatype_props": remaining}
    session.flush()

    with pytest.raises(KGError) as exc:
        run_instance_validation(session, graph.id)
    assert exc.value.code == ErrorCode.VALIDATION_VIOLATION
    with pytest.raises(KGError) as exc:
        run_ontology_validation(session, h["onto"].id)
    assert exc.value.code == ErrorCode.VALIDATION_VIOLATION
    assert session.scalar(select(func.count()).select_from(ValidationReport)) == 1


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

        exported = client.get(f"/api/v1/validation/reports/{rid}/export?format=json")
        assert exported.status_code == 200
        assert exported.headers["content-type"].startswith("application/json")
        payload = exported.json()
        assert payload["report_id"] == rid
        assert payload["target_revision"] == gr.id
        assert {item["state"] for item in payload["results"]} <= {
            "PASS",
            "VIOLATION",
            "NA",
            "NOT_RUN",
        }

        turtle = client.get(f"/api/v1/validation/reports/{rid}/export?format=turtle")
        assert turtle.status_code == 200
        from rdflib import Graph

        graph = Graph().parse(data=turtle.text, format="turtle")
        assert len(graph) >= 6
