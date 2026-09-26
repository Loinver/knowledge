"""资产层校验引擎（H-50）。"""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.domain import ontology_export_service
from app.domain.ontology_snapshot import (
    ResourceSnapshot,
    load_ontology_snapshot,
    load_resource_snapshot,
    relation_endpoints,
)
from app.domain.template_service import template_resources
from app.models.domain import (
    AssemblyTemplate,
    Ontology,
    OntologyResourceRef,
    OntologyRuleRef,
)
from app.models.enums import ResourceKind, ResourceStatus, ValidationState
from app.models.governance import Rule
from app.models.resource import ModelResource, Namespace
from app.models.validation import ValidationReport, ValidationResult
from app.semantics.backend import SemanticBackend

type ValidationResource = ModelResource | ResourceSnapshot


def get_validation_report(session: Session, report_id: int) -> ValidationReport:
    report = session.get(ValidationReport, report_id)
    if report is None:
        raise KGError(ErrorCode.RESOURCE_NOT_FOUND, {"report_id": report_id})
    return report


def run_ontology_validation(
    session: Session, ontology_id: int, *, backend: SemanticBackend | None = None
) -> ValidationReport:
    """对本体执行 8 项资产层校验，四态输出。"""
    onto = session.get(Ontology, ontology_id)
    if onto is None:
        raise KGError(ErrorCode.RESOURCE_NOT_FOUND, {"ontology_id": ontology_id})
    resources: list[ValidationResource] = []
    if onto.status == ResourceStatus.PUBLISHED:
        frozen = load_ontology_snapshot(session, onto.id, onto.current_revision)
        resources.extend(frozen.values())
        referenced_ids = list(frozen)
    else:
        refs = list(
            session.scalars(
                select(OntologyResourceRef).where(
                    OntologyResourceRef.ontology_id == ontology_id
                )
            )
        )
        referenced_ids = [ref.resource_id for ref in refs]
        for ref in refs:
            if ref.pinned_revision is not None:
                resources.append(
                    load_resource_snapshot(
                        session, ref.resource_id, ref.pinned_revision
                    )
                )
            else:
                res = session.get(ModelResource, ref.resource_id)
                if res is not None:
                    resources.append(res)

    checks = [
        _check_a01_closure(resources, referenced_ids),
        _check_a02_type_metadata(session, resources),
        _check_a03_property_range(session, resources),
        _check_a04_relation_endpoints(session, resources),
        _check_a05_rule_set(session, onto),
        _check_a06_core_template(session, onto, referenced_ids),
        _check_a07_namespace(session, resources),
        _check_a08_owl_consistency(session, onto, backend),
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
    resources: list[ValidationResource], referenced_ids: list[int]
) -> ValidationResult:
    """A01 资源闭包：引用的资源全部存在。"""
    res_ids = {res.id for res in resources}
    missing = [rid for rid in referenced_ids if rid not in res_ids]
    if missing:
        return ValidationResult(
            check_code="A01",
            state=ValidationState.VIOLATION,
            detail={"missing_ids": missing},
            message="dangling references",
        )
    return ValidationResult(check_code="A01", state=ValidationState.PASS)


def _check_a02_type_metadata(
    session: Session, resources: list[ValidationResource]
) -> ValidationResult:
    """A02 类型元数据：实体类型 label_i18n 非空且含 zh-CN。"""
    for res in resources:
        if res.kind not in {ResourceKind.ENTITY, ResourceKind.ASSOC}:
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
    session: Session, resources: list[ValidationResource]
) -> ValidationResult:
    """A03 属性值域：数据属性 datatype 合法。"""
    valid_types = {"string", "integer", "decimal", "boolean", "date", "enum"}
    for res in resources:
        if isinstance(res, ResourceSnapshot):
            for prop in res.datatype_props:
                if prop.datatype not in valid_types:
                    return ValidationResult(
                        check_code="A03",
                        state=ValidationState.VIOLATION,
                        focus_node=res.iri,
                        detail={"resource": prop.name, "datatype": prop.datatype},
                        message="invalid datatype",
                    )
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
    session: Session, resources: list[ValidationResource]
) -> ValidationResult:
    """A04 关系端点与关联实体：关系端点类型存在于引用中。"""
    resource_iris = {r.iri for r in resources}
    resource_iri_by_id = {res.id: res.iri for res in resources}
    for res in resources:
        if res.kind != ResourceKind.OBJECT_PROP:
            continue
        meta = res.definition_i18n or {}
        domain_iri = meta.get("domain_iri")
        range_iri = meta.get("range_iri")
        if isinstance(res, ResourceSnapshot):
            domain_iri, range_iri = relation_endpoints(res, resource_iri_by_id)
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
    """A05 规则集：钉扎规则存在、版本未漂移、DATA/DERIVATION 表达式可解析。

    本体未挂任何规则 → NA（无规则集可查，不是通过也不是未执行）。
    """
    refs = list(
        session.scalars(
            select(OntologyRuleRef).where(OntologyRuleRef.ontology_id == onto.id)
        )
    )
    if not refs:
        return ValidationResult(
            check_code="A05",
            state=ValidationState.NA,
            message="no rules defined",
        )
    changed: list[int] = []
    broken: list[dict] = []
    for ref in refs:
        rule = session.get(Rule, ref.rule_id)
        if rule is None:
            changed.append(ref.rule_id)
            continue
        if rule.revision != ref.pinned_revision:
            broken.append(
                {
                    "rule_id": rule.id,
                    "pinned": ref.pinned_revision,
                    "current": rule.revision,
                }
            )
            continue
        if rule.language in ("DATA", "DERIVATION"):
            try:
                config = json.loads(rule.expression)
            except ValueError:
                broken.append({"rule_id": rule.id, "reason": "invalid_json"})
                continue
            if not isinstance(config, dict) or not config.get("op"):
                broken.append({"rule_id": rule.id, "reason": "missing_op"})
    if changed or broken:
        return ValidationResult(
            check_code="A05",
            state=ValidationState.VIOLATION,
            detail={"missing_rules": changed, "broken_rules": broken},
            message="rule set inconsistent with pinned revisions",
        )
    return ValidationResult(check_code="A05", state=ValidationState.PASS)


