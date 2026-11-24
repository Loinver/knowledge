"""资源引用面与版本历史（实体类型 / 关系类型详情页共用）。

详情页的「规则命中 / 业务域归属 / 被引用的本体 / 版本历史 / 最近一次资产层校验」
这几块与资源到底是实体类型还是关系类型无关，抽到这里复用；类型专属的部分
（实体类型的「关联关系」页签）留在各自的领域服务里。

一次取全而不是每个页签发一串请求，避免详情页打开时的请求瀑布。
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.domain import (
    BusinessDomain,
    DomainMember,
    Ontology,
    OntologyResourceRef,
)
from app.models.governance import Rule
from app.models.resource import ModelResource, ResourceRevision
from app.models.validation import ValidationReport, ValidationResult


def resource_usages(session: Session, resource: ModelResource) -> dict[str, object]:
    """按资源（实体类型或关系类型）取引用面与版本历史。"""
    # ── 规则：按目标 IRI 命中 ──
    rules = [
        {
            "id": rule.id,
            "identifier": rule.identifier,
            "name_i18n": rule.name_i18n,
            "severity": rule.severity,
        }
        for rule in session.scalars(
            select(Rule)
            .where(Rule.target_iri == resource.iri)
            .order_by(Rule.identifier)
        )
    ]

    # ── 引用面：业务域归属 + 引用了它的本体 ──
    member_rows = session.execute(
        select(DomainMember, BusinessDomain)
        .join(BusinessDomain, BusinessDomain.id == DomainMember.domain_id)
        .where(DomainMember.resource_id == resource.id)
        .order_by(BusinessDomain.name)
    ).all()
    domains = [
        {
            "id": domain.id,
            "name": domain.name,
            "label_i18n": domain.label_i18n,
            "as_ref": member.as_ref,
        }
        for member, domain in member_rows
    ]

    ontology_rows = session.execute(
        select(Ontology)
        .join(OntologyResourceRef, OntologyResourceRef.ontology_id == Ontology.id)
        .where(OntologyResourceRef.resource_id == resource.id)
        .order_by(Ontology.name)
    ).scalars()
    ontologies = [
        {
            "id": item.id,
            "name": item.name,
            "label_i18n": item.label_i18n,
            "status": item.status,
            "current_revision": item.current_revision,
        }
        for item in ontology_rows
    ]

    # ── 版本历史 ──
    revisions = [
        {"revision": row.revision, "published_at": row.published_at}
        for row in session.scalars(
            select(ResourceRevision)
            .where(ResourceRevision.resource_id == resource.id)
            .order_by(ResourceRevision.revision.desc())
        )
    ]

    # ── 校验状态：最近一次资产层报告里焦点节点命中该资源的检查项 ──
    validations: list[dict[str, object]] = []
    latest = session.scalar(
        select(func.max(ValidationReport.id)).where(
            ValidationReport.scope == "ontology"
        )
    )
    if latest is not None:
        validations = [
            {
                "check_code": row.check_code,
                "state": row.state.value,
                "message": row.message,
            }
            for row in session.scalars(
                select(ValidationResult)
                .where(
                    ValidationResult.report_id == latest,
                    ValidationResult.focus_node == resource.iri,
                )
                .order_by(ValidationResult.check_code)
            )
        ]

    return {
        "rules": rules,
        "domains": domains,
        "ontologies": ontologies,
        "revisions": revisions,
        "validations": validations,
    }
