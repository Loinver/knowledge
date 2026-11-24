"""固定输入的资产层校验：工作草稿与历史版本分别出具四态证据。"""

from __future__ import annotations

import json

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.domain.ontology_export_service import validate_resource_references
from app.domain.ontology_snapshot import ResourceSnapshot, relation_endpoints
from app.domain.ontology_validation_context import (
    OntologyValidationContext,
    frozen_context,
    working_context,
)
from app.models.domain import Ontology, OntologyRevision
from app.models.enums import ResourceKind, ResourceStatus, ValidationState
from app.models.resource import ModelResource, Namespace
from app.models.validation import ValidationReport, ValidationResult
from app.schemas.ontology import OntologyExportFormat
from app.schemas.type import DataTypePropCreate
from app.schemas.validation import OntologyValidationTarget
from app.semantics.backend import SemanticBackend
from app.semantics.ontology_rdf import (
    OntologyRdfMetadata,
    OntologyRdfResource,
    serialize_ontology_rdf,
)
from app.semantics.ontology_validation import check_ontology_consistency

type ValidationResource = ModelResource | ResourceSnapshot


def get_validation_report(session: Session, report_id: int) -> ValidationReport:
    report = session.get(ValidationReport, report_id)
    if report is None:
        raise KGError(ErrorCode.RESOURCE_NOT_FOUND, {"report_id": report_id})
    return report


def run_ontology_validation(
    session: Session,
    ontology_id: int,
    *,
    backend: SemanticBackend | None = None,
    target: OntologyValidationTarget | None = None,
    revision: int | None = None,
) -> ValidationReport:
    """旧领域调用缺省检查发布版；HTTP明确指定WORKING，不再以status推断。"""
    onto = session.get(Ontology, ontology_id, populate_existing=True)
    if onto is None:
        raise KGError(ErrorCode.RESOURCE_NOT_FOUND, {"ontology_id": ontology_id})
    target = target or (
        OntologyValidationTarget.PUBLISHED
        if onto.status == ResourceStatus.PUBLISHED
        else OntologyValidationTarget.WORKING
    )
    if target == OntologyValidationTarget.PUBLISHED:
        pin = onto.current_revision if revision is None else revision
        published = session.scalar(
            select(OntologyRevision).where(
                OntologyRevision.ontology_id == ontology_id,
                OntologyRevision.revision == pin,
            )
        )
        if published is None:
            raise KGError(
                ErrorCode.REVISION_NOT_FOUND,
                {"ontology_id": ontology_id, "revision": pin},
            )
        context = frozen_context(session, onto, published)
    else:
        if revision is not None:
            raise KGError(
                ErrorCode.INVALID_REQUEST, {"reason": "working_revision_parameter"}
            )
        context = working_context(session, onto)
    return validate_context(session, context, backend=backend)


def validate_context(
    session: Session,
    context: OntologyValidationContext,
    *,
    backend: SemanticBackend | None = None,
    local_reasoner: bool = False,
) -> ValidationReport:
    resources: list[ValidationResource] = list(context.resources())
    checks = [
        _check_a01_closure(resources, context.referenced_ids),
        _check_a02_type_metadata(session, resources),
        _check_a03_property_range(session, resources),
        _check_a04_relation_endpoints(session, resources),
        _check_a05_rule_set(context),
        _check_a06_core_template(context),
        _check_a07_namespace(session, resources),
        _check_a08_owl_consistency(context, backend, local_reasoner=local_reasoner),
    ]
    summary = {
        "pass": sum(c.state == ValidationState.PASS for c in checks),
        "violation": sum(c.state == ValidationState.VIOLATION for c in checks),
        "na": sum(c.state == ValidationState.NA for c in checks),
        "not_run": sum(c.state == ValidationState.NOT_RUN for c in checks),
    }
    report = ValidationReport(
        scope="ontology",
        target_id=context.ontology_id,
        target_revision=context.published_revision,
        summary=summary,
        binding=context.binding(),
    )
    session.add(report)
    session.flush()
    for check in checks:
        check.report_id = report.id
        session.add(check)
    session.flush()
    return report


def require_publishable_report(report: ValidationReport) -> None:
    rejected = [
        {"check_code": item.check_code, "state": item.state.value}
        for item in report.results
        if item.state in {ValidationState.VIOLATION, ValidationState.NOT_RUN}
    ]
    if rejected:
        raise KGError(
            ErrorCode.VALIDATION_VIOLATION,
            {"reason": "publication_checks_failed", "checks": rejected},
        )


