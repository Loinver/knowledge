"""业务域管理领域服务（H-10）。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.models.domain import BusinessDomain, DomainMember
from app.models.enums import ResourceStatus
from app.models.resource import ModelResource
from app.schemas.domain import (
    DomainCreate,
    DomainMemberAdd,
    DomainUpdate,
    PublishCheckResult,
)


def create_domain(session: Session, payload: DomainCreate) -> BusinessDomain:
    """创建业务域。name 唯一。"""
    existing = session.execute(
        select(BusinessDomain).where(BusinessDomain.name == payload.name)
    ).scalar_one_or_none()
    if existing is not None:
        raise KGError(
            ErrorCode.ALREADY_PUBLISHED,
            {"name": payload.name, "reason": "domain_name_taken"},
        )
    domain = BusinessDomain(
        name=payload.name,
        iri=payload.iri,
        label_i18n=payload.label_i18n,
        definition_i18n=payload.definition_i18n,
        status=ResourceStatus.DRAFT,
    )
    session.add(domain)
    session.flush()
    for rid in payload.member_ids:
        add_member(session, domain.id, DomainMemberAdd(resource_id=rid))
    session.flush()
    return domain


def add_member(
    session: Session, domain_id: int, payload: DomainMemberAdd
) -> DomainMember:
    """添加业务域成员。as_ref=True 表示跨域引用，按 IRI 去重。"""
    resource = session.get(ModelResource, payload.resource_id)
    if resource is None:
        raise KGError(
            ErrorCode.RESOURCE_NOT_FOUND, {"resource_id": payload.resource_id}
        )
    existing = session.execute(
        select(DomainMember).where(
            DomainMember.domain_id == domain_id,
            DomainMember.resource_id == payload.resource_id,
            DomainMember.as_ref == payload.as_ref,
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise KGError(
            ErrorCode.ALREADY_PUBLISHED,
            {"resource_id": payload.resource_id, "reason": "member_exists"},
        )
    member = DomainMember(
        domain_id=domain_id,
        resource_id=payload.resource_id,
        as_ref=payload.as_ref,
        owner_domain_id=payload.owner_domain_id,
    )
    session.add(member)
    session.flush()
    return member


def remove_member(session: Session, domain_id: int, member_id: int) -> None:
    member = session.get(DomainMember, member_id)
    if member is None or member.domain_id != domain_id:
        raise KGError(ErrorCode.RESOURCE_NOT_FOUND, {"member_id": member_id})
    session.delete(member)
    session.flush()


def list_members(session: Session, domain_id: int) -> list[DomainMember]:
    return list(
        session.execute(
            select(DomainMember).where(DomainMember.domain_id == domain_id)
        ).scalars()
    )


def get_domain(session: Session, domain_id: int) -> BusinessDomain:
    domain = session.get(BusinessDomain, domain_id)
    if domain is None:
        raise KGError(ErrorCode.RESOURCE_NOT_FOUND, {"domain_id": domain_id})
    return domain


def list_domains(
    session: Session, q: str = "", page: int = 1, page_size: int = 50
) -> tuple[list[BusinessDomain], int]:
    stmt = select(BusinessDomain)
    if q:
        stmt = stmt.where(BusinessDomain.name.ilike(f"%{q}%"))
    count_stmt = select(BusinessDomain)
    if q:
        count_stmt = count_stmt.where(BusinessDomain.name.ilike(f"%{q}%"))
    total = len(list(session.execute(count_stmt).scalars()))
    stmt = (
        stmt.order_by(BusinessDomain.name)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = list(session.execute(stmt).scalars())
    return items, total


def update_domain(
    session: Session, domain: BusinessDomain, payload: DomainUpdate
) -> BusinessDomain:
    """更新业务域（草稿态）。带 If-Match 乐观锁。"""
    if domain.current_revision != payload.if_match:
        raise KGError(
            ErrorCode.REVISION_CONFLICT,
            {
                "domain": domain.name,
                "expected": domain.current_revision,
                "actual": payload.if_match,
            },
        )
    if payload.label_i18n is not None:
        domain.label_i18n = payload.label_i18n
    if payload.definition_i18n is not None:
        domain.definition_i18n = payload.definition_i18n
    session.flush()
    return domain


def check_publish(session: Session, domain: BusinessDomain) -> PublishCheckResult:
    """发布前四项检查：成员存在/版本可用/依赖完整/循环引用。"""
    members = list_members(session, domain.id)
    issues: list[str] = []

    member_exists = True
    versions_available = True
    for m in members:
        res = session.get(ModelResource, m.resource_id)
        if res is None:
            member_exists = False
            issues.append(f"member {m.resource_id} not found")
        elif res.status != ResourceStatus.PUBLISHED:
            versions_available = False
            issues.append(f"member {m.resource_id} not published")

    dependencies_complete = member_exists and versions_available

    no_circular_ref = not _has_circular_ref(session, domain.id, domain.id, set())
    if not no_circular_ref:
        issues.append("circular cross-domain reference detected")

    can_publish = (
        member_exists
        and versions_available
        and dependencies_complete
        and no_circular_ref
    )
    return PublishCheckResult(
        member_exists=member_exists,
        versions_available=versions_available,
        dependencies_complete=dependencies_complete,
        no_circular_ref=no_circular_ref,
        can_publish=can_publish,
        issues=issues,
    )


def _has_circular_ref(
    session: Session, start: int, current: int, visited: set[int]
) -> bool:
    """检测跨域引用是否成环。"""
    if current in visited:
        return True
    visited.add(current)
    members = (
        session.execute(select(DomainMember).where(DomainMember.domain_id == current))
        .scalars()
        .all()
    )
    for m in members:
        if (
            m.owner_domain_id is not None
            and m.owner_domain_id != start
            and _has_circular_ref(session, start, m.owner_domain_id, visited)
        ):
            return True
    visited.discard(current)
    return False


def publish_domain(session: Session, domain: BusinessDomain) -> int:
    """发布业务域：冻结不可变版本。发布前必须通过四项检查。"""
    check = check_publish(session, domain)
    if not check.can_publish:
        raise KGError(
            ErrorCode.VALIDATION_VIOLATION,
            {"domain": domain.name, "issues": check.issues},
        )

    from app.models.domain import DomainRevision

    new_rev = domain.current_revision + 1
    members = list_members(session, domain.id)
    payload = {
        "name": domain.name,
        "iri": domain.iri,
        "label_i18n": domain.label_i18n,
        "members": [
            {"resource_id": m.resource_id, "as_ref": m.as_ref} for m in members
        ],
    }
    rev = DomainRevision(
        domain_id=domain.id,
        revision=new_rev,
        payload=payload,
    )
    session.add(rev)
    domain.current_revision = new_rev
    domain.status = ResourceStatus.PUBLISHED
    session.flush()
    return new_rev
