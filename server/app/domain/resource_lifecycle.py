"""资源级生命周期扩展：撤回发布与草稿删除（实体类型/关系类型共用）。

撤回发布让已发布资源回到 DRAFT，可继续编辑后再发布为新版本；
ResourceRevision 历史保持不可变，已冻结的本体/证据引用不受影响——
这补上了「已发布类型无法演进」的生命周期断点。

草稿删除只接受从未发布过的资源（current_revision == 0）：发布过就有
版本历史，证据与快照可能按 id 钉住它，不能物理删除。删除会连带清理
子资源（DATATYPE_PROP 属性、ASSOC 伴生资源）及其约束明细；外部引用
（业务域成员、本体引用、规则 IRI、其它资源指向它的端点/特征引用、
层级子节点）一律拒绝。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.orm import Session

from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.models.domain import DomainMember, OntologyResourceRef
from app.models.enums import ResourceStatus
from app.models.governance import Rule
from app.models.resource import (
    DatatypePropDetail,
    ModelResource,
    ObjectPropDetail,
    ResourceParent,
    ResourceRef,
    ResourceRevision,
)

# 资源 → 子资源的挂载角色；子资源自己的属性再挂一层 assoc_attribute。
_SUB_ROLES = ("data_prop", "assoc_resource")
_SUBSUB_ROLES = ("assoc_attribute",)


def unpublish_resource(session: Session, resource: ModelResource) -> ModelResource:
    """撤回发布：PUBLISHED → DRAFT。

    只有 PUBLISHED 状态可以撤回；撤回时递增 edit_revision，
    让发布前发出的编辑令牌全部失效。
    """
    updated = session.scalar(
        update(ModelResource)
        .where(
            ModelResource.id == resource.id,
            ModelResource.status == ResourceStatus.PUBLISHED,
        )
        .values(
            status=ResourceStatus.DRAFT,
            edit_revision=ModelResource.edit_revision + 1,
        )
        .returning(ModelResource)
        .execution_options(populate_existing=True)
    )
    if updated is None:
        session.refresh(resource)
        raise KGError(
            ErrorCode.INVALID_REQUEST,
            {"resource": resource.name, "reason": "unpublish_requires_published"},
        )
    return updated


def delete_resource(session: Session, resource: ModelResource) -> None:
    """删除从未发布过的草稿资源，连同其子资源与约束明细。"""
    if resource.status != ResourceStatus.DRAFT or resource.current_revision != 0:
        raise KGError(
            ErrorCode.ALREADY_PUBLISHED,
            {"resource": resource.name, "reason": "delete_requires_fresh_draft"},
        )
    _ensure_unreferenced(session, resource)
    _cleanup(session, resource)
    session.flush()


def _ensure_unreferenced(session: Session, resource: ModelResource) -> None:
    """有外部引用就拒绝删除，引用计数进 RESOURCE_IN_USE 供界面提示。"""

    def _count(stmt: Any) -> int:
        return session.scalar(select(func.count()).select_from(stmt.subquery())) or 0

    blockers = (
        _count(select(DomainMember).where(DomainMember.resource_id == resource.id))
        + _count(
            select(OntologyResourceRef).where(
                OntologyResourceRef.resource_id == resource.id
            )
        )
        # 规则按 IRI 引用资源（rename 会同步 target_iri），也是引用面。
        + _count(select(Rule).where(Rule.target_iri == resource.iri))
        + _count(
            select(ResourceRef).where(
                ResourceRef.target_id == resource.id,
                ResourceRef.source_id != resource.id,
            )
        )
        + _count(select(ResourceParent).where(ResourceParent.parent_id == resource.id))
    )
    if blockers:
        raise KGError(
            ErrorCode.RESOURCE_IN_USE,
            {
                "resource_id": resource.id,
                "count": blockers,
                "reason": "resource_in_use",
            },
        )


def _cleanup(session: Session, resource: ModelResource) -> None:
    """先删孙辈（ASSOC 的属性）、再删子辈、最后删自身，保持外键方向。"""
    child_ids = list(
        session.scalars(
            select(ResourceRef.target_id).where(
                ResourceRef.source_id == resource.id,
                ResourceRef.role.in_(_SUB_ROLES),
            )
        )
    )
    grandchild_ids: list[int] = []
    if child_ids:
        grandchild_ids = list(
            session.scalars(
                select(ResourceRef.target_id).where(
                    ResourceRef.source_id.in_(child_ids),
                    ResourceRef.role.in_(_SUBSUB_ROLES),
                )
            )
        )
    for ids in (grandchild_ids, child_ids):
        if not ids:
            continue
        session.execute(
            delete(DatatypePropDetail).where(DatatypePropDetail.resource_id.in_(ids))
        )
        session.execute(delete(ResourceRef).where(ResourceRef.source_id.in_(ids)))
        session.execute(
            delete(ResourceRevision).where(ResourceRevision.resource_id.in_(ids))
        )
        session.execute(delete(ModelResource).where(ModelResource.id.in_(ids)))
    session.execute(
        delete(ObjectPropDetail).where(ObjectPropDetail.resource_id == resource.id)
    )
    session.execute(
        delete(ResourceRef).where(
            or_(
                ResourceRef.source_id == resource.id,
                ResourceRef.target_id == resource.id,
            )
        )
    )
    session.execute(
        delete(ResourceParent).where(
            or_(
                ResourceParent.child_id == resource.id,
                ResourceParent.parent_id == resource.id,
            )
        )
    )
    session.execute(
        delete(ResourceRevision).where(ResourceRevision.resource_id == resource.id)
    )
    session.execute(delete(ModelResource).where(ModelResource.id == resource.id))
