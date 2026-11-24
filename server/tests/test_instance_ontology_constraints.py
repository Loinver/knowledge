"""G03：在临时数据库中验证冻结继承、子类端点与零/一/多关系基数。"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from app.core.db import Base
from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.domain.instance_validation_service import run_instance_validation
from app.domain.iri_service import register_namespace
from app.domain.ontology_service import create_ontology, publish_ontology
from app.domain.relation_service import create_relation_type, publish_relation_type
from app.domain.status_service import get_revision, publish_resource
from app.domain.type_service import create_entity_type, publish_entity_type
from app.models.data_access import Mapping, MappingRevision
from app.models.domain import Ontology, OntologyRevision
from app.models.enums import ResourceStatus, ValidationState
from app.models.extraction import (
    EntityIdentity,
    ExtractionRun,
    GraphRevision,
    GraphTriple,
)
from app.models.resource import ModelResource, ObjectPropDetail, ResourceParent
from app.models.validation import ValidationReport, ValidationResult
from app.schemas.ontology import OntologyCreate
from app.schemas.relation import CardinalitySpec, EndpointSpec, RelationTypeCreate
from app.schemas.type import DataTypePropCreate, EntityTypeCreate
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

NS = "https://example.org/instance-constraints/"


@pytest.fixture()
def session(tmp_path: Path) -> Iterator[Session]:
    engine = create_engine(f"sqlite:///{tmp_path}/instances.db")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            yield db
    finally:
        engine.dispose()


@dataclass
class Scenario:
    ontology: Ontology
    graph: GraphRevision
    parent: ModelResource
    child: ModelResource
    grandchild: ModelResource
    range_parent: ModelResource
    range_child: ModelResource
    relation: ModelResource


def _seed(
    session: Session,
    *,
    domain: tuple[int, int] = (0, -1),
    range_: tuple[int, int] = (0, -1),
) -> Scenario:
    ns = register_namespace(session, "ic", NS)

    def entity(
        name: str,
        parents: list[int] | None = None,
        props: list[DataTypePropCreate] | None = None,
    ) -> ModelResource:
        result = create_entity_type(
            session,
            EntityTypeCreate(
                name=name,
                namespace_id=ns.id,
                label_i18n={"en-US": name, "zh-CN": name},
                parent_ids=parents or [],
                data_props=props or [],
            ),
        )
        publish_entity_type(session, result)
        return result

    parent = entity(
        "Parent",
        props=[DataTypePropCreate(name="code", datatype="string", nullable=False)],
    )
    child = entity("Child", [parent.id])
    grandchild = entity("Grandchild", [child.id])
    range_parent = entity("RangeParent")
    range_child = entity("RangeChild", [range_parent.id])
    relation = create_relation_type(
        session,
        RelationTypeCreate(
            name="Rel",
            namespace_id=ns.id,
            label_i18n={"en-US": "Rel", "zh-CN": "Rel"},
            domain_spec=EndpointSpec(
                type_id=parent.id,
                cardinality=CardinalitySpec(min=domain[0], max=domain[1]),
            ),
            range_spec=EndpointSpec(
                type_id=range_parent.id,
                cardinality=CardinalitySpec(min=range_[0], max=range_[1]),
            ),
        ),
    )
    publish_relation_type(session, relation)
    ontology = create_ontology(
        session,
        OntologyCreate(
            name="InstanceConstraints",
            iri=f"{NS}Ontology",
            label_i18n={"en-US": "Instances", "zh-CN": "Instances"},
            ref_resource_ids=[grandchild.id, range_child.id, relation.id],
        ),
    )
    publish_ontology(session, ontology)
    mapping = Mapping(name="InstanceConstraints", ontology_id=ontology.id)
    session.add(mapping)
    session.flush()
    revision = MappingRevision(mapping_id=mapping.id, revision=1, onto_version=1)
    session.add(revision)
    session.flush()
    run = ExtractionRun(mapping_revision_id=revision.id, status="SUCCESS")
    session.add(run)
    session.flush()
    graph = GraphRevision(run_id=run.id, is_current=True, publishable=True)
    session.add(graph)
    session.flush()
    return Scenario(
        ontology, graph, parent, child, grandchild, range_parent, range_child, relation
    )


def _entity(
    session: Session,
    scenario: Scenario,
    name: str,
    type_: ModelResource,
    attrs: dict | None = None,
) -> str:
    iri = f"{NS}{name}"
    session.add(
        EntityIdentity(
            graph_revision_id=scenario.graph.id,
            iri=iri,
            type_iri=type_.iri,
            row_key=name,
            attrs=attrs if attrs is not None else {"code": "ok"},
        )
    )
    session.flush()
    return iri


def _edge(session: Session, scenario: Scenario, subject: str, object_: str) -> None:
    session.add(
        GraphTriple(
            graph_revision_id=scenario.graph.id,
            subject=subject,
            predicate=scenario.relation.name,
            object_=object_,
        )
    )
    session.flush()


def _check(session: Session, scenario: Scenario, code: str) -> ValidationResult:
    report = run_instance_validation(session, scenario.graph.id)
    return next(result for result in report.results if result.check_code == code)


@pytest.mark.parametrize("level", ["child", "grandchild"])
@pytest.mark.parametrize(
    ("attrs", "expected"),
    [
        ({}, ValidationState.VIOLATION),
        ({"code": None}, ValidationState.VIOLATION),
        ({"code": []}, ValidationState.VIOLATION),
        ({"code": 42}, ValidationState.VIOLATION),
        ({"code": "ok"}, ValidationState.PASS),
        ({"code": ["a", "b"]}, ValidationState.PASS),
    ],
)
def test_inherited_required_attribute(
    session: Session, level: str, attrs: dict, expected: ValidationState
) -> None:
    scenario = _seed(session)
    iri = _entity(session, scenario, "instance", getattr(scenario, level), attrs)
    result = _check(session, scenario, "I03")
    assert result.state == expected
    if expected == ValidationState.VIOLATION:
        assert result.focus_node == iri
        assert result.detail["attr"] == "code"


@pytest.mark.parametrize("subject_level", ["parent", "child", "grandchild"])
@pytest.mark.parametrize("object_level", ["range_parent", "range_child"])
def test_subclass_domain_and_range_are_accepted(
    session: Session, subject_level: str, object_level: str
) -> None:
    scenario = _seed(session)
    subject = _entity(session, scenario, "s", getattr(scenario, subject_level))
    object_ = _entity(session, scenario, "o", getattr(scenario, object_level), {})
    _edge(session, scenario, subject, object_)
    assert _check(session, scenario, "I02").state == ValidationState.PASS


@pytest.mark.parametrize("direction", ["domain", "range"])
@pytest.mark.parametrize(
    ("bounds", "count", "expected"),
    [
        ((1, 1), 0, ValidationState.VIOLATION),
        ((1, 1), 1, ValidationState.PASS),
        ((1, 1), 3, ValidationState.VIOLATION),
        ((0, 0), 0, ValidationState.PASS),
        ((0, 0), 1, ValidationState.VIOLATION),
        ((0, 1), 0, ValidationState.PASS),
        ((0, 1), 1, ValidationState.PASS),
        ((0, 1), 3, ValidationState.VIOLATION),
        ((0, -1), 0, ValidationState.PASS),
        ((0, -1), 3, ValidationState.PASS),
        ((2, 3), 1, ValidationState.VIOLATION),
        ((2, 3), 3, ValidationState.PASS),
    ],
)
def test_all_target_instances_obey_directional_cardinality(
    session: Session,
    direction: str,
    bounds: tuple[int, int],
    count: int,
    expected: ValidationState,
) -> None:
    scenario = _seed(
        session, **{direction if direction == "domain" else "range_": bounds}
    )
    target = _entity(
        session,
        scenario,
        "target",
        scenario.grandchild if direction == "domain" else scenario.range_child,
        {"code": "ok"} if direction == "domain" else {},
    )
    for index in range(count):
        other = _entity(
            session,
            scenario,
            f"other-{index}",
            scenario.range_child if direction == "domain" else scenario.grandchild,
            {} if direction == "domain" else {"code": "ok"},
        )
        _edge(
            session,
            scenario,
            target if direction == "domain" else other,
            other if direction == "domain" else target,
        )
    result = _check(session, scenario, "I02")
    assert result.state == expected
    if expected == ValidationState.VIOLATION:
        assert result.focus_node == target
        assert result.detail == {
            "predicate": "Rel",
            "direction": direction,
            "min": bounds[0],
            "max": bounds[1],
            "count": count,
            "reason": "relation_cardinality_violation",
        }


@pytest.mark.parametrize("direction", ["domain", "range"])
def test_isolated_target_is_checked_even_when_other_instances_have_edges(
    session: Session, direction: str
) -> None:
    scenario = _seed(session, domain=(1, 1), range_=(1, 1))
    subject = _entity(session, scenario, "s", scenario.grandchild)
    object_ = _entity(session, scenario, "o", scenario.range_child, {})
    _edge(session, scenario, subject, object_)
    isolated = _entity(
        session,
        scenario,
        "isolated",
        scenario.child if direction == "domain" else scenario.range_child,
        {"code": "ok"} if direction == "domain" else {},
    )
    result = _check(session, scenario, "I02")
    assert result.state == ValidationState.VIOLATION
    assert result.focus_node == isolated
    assert result.detail["count"] == 0
    assert result.detail["direction"] == direction


def test_duplicate_facts_count_distinct_neighbours_without_deleting_facts(
    session: Session,
) -> None:
    scenario = _seed(session, domain=(1, 1), range_=(1, 1))
    subject = _entity(session, scenario, "s", scenario.child)
    object_ = _entity(session, scenario, "o", scenario.range_child, {})
    for _ in range(3):
        _edge(session, scenario, subject, object_)
    assert _check(session, scenario, "I02").state == ValidationState.PASS
    assert session.scalar(select(func.count()).select_from(GraphTriple)) == 3


@pytest.mark.parametrize(
    ("attrs", "expected"),
    [({}, ValidationState.VIOLATION), ({"code": "ok"}, ValidationState.PASS)],
)
def test_diamond_inheritance_preserves_required_attributes_and_both_endpoints(
    session: Session, attrs: dict, expected: ValidationState
) -> None:
    scenario = _seed(session)
    # Two frozen branches share Parent; Grandchild belongs to both endpoints.
    for resource, parents in (
        (scenario.range_parent, [scenario.parent.id]),
        (scenario.grandchild, [scenario.child.id, scenario.range_child.id]),
    ):
        frozen = get_revision(session, resource.id, 1)
        frozen.payload = {**frozen.payload, "parent_ids": parents}
    iri = _entity(session, scenario, "diamond", scenario.grandchild, attrs)
    _edge(session, scenario, iri, iri)
    assert _check(session, scenario, "I02").state == ValidationState.PASS
    assert _check(session, scenario, "I03").state == expected


def test_non_target_instances_and_other_graphs_do_not_affect_cardinality(
    session: Session,
) -> None:
    scenario = _seed(session, domain=(1, 1), range_=(0, -1))
    # RangeChild is unrelated to domain, so no outgoing edge is required.
    _entity(session, scenario, "non-target", scenario.range_child, {})
    assert _check(session, scenario, "I02").state == ValidationState.PASS
    subject = _entity(session, scenario, "s", scenario.child)
    other_graph = GraphRevision(run_id=scenario.graph.run_id)
    session.add(other_graph)
    session.flush()
    session.add(
        GraphTriple(
            graph_revision_id=other_graph.id,
            subject=subject,
            predicate="Rel",
            object_=f"{NS}non-target",
        )
    )
    session.flush()
    result = _check(session, scenario, "I02")
    assert result.state == ValidationState.VIOLATION
    assert result.detail["count"] == 0


def test_missing_frozen_endpoint_is_not_run_even_without_edges(
    session: Session,
) -> None:
    scenario = _seed(session)
    frozen = get_revision(session, scenario.relation.id, 1)
    frozen.payload = {
        **frozen.payload,
        "resource_refs": [
            ref
            for ref in frozen.payload["resource_refs"]
            if ref["role"] != "relation_range"
        ],
    }
    _entity(session, scenario, "s", scenario.child)
    assert _check(session, scenario, "I02").state == ValidationState.NOT_RUN


@pytest.mark.parametrize("direction", ["domain", "range"])
def test_unrelated_endpoint_type_remains_a_violation(
    session: Session, direction: str
) -> None:
    scenario = _seed(session)
    subject = _entity(
        session,
        scenario,
        "s",
        scenario.range_child if direction == "domain" else scenario.child,
    )
    object_ = _entity(
        session,
        scenario,
        "o",
        scenario.child if direction == "range" else scenario.range_child,
        {},
    )
    _edge(session, scenario, subject, object_)
    result = _check(session, scenario, "I02")
    assert result.state == ValidationState.VIOLATION
    assert f"expected_{direction}" in result.detail


@pytest.mark.parametrize(
    "cardinality",
    [
        None,
        {},
        {"min": 1},
        {"min": True, "max": 1},
        {"min": -1, "max": 1},
        {"min": 2, "max": 1},
        {"min": 0, "max": -2},
        {"min": 0, "max": None},
    ],
)
@pytest.mark.parametrize("direction", ["domain", "range"])
def test_missing_or_invalid_frozen_cardinality_is_not_run(
    session: Session, direction: str, cardinality: dict | None
) -> None:
    scenario = _seed(session)
    frozen = get_revision(session, scenario.relation.id, 1)
    frozen.payload = {
        **frozen.payload,
        "object_prop": {
            **frozen.payload["object_prop"],
            f"{direction}_cardinality": cardinality,
        },
    }
    _entity(session, scenario, "s", scenario.child)
    _entity(session, scenario, "o", scenario.range_child, {})
    result = _check(session, scenario, "I02")
    assert result.state == ValidationState.NOT_RUN
    assert result.detail["direction"] == direction
    assert result.detail["reason"] in {
        "missing_relation_cardinality_snapshot",
        "invalid_relation_cardinality_snapshot",
    }


def test_absent_object_property_snapshot_is_not_run_with_zero_edges(
    session: Session,
) -> None:
    scenario = _seed(session, domain=(1, 1))
    frozen = get_revision(session, scenario.relation.id, 1)
    frozen.payload = {
        key: value for key, value in frozen.payload.items() if key != "object_prop"
    }
    _entity(session, scenario, "s", scenario.child)
    result = _check(session, scenario, "I02")
    assert result.state == ValidationState.NOT_RUN
    assert result.detail["reason"] == "missing_relation_cardinality_snapshot"


@pytest.mark.parametrize("damage", ["missing", "cycle", "wrong_kind"])
def test_broken_frozen_ancestor_closure_fails_without_live_fallback(
    session: Session, damage: str
) -> None:
    scenario = _seed(session)
    reports_before = session.scalar(select(func.count()).select_from(ValidationReport))
    frozen = get_revision(session, scenario.child.id, 1)
    if damage == "missing":
        published = session.scalar(
            select(OntologyRevision).where(
                OntologyRevision.ontology_id == scenario.ontology.id
            )
        )
        assert published is not None
        published.resource_versions = {
            key: pin
            for key, pin in published.resource_versions.items()
            if key != str(scenario.parent.id)
        }
    else:
        parent_id = (
            scenario.grandchild.id if damage == "cycle" else scenario.relation.id
        )
        frozen.payload = {**frozen.payload, "parent_ids": [parent_id]}
    _entity(session, scenario, "s", scenario.grandchild)
    with pytest.raises(KGError) as exc:
        run_instance_validation(session, scenario.graph.id)
    assert exc.value.code == ErrorCode.VALIDATION_VIOLATION
    assert exc.value.params["reason"] in {
        "missing_resource_versions",
        "missing_parent_snapshot",
        "inheritance_cycle",
        "invalid_parent_kind",
    }
    assert (
        session.scalar(select(func.count()).select_from(ValidationReport))
        == reports_before
    )


@pytest.mark.parametrize("damage", ["properties", "constraints"])
def test_missing_inherited_frozen_data_is_not_pass(
    session: Session, damage: str
) -> None:
    scenario = _seed(session)
    frozen = get_revision(session, scenario.parent.id, 1)
    if damage == "properties":
        frozen.payload = {
            key: value
            for key, value in frozen.payload.items()
            if key != "datatype_props"
        }
    else:
        frozen.payload = {
            **frozen.payload,
            "datatype_props": [
                {key: value for key, value in prop.items() if key != "max_cardinality"}
                for prop in frozen.payload["datatype_props"]
            ],
        }
    _entity(session, scenario, "s", scenario.grandchild)
    if damage == "properties":
        with pytest.raises(KGError) as exc:
            run_instance_validation(session, scenario.graph.id)
        assert exc.value.params["reason"] == "incomplete_property_snapshot"
    else:
        result = _check(session, scenario, "I03")
        assert result.state == ValidationState.NOT_RUN
        assert result.detail["reason"] == "missing_property_constraints_snapshot"


def test_historical_checks_keep_frozen_parent_endpoints_and_bounds(
    session: Session,
) -> None:
    scenario = _seed(session, domain=(1, 1), range_=(1, 1))
    subject = _entity(session, scenario, "s", scenario.grandchild)
    object_ = _entity(session, scenario, "o", scenario.range_child, {})
    _edge(session, scenario, subject, object_)

    def results() -> list[tuple]:
        report = run_instance_validation(session, scenario.graph.id)
        return [(r.check_code, r.state, r.focus_node, r.detail) for r in report.results]

    before = results()
    assert _check(session, scenario, "I02").state == ValidationState.PASS
    assert _check(session, scenario, "I03").state == ValidationState.PASS
    parent_edge = session.scalar(
        select(ResourceParent).where(ResourceParent.child_id == scenario.child.id)
    )
    assert parent_edge is not None
    session.delete(parent_edge)
    scenario.child.status = ResourceStatus.DRAFT
    publish_resource(session, scenario.child)
    detail = session.get(ObjectPropDetail, scenario.relation.id)
    assert detail is not None
    detail.domain_min, detail.domain_max = 0, 0
    scenario.relation.status = ResourceStatus.DRAFT
    publish_resource(session, scenario.relation)
    assert results() == before


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("https://example.org/value", ValidationState.PASS),
        ("urn:example:identifier", ValidationState.PASS),
        ("../relative/path", ValidationState.PASS),
        ("", ValidationState.PASS),
        ("https://example.org/资料", ValidationState.PASS),
        ("https://example.org/a%20b", ValidationState.PASS),
        ("https://example.org/has space", ValidationState.VIOLATION),
        ("https://example.org/bad%escape", ValidationState.VIOLATION),
        ("http://[bad", ValidationState.VIOLATION),
        (42, ValidationState.VIOLATION),
        (None, ValidationState.VIOLATION),
    ],
)
def test_inherited_frozen_any_uri_values(
    session: Session, value: object, expected: ValidationState
) -> None:
    scenario = _seed(session)
    frozen = get_revision(session, scenario.parent.id, 1)
    frozen.payload = {
        **frozen.payload,
        "datatype_props": [
            {**prop, "datatype": "anyURI"} for prop in frozen.payload["datatype_props"]
        ],
    }
    _entity(session, scenario, "uri", scenario.grandchild, {"code": value})
    assert _check(session, scenario, "I03").state == expected
