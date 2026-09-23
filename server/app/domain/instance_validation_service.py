"""实例层校验报告（H-51）。

对图谱版本做实例层校验，复用 M1 四态常量。
检查抽取产出是否符合本体定义。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.domain.ontology_snapshot import (
    ResourceSnapshot,
    load_ontology_snapshot,
    relation_endpoints,
)
from app.models.data_access import Mapping, MappingRevision
from app.models.enums import ResourceKind, ValidationState
from app.models.extraction import (
    DerivedEdge,
    EntityIdentity,
    ExtractionRun,
    FactEvidence,
    GraphRevision,
    GraphTriple,
    Quarantine,
)
from app.models.validation import ValidationReport, ValidationResult


def run_instance_validation(
    session: Session, graph_revision_id: int
) -> ValidationReport:
    """对图谱版本执行 6 项实例层校验，四态输出。"""
    gr = session.get(GraphRevision, graph_revision_id)
    if gr is None:
        raise KGError(
            ErrorCode.RESOURCE_NOT_FOUND,
            {"graph_revision_id": graph_revision_id},
        )
    run = session.get(ExtractionRun, gr.run_id)
    if run is None:
        raise KGError(ErrorCode.RESOURCE_NOT_FOUND, {"run_id": gr.run_id})
    rev = session.get(MappingRevision, run.mapping_revision_id)
    if rev is None:
        raise KGError(
            ErrorCode.REVISION_NOT_FOUND,
            {"mapping_revision_id": run.mapping_revision_id},
        )
    mapping = session.get(Mapping, rev.mapping_id)
    if mapping is None:
        raise KGError(ErrorCode.RESOURCE_NOT_FOUND, {"mapping_id": rev.mapping_id})
    resources = list(
        load_ontology_snapshot(session, mapping.ontology_id, rev.onto_version).values()
    )

    checks = [
        _check_i01_entity_type_defined(session, gr, resources),
        _check_i02_relation_endpoint_types(session, gr, resources),
        _check_i03_attribute_value_types(session, gr, resources),
        _check_i04_fact_evidence(session, gr),
        _check_i05_quarantine(session, gr),
        _check_i06_derived_edge_refs(session, gr),
    ]

    summary = {
        "pass": sum(1 for c in checks if c.state == ValidationState.PASS),
        "violation": sum(1 for c in checks if c.state == ValidationState.VIOLATION),
        "na": sum(1 for c in checks if c.state == ValidationState.NA),
        "not_run": sum(1 for c in checks if c.state == ValidationState.NOT_RUN),
    }
    report = ValidationReport(
        scope="instance",
        target_id=graph_revision_id,
        target_revision=graph_revision_id,
        summary=summary,
    )
    session.add(report)
    session.flush()
    for check in checks:
        check.report_id = report.id
        session.add(check)
    session.flush()
    return report


def _check_i01_entity_type_defined(
    session: Session, gr: GraphRevision, resources: list[ResourceSnapshot]
) -> ValidationResult:
    """I01：每个 EntityIdentity 的 type_iri 必须在本体已定义。"""
    entity_iris = {
        r.iri for r in resources if r.kind in {ResourceKind.ENTITY, ResourceKind.ASSOC}
    }
    entities = list(
        session.scalars(
            select(EntityIdentity).where(EntityIdentity.graph_revision_id == gr.id)
        )
    )
    undefined = [e for e in entities if e.type_iri not in entity_iris]
    if undefined:
        return ValidationResult(
            check_code="I01",
            state=ValidationState.VIOLATION,
            focus_node=undefined[0].iri,
            detail={
                "undefined_types": sorted({e.type_iri for e in undefined}),
                "count": len(undefined),
            },
            message="entity type not defined in ontology",
        )
    return ValidationResult(check_code="I01", state=ValidationState.PASS)


def _check_i02_relation_endpoint_types(
    session: Session, gr: GraphRevision, resources: list[ResourceSnapshot]
) -> ValidationResult:
    """I02：关系三元组的 subject/object 类型符合 domain/range。"""
    rel_by_name = {r.name: r for r in resources if r.kind == ResourceKind.OBJECT_PROP}
    resource_iris = {r.id: r.iri for r in resources}
    entity_type_map = _entity_type_map(session, gr)
    triples = list(
        session.scalars(
            select(GraphTriple).where(
                GraphTriple.graph_revision_id == gr.id,
                GraphTriple.predicate != "_entity_attrs",
            )
        )
    )
    for triple in triples:
        rel = rel_by_name.get(triple.predicate)
        if rel is None:
            return ValidationResult(
                check_code="I02",
                state=ValidationState.VIOLATION,
                focus_node=triple.predicate,
                detail={"predicate": triple.predicate},
                message="relation type not defined in ontology",
            )
        domain_iri, range_iri = relation_endpoints(rel, resource_iris)
        if not domain_iri or not range_iri:
            return ValidationResult(
                check_code="I02",
                state=ValidationState.NOT_RUN,
                focus_node=triple.predicate,
                message="relation endpoint definitions missing from snapshot",
            )
        subj_type = entity_type_map.get(triple.subject)
        obj_type = entity_type_map.get(triple.object_)
        if domain_iri and subj_type != domain_iri:
            return ValidationResult(
                check_code="I02",
                state=ValidationState.VIOLATION,
                focus_node=triple.predicate,
                detail={
                    "expected_domain": domain_iri,
                    "actual_subject_type": subj_type,
                    "subject": triple.subject,
                },
                message="subject type does not match relation domain",
            )
        if range_iri and obj_type != range_iri:
            return ValidationResult(
                check_code="I02",
                state=ValidationState.VIOLATION,
                focus_node=triple.predicate,
                detail={
                    "expected_range": range_iri,
                    "actual_object_type": obj_type,
                    "object": triple.object_,
                },
                message="object type does not match relation range",
            )
    return ValidationResult(check_code="I02", state=ValidationState.PASS)


def _check_i03_attribute_value_types(
    session: Session, gr: GraphRevision, resources: list[ResourceSnapshot]
) -> ValidationResult:
    """I03：实体属性值类型符合数据属性定义的 datatype。"""
    prop_by_name = {
        r.name: r for r in resources if r.kind == ResourceKind.DATATYPE_PROP
    }
    type_by_iri = {
        r.iri: r
        for r in resources
        if r.kind in {ResourceKind.ENTITY, ResourceKind.ASSOC}
    }
    valid_types = {"string", "integer", "decimal", "boolean", "date", "enum"}
    entities = list(
        session.scalars(
            select(EntityIdentity).where(EntityIdentity.graph_revision_id == gr.id)
        )
    )
    for entity in entities:
        attrs = entity.attrs or {}
        owner = type_by_iri.get(entity.type_iri)
        owner_props = (
            {prop.name: prop for prop in owner.datatype_props} if owner else {}
        )
        legacy_props = (
            owner is not None and "datatype_props" not in owner.model_fields_set
        )
        for attr_name, value in attrs.items():
            detail = owner_props.get(attr_name)
            prop = prop_by_name.get(attr_name)
            if detail is not None:
                datatype = detail.datatype
            elif prop is not None and legacy_props:
                datatype = (prop.definition_i18n or {}).get("datatype", "string")
            else:
                return ValidationResult(
                    check_code="I03",
                    state=ValidationState.VIOLATION,
                    focus_node=entity.iri,
                    detail={"attr": attr_name},
                    message="attribute not defined in ontology",
                )
            if datatype not in valid_types:
                return ValidationResult(
                    check_code="I03",
                    state=ValidationState.NOT_RUN,
                    focus_node=entity.iri,
                    detail={"attr": attr_name, "datatype": datatype},
                    message="unsupported datatype in resource snapshot",
                )
            if datatype == "enum" and (
                detail is None or detail.enum_dictionary is None
            ):
                return ValidationResult(
                    check_code="I03",
                    state=ValidationState.NOT_RUN,
                    focus_node=entity.iri,
                    detail={"attr": attr_name},
                    message="enum dictionary missing from resource snapshot",
                )
            values = value if isinstance(value, list) else [value]
            enum_values = (
                {entry.value for entry in detail.enum_dictionary.entries}
                if detail is not None and detail.enum_dictionary is not None
                else None
            )
            nullable = detail.nullable if detail is not None else False
            matches = (bool(values) or nullable) and all(
                (item is None and nullable)
                or (
                    _value_matches_type(item, datatype)
                    and (enum_values is None or item in enum_values)
                )
                for item in values
            )
            if not matches:
                return ValidationResult(
                    check_code="I03",
                    state=ValidationState.VIOLATION,
                    focus_node=entity.iri,
                    detail={
                        "attr": attr_name,
                        "datatype": datatype,
                        "value_type": type(value).__name__,
                    },
                    message="attribute value does not match datatype",
                )
    return ValidationResult(check_code="I03", state=ValidationState.PASS)


def _check_i04_fact_evidence(session: Session, gr: GraphRevision) -> ValidationResult:
    """I04：每条关系事实至少有一条 FactEvidence。无来源即不可信。"""
    triples = list(
        session.scalars(
            select(GraphTriple).where(
                GraphTriple.graph_revision_id == gr.id,
                GraphTriple.predicate != "_entity_attrs",
            )
        )
    )
    if not triples:
        return ValidationResult(
            check_code="I04", state=ValidationState.NA, message="no relation facts"
        )
    missing: list[str] = []
    for triple in triples:
        found = session.scalar(
            select(FactEvidence)
            .where(
                FactEvidence.graph_revision_id == gr.id,
                FactEvidence.subject == triple.subject,
                FactEvidence.predicate == triple.predicate,
                FactEvidence.object_ == triple.object_,
            )
            .limit(1)
        )
        if found is None:
            missing.append(f"{triple.subject} {triple.predicate} {triple.object_}")
    if missing:
        return ValidationResult(
            check_code="I04",
            state=ValidationState.VIOLATION,
            focus_node=missing[0],
            detail={"count": len(missing)},
            message="fact without evidence",
        )
    return ValidationResult(check_code="I04", state=ValidationState.PASS)


def _check_i05_quarantine(session: Session, gr: GraphRevision) -> ValidationResult:
    """I05：隔离记录标记。有隔离记录表示抽取时存在问题行。"""
    run = session.get(ExtractionRun, gr.run_id)
    assert run is not None
    found = session.scalar(
        select(Quarantine).where(Quarantine.run_id == run.id).limit(1)
    )
    if found is not None:
        return ValidationResult(
            check_code="I05",
            state=ValidationState.VIOLATION,
            detail={"run_id": run.id},
            message="quarantine records exist",
        )
    return ValidationResult(check_code="I05", state=ValidationState.PASS)


def _check_i06_derived_edge_refs(
    session: Session, gr: GraphRevision
) -> ValidationResult:
    """I06：派生边的 subject/object 必须是图谱中存在的实体。"""
    derived = list(
        session.scalars(
            select(DerivedEdge).where(DerivedEdge.graph_revision_id == gr.id)
        )
    )
    if not derived:
        return ValidationResult(
            check_code="I06", state=ValidationState.NA, message="no derived edges"
        )
    entity_iris = set(
        session.scalars(
            select(EntityIdentity.iri).where(EntityIdentity.graph_revision_id == gr.id)
        )
    )
    for edge in derived:
        if edge.subject not in entity_iris or edge.object_ not in entity_iris:
            return ValidationResult(
                check_code="I06",
                state=ValidationState.VIOLATION,
                focus_node=f"{edge.subject} {edge.predicate} {edge.object_}",
                detail={"edge_id": edge.id},
                message="derived edge references non-existent entity",
            )
    return ValidationResult(check_code="I06", state=ValidationState.PASS)


def _entity_type_map(session: Session, gr: GraphRevision) -> dict[str, str]:
    entities = list(
        session.scalars(
            select(EntityIdentity).where(EntityIdentity.graph_revision_id == gr.id)
        )
    )
    return {e.iri: e.type_iri for e in entities}


def _value_matches_type(value: object, datatype: str) -> bool:
    if datatype == "string":
        return isinstance(value, str)
    if datatype == "integer":
        return isinstance(value, int | float) and not isinstance(value, bool)
    if datatype == "decimal":
        return isinstance(value, int | float) and not isinstance(value, bool)
    if datatype == "boolean":
        return isinstance(value, bool)
    if datatype == "date":
        return isinstance(value, str)
    if datatype == "enum":
        return isinstance(value, str)
    return True