def _check_a01_closure(
    resources: list[ValidationResource], referenced_ids: list[int]
) -> ValidationResult:
    """A01 资源闭包：引用的资源全部存在。"""
    res_ids = {res.id for res in resources}
    required_ids = set(referenced_ids)
    for resource in resources:
        if isinstance(resource, ResourceSnapshot):
            required_ids.update(resource.parent_ids)
            required_ids.update(ref.target_id for ref in resource.resource_refs)
    missing = sorted(required_ids - res_ids)
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
        if not (res.label_i18n or {}).get("zh-CN", "").strip():
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
    valid_types = {"string", "integer", "decimal", "boolean", "date", "enum", "anyURI"}
    for res in resources:
        if isinstance(res, ResourceSnapshot):
            for prop in res.datatype_props:
                try:
                    DataTypePropCreate.model_validate(prop.model_dump())
                except ValidationError as exc:
                    return ValidationResult(
                        check_code="A03",
                        state=ValidationState.VIOLATION,
                        focus_node=res.iri,
                        detail={
                            "resource": prop.name,
                            "issues": [
                                {"field": list(item["loc"]), "type": item["type"]}
                                for item in exc.errors()
                            ],
                        },
                        message="invalid property definition",
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


def _check_a05_rule_set(context: OntologyValidationContext) -> ValidationResult:
    if not context.rules:
        return ValidationResult(
            check_code="A05", state=ValidationState.NA, message="no rules defined"
        )
    broken = []
    for record in context.rules:
        rule = record.get("snapshot")
        if not isinstance(rule, dict) or rule.get("revision") != record.get("revision"):
            broken.append(
                {
                    "rule_id": record.get("rule_id"),
                    "reason": "missing_or_mismatched_rule_snapshot",
                }
            )
            continue
        if rule.get("language") in {"DATA", "DERIVATION"}:
            try:
                config = json.loads(rule.get("expression", ""))
            except (ValueError, TypeError):
                config = None
            if not isinstance(config, dict) or not config.get("op"):
                broken.append(
                    {
                        "rule_id": record.get("rule_id"),
                        "reason": "invalid_rule_expression",
                    }
                )
    if broken:
        return ValidationResult(
            check_code="A05",
            state=ValidationState.VIOLATION,
            detail={"broken_rules": broken},
            message="invalid fixed rule set",
        )
    return ValidationResult(check_code="A05", state=ValidationState.PASS)


def _check_a06_core_template(context: OntologyValidationContext) -> ValidationResult:
    template = context.template
    if template is None:
        return ValidationResult(
            check_code="A06",
            state=ValidationState.NOT_RUN,
            message="historical template snapshot unavailable",
        )
    if template.get("template_id") is None:
        return ValidationResult(
            check_code="A06",
            state=ValidationState.NA,
            message="ontology not instantiated from a template",
        )
    missing = [
        member["resource_id"]
        for member in template.get("resources", [])
        if member["resource_id"] not in context.payloads
    ]
    # Updating a template must not silently repin an existing assembly. A01 and
    # A08 validate the actual frozen versions selected by the ontology.
    if missing:
        return ValidationResult(
            check_code="A06",
            state=ValidationState.VIOLATION,
            detail={"missing_members": missing},
            message="template core members not preserved in ontology",
        )
    return ValidationResult(check_code="A06", state=ValidationState.PASS)


def _check_a08_owl_consistency(
    context: OntologyValidationContext,
    backend: SemanticBackend | None,
    *,
    local_reasoner: bool,
) -> ValidationResult:
    if (backend is None and not local_reasoner) or (
        backend is not None and not backend.has_full_reasoner()
    ):
        return ValidationResult(
            check_code="A08",
            state=ValidationState.NOT_RUN,
            message="consistency reasoner not available",
        )
    try:
        resources = {
            rid: OntologyRdfResource.model_validate(payload)
            for rid, payload in context.payloads.items()
        }
        for rid, resource in resources.items():
            validate_resource_references(rid, resource, resources)
        content = serialize_ontology_rdf(
            OntologyRdfMetadata.model_validate(context.metadata),
            resources,
            revision=context.published_revision,
            rdf_format=OntologyExportFormat.TURTLE,
            rules=context.rules,
        )
        result = check_ontology_consistency(content, backend)
    except KGError as exc:
        return ValidationResult(
            check_code="A08",
            state=ValidationState.VIOLATION,
            detail={"reason": "invalid_semantic_snapshot", "params": exc.params},
            message="ontology RDF compilation failed",
        )
    except (ValidationError, ValueError, NotImplementedError) as exc:
        return ValidationResult(
            check_code="A08",
            state=ValidationState.NOT_RUN,
            detail={"reason": type(exc).__name__},
            message="ontology consistency check unavailable",
        )
    detail = {
        "engine": "OWL2_RL",
        "scope": "ontology_graph",
        "errors": (result.raw or {}).get("errors", [])[:10]
        if isinstance(result.raw, dict)
        else [],
    }
    return ValidationResult(
        check_code="A08", state=result.state, detail=detail, message=result.results_text
    )