def _check_a06_core_template(
    session: Session, onto: Ontology, referenced_ids: list[int]
) -> ValidationResult:
    """A06 核心模板：模板来源的本体必须保留模板成员资源且种类一致。

    非模板装配的本体 → NA（无模板契约可核对）。
    """
    if onto.template_id is None:
        return ValidationResult(
            check_code="A06",
            state=ValidationState.NA,
            message="ontology not instantiated from a template",
        )
    template = session.get(AssemblyTemplate, onto.template_id)
    if template is None:
        return ValidationResult(
            check_code="A06",
            state=ValidationState.VIOLATION,
            detail={"template_id": onto.template_id},
            message="template origin missing",
        )
    referenced = set(referenced_ids)
    missing: list[str] = []
    for member in template_resources(template):
        resource = session.get(ModelResource, member.resource_id)
        if resource is None:
            missing.append(f"resource:{member.resource_id}")
            continue
        if member.resource_id not in referenced:
            missing.append(resource.name)
    if missing:
        return ValidationResult(
            check_code="A06",
            state=ValidationState.VIOLATION,
            detail={"missing_members": missing},
            message="template core members not preserved in ontology",
        )
    return ValidationResult(check_code="A06", state=ValidationState.PASS)


def _check_a07_namespace(
    session: Session, resources: list[ValidationResource]
) -> ValidationResult:
    """A07 命名空间与核心包锁定：引用资源的命名空间已注册。"""
    for res in resources:
        if isinstance(res, ResourceSnapshot) and (
            not res.namespace.get("prefix") or not res.namespace.get("iri")
        ):
            return ValidationResult(
                check_code="A07",
                state=ValidationState.VIOLATION,
                detail={"resource_id": res.id},
                message="namespace missing from resource snapshot",
            )
    ns_ids = {r.namespace_id for r in resources if isinstance(r, ModelResource)}
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
    session: Session,
    onto: Ontology,
    backend: SemanticBackend | None,
) -> ValidationResult:
    """A08 OWL 一致性：owlrl OWL 2 RL 闭包真实执行。

    DL 完整推理仍超出范围，推理谱系如实写入 message；引擎缺失、
    本体未发布或导出失败按 NOT_RUN 处理，绝不显示成 PASS。
    """
    if onto.current_revision < 1:
        return ValidationResult(
            check_code="A08",
            state=ValidationState.NA,
            message="ontology not published",
        )
    if backend is None or not backend.has_full_reasoner():
        return ValidationResult(
            check_code="A08",
            state=ValidationState.NOT_RUN,
            message="consistency reasoner not available",
        )
    try:
        exported = ontology_export_service.export_ontology(
            session, onto.id, revision=onto.current_revision
        )
    except KGError as exc:
        return ValidationResult(
            check_code="A08",
            state=ValidationState.NOT_RUN,
            detail={"reason": "export_failed", "params": exc.params},
            message="ontology RDF export failed",
        )
    report = backend.check_consistency(exported.content)
    if report.state is ValidationState.NOT_RUN:
        return ValidationResult(
            check_code="A08",
            state=ValidationState.NOT_RUN,
            message=report.results_text,
        )
    conflicts = (report.raw or {}).get("errors") if isinstance(report.raw, dict) else []
    result = ValidationResult(
        check_code="A08",
        state=report.state,
        message="owlrl OWL 2 RL consistency check (full DL reasoning out of scope)",
    )
    if conflicts:
        result.detail = {"errors": conflicts[:10]}
    return result
