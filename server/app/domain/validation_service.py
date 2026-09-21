"""资产层校验引擎（H-50）。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.models.domain import Ontology, OntologyResourceRef
from app.models.enums import ResourceKind, ValidationState
from app.models.resource import ModelResource, Namespace
from app.models.validation import ValidationReport, ValidationResult
from app.semantics.rdflib_backend import RdflibBackend


def run_ontology_validation(session: Session, ontology_id: int) -> ValidationReport:
    """对本体执行 8 项资产层校验，四态输出。"""
    onto = session.get(Ontology, ontology_id)
    if onto is None:
        raise KGError(ErrorCode.RESOURCE_NOT_FOUND, {"ontology_id": ontology_id})
    refs = list(
        session.execute(
            select(OntologyResourceRef).where(
                OntologyResourceRef.ontology_id == ontology_id
            )
        ).scalars()
    )
    resources: list[ModelResource] = []
    for ref in refs:
        res = session.get(ModelResource, ref.resource_id)
        if res is not None:
            resources.append(res)

    checks = [
        _check_a01_closure(session, resources, onto, refs),
        _check_a02_type_metadata(session, resources),
        _check_a03_property_range(session, resources),
        _check_a04_relation_endpoints(session, resources),
        _check_a05_rule_set(session, onto),
        _check_a06_core_template(session, onto),
        _check_a07_namespace(session, resources),
        _check_a08_owl_consistency(session, resources),
    ]

    summary = {
        "pass": sum(1 for c in checks if c.state == ValidationState.PASS),
        "violation": sum(1 for c in checks if c.state == ValidationState.VIOLATION),
        "na": sum(1 for c in checks if c.state == ValidationState.NA),
        "not_run": sum(1 for c in checks if c.state == ValidationState.NOT_RUN),
    }
    report = ValidationReport(
        scope="ontology",
        target_id=ontology_id,
        target_revision=onto.current_revision,
        summary=summary,
    )
    session.add(report)
    session.flush()
    for check in checks:
        check.report_id = report.id
        session.add(check)
    session.flush()
    return report


def _check_a01_closure(
    session: Session,
    resources: list[ModelResource],
    onto: Ontology,
    refs: list[OntologyResourceRef],
) -> ValidationResult:
    """A01 资源闭包：引用的资源全部存在。"""
    res_ids = {res.id for res in resources}
    missing = [r.resource_id for r in refs if r.resource_id not in res_ids]
    if missing:
        return ValidationResult(
            check_code="A01",
            state=ValidationState.VIOLATION,
            detail={"missing_ids": missing},
            message="dangling references",
        )
    return ValidationResult(check_code="A01", state=ValidationState.PASS)


def _check_a02_type_metadata(
    session: Session, resources: list[ModelResource]
) -> ValidationResult:
    """A02 类型元数据：实体类型 label_i18n 非空且含 zh-CN。"""
    for res in resources:
        if res.kind != ResourceKind.ENTITY:
            continue
        if not res.label_i18n or "zh-CN" not in res.label_i18n:
            return ValidationResult(
                check_code="A02",
                state=ValidationState.VIOLATION,
                focus_node=res.iri,
                detail={"resource": res.name, "field": "label_i18n"},
                message="missing zh-CN label",
            )
    return ValidationResult(check_code="A02", state=ValidationState.PASS)


def _check_a03_property_range(
    session: Session, resources: list[ModelResource]
) -> ValidationResult:
    """A03 属性值域：数据属性 datatype 合法。"""
    valid_types = {"string", "integer", "decimal", "boolean", "date", "enum"}
    for res in resources:
        if res.kind != ResourceKind.DATATYPE_PROP:
            continue
        datatype = (res.definition_i18n or {}).get("datatype", "string")
        if datatype not in valid_types:
            return ValidationResult(
                check_code="A03",
                state=ValidationState.VIOLATION,
                focus_node=res.iri,
                detail={"resource": res.name, "datatype": datatype},
                message="invalid datatype",
            )
    return ValidationResult(check_code="A03", state=ValidationState.PASS)


def _check_a04_relation_endpoints(
    session: Session, resources: list[ModelResource]
) -> ValidationResult:
    """A04 关系端点与关联实体：关系端点类型存在于引用中。"""
    resource_iris = {r.iri for r in resources}
    for res in resources:
        if res.kind != ResourceKind.OBJECT_PROP:
            continue
        meta = res.definition_i18n or {}
        domain_iri = meta.get("domain_iri")
        range_iri = meta.get("range_iri")
        if domain_iri and domain_iri not in resource_iris:
            return ValidationResult(
                check_code="A04",
                state=ValidationState.VIOLATION,
                focus_node=res.iri,
                detail={"missing": "domain", "iri": domain_iri},
                message="domain type not in ontology",
            )
        if range_iri and range_iri not in resource_iris:
            return ValidationResult(
                check_code="A04",
                state=ValidationState.VIOLATION,
                focus_node=res.iri,
                detail={"missing": "range", "iri": range_iri},
                message="range type not in ontology",
            )
    return ValidationResult(check_code="A04", state=ValidationState.PASS)


def _check_a05_rule_set(session: Session, onto: Ontology) -> ValidationResult:
    """A05 规则集：规则引用的资源存在。M1 规则集为空 → NA。"""
    return ValidationResult(
        check_code="A05",
        state=ValidationState.NA,
        message="no rules defined",
    )


def _check_a06_core_template(session: Session, onto: Ontology) -> ValidationResult:
    """A06 核心模板必需类型：M1 无模板实现 → NA。"""
    return ValidationResult(
        check_code="A06",
        state=ValidationState.NA,
        message="no template validation",
    )


def _check_a07_namespace(
    session: Session, resources: list[ModelResource]
) -> ValidationResult:
    """A07 命名空间与核心包锁定：引用资源的命名空间已注册。"""
    ns_ids = {r.namespace_id for r in resources}
    for ns_id in ns_ids:
        ns = session.get(Namespace, ns_id)
        if ns is None:
            return ValidationResult(
                check_code="A07",
                state=ValidationState.VIOLATION,
                detail={"namespace_id": ns_id},
                message="namespace not registered",
            )
    return ValidationResult(check_code="A07", state=ValidationState.PASS)


def _check_a08_owl_consistency(
    session: Session, resources: list[ModelResource]
) -> ValidationResult:
    """A08 OWL 一致性：未接完整推理器 → NOT_RUN，绝不能显示成 PASS。"""
    backend = RdflibBackend()
    if not backend.has_full_reasoner():
        return ValidationResult(
            check_code="A08",
            state=ValidationState.NOT_RUN,
            message="full OWL-DL reasoner not available",
        )
    return ValidationResult(
        check_code="A08",
        state=ValidationState.NOT_RUN,
        message="full OWL-DL reasoner not available",
    )
