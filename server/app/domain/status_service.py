"""资源状态机与修订号并发控制（H-01 / H-02）。"""

from __future__ import annotations

import hashlib
import json

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.domain.resource_payload import build_resource_payload
from app.models.enums import ResourceKind, ResourceStatus
from app.models.resource import (
    ModelResource,
    ResourceRef,
    ResourceRevision,
)


def _checksum(payload: dict) -> str:
    """计算 payload 的稳定校验和，用于版本完整性。"""
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
    return hashlib.sha256(raw).hexdigest()


def check_revision(resource: ModelResource, if_match: int | None) -> None:
    """乐观锁校验：写接口必须带 If-Match，匹配失败返回 409。

    禁止"后打开的页面静默覆盖先写入的更新"。
    """
    if if_match is None:
        raise KGError(ErrorCode.INVALID_REQUEST, {"reason": "if_match_required"})
    if if_match != resource.current_revision:
        raise KGError(
            ErrorCode.REVISION_CONFLICT,
            {
                "resource": resource.name,
                "expected": resource.current_revision,
                "actual": if_match,
            },
        )


def lock_resource_edit(
    session: Session, resource: ModelResource, if_match: int, edit_revision: int | None
) -> ModelResource:
    """草稿修订号与发布版本分离；旧调用方仅能编辑尚未被修改的草稿。"""
    expected_edit = 0 if edit_revision is None else edit_revision
    locked = session.scalar(
        update(ModelResource)
        .where(
            ModelResource.id == resource.id,
            ModelResource.status == ResourceStatus.DRAFT,
            ModelResource.current_revision == if_match,
            ModelResource.edit_revision == expected_edit,
        )
        .values(edit_revision=ModelResource.edit_revision + 1)
        .returning(ModelResource)
        .execution_options(populate_existing=True)
    )
    if locked is None:
        session.refresh(resource)
        if resource.status != ResourceStatus.DRAFT:
            raise KGError(ErrorCode.ALREADY_PUBLISHED, {"resource": resource.name})
        raise KGError(
            ErrorCode.REVISION_CONFLICT,
            {
                "expected": expected_edit,
                "actual": resource.edit_revision,
                "resource": resource.name,
            },
        )
    return locked


def publish_resource(
    session: Session,
    resource: ModelResource,
    *,
    _owned: bool = False,
    _ancestors: frozenset[int] = frozenset(),
    _frozen_owned: dict[int, ResourceRevision] | None = None,
) -> ResourceRevision:
    """发布资源：冻结当前内容为不可变版本。

    resource_revision 只增不改；current_revision 前移。
    已发布状态的资源不能再次发布（需先改草稿再发新版本）。
    并发双发布：用带 status 条件的原子 UPDATE 抢占发布权，输家拿到
    409 ALREADY_PUBLISHED，而不是双双通过后撞 (resource_id, revision)
    唯一约束变成 503。
    """
    if resource.id in _ancestors:
        raise KGError(ErrorCode.VALIDATION_VIOLATION, {"reason": "ownership_cycle"})
    frozen_owned = {} if _frozen_owned is None else _frozen_owned
    if _owned and resource.id in frozen_owned:
        return frozen_owned[resource.id]
    claimed = session.scalar(
        update(ModelResource)
        .where(
            ModelResource.id == resource.id,
            ModelResource.status.in_([ResourceStatus.DRAFT, ResourceStatus.PUBLISHED])
            if _owned
            else ModelResource.status == ResourceStatus.DRAFT,
        )
        .values(edit_revision=ModelResource.edit_revision + 1)
        .returning(ModelResource)
        .execution_options(populate_existing=True)
    )
    if claimed is None:
        session.refresh(resource)
        raise KGError(ErrorCode.ALREADY_PUBLISHED, {"resource": resource.name})
    resource = claimed
    owned_versions: dict[str, int] = {}
    for ref in session.scalars(
        select(ResourceRef)
        .where(
            ResourceRef.source_id == resource.id,
            ResourceRef.role.in_(["data_prop", "assoc_attribute", "assoc_resource"]),
        )
        .order_by(ResourceRef.target_id)
    ):
        child = session.get(ModelResource, ref.target_id)
        expected = (
            ResourceKind.ASSOC
            if ref.role == "assoc_resource"
            else ResourceKind.DATATYPE_PROP
        )
        if child is None or child.kind != expected:
            raise KGError(
                ErrorCode.VALIDATION_VIOLATION,
                {
                    "reason": "invalid_owned_resource",
                    "resource_id": ref.target_id,
                },
            )
        frozen_child = publish_resource(
            session,
            child,
            _owned=True,
            _ancestors=_ancestors | {resource.id},
            _frozen_owned=frozen_owned,
        )
        owned_versions[str(child.id)] = frozen_child.revision
    new_rev = resource.current_revision + 1
    payload = build_resource_payload(session, resource, owned_versions)
    checksum = _checksum(payload)
    if _owned and resource.current_revision > 0:
        previous = get_revision(session, resource.id, resource.current_revision)
        if previous.checksum == checksum and previous.payload == payload:
            resource.status = ResourceStatus.PUBLISHED
            session.flush()
            frozen_owned[resource.id] = previous
            return previous
    rev = ResourceRevision(
        resource_id=resource.id,
        revision=new_rev,
        payload=payload,
        checksum=checksum,
    )
    session.add(rev)
    resource.current_revision = new_rev
    # edit_revision 已在抢占发布的原子 UPDATE 里递增，使在途编辑令牌全部失效。
    resource.status = ResourceStatus.PUBLISHED
    session.flush()
    frozen_owned[resource.id] = rev
    return rev


def get_revision(session: Session, resource_id: int, revision: int) -> ResourceRevision:
    """取不可变版本。不存在抛 404。"""
    rev = session.execute(
        select(ResourceRevision).where(
            ResourceRevision.resource_id == resource_id,
            ResourceRevision.revision == revision,
        )
    ).scalar_one_or_none()
    if rev is None:
        raise KGError(
            ErrorCode.REVISION_NOT_FOUND,
            {"resource_id": resource_id, "revision": revision},
        )
    return rev
