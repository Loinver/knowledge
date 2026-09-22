"""资源状态机与修订号并发控制（H-01 / H-02）。"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.models.enums import ResourceStatus
from app.models.resource import (
    DatatypePropDetail,
    ModelResource,
    ObjectPropDetail,
    ResourceParent,
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


def publish_resource(session: Session, resource: ModelResource) -> ResourceRevision:
    """发布资源：冻结当前内容为不可变版本。

    resource_revision 只增不改；current_revision 前移。
    已发布状态的资源不能再次发布（需先改草稿再发新版本）。
    """
    if resource.status == ResourceStatus.PUBLISHED:
        raise KGError(ErrorCode.ALREADY_PUBLISHED, {"resource": resource.name})
    new_rev = resource.current_revision + 1
    payload = {
        "name": resource.name,
        "iri": resource.iri,
        "kind": resource.kind.value,
        "label_i18n": deepcopy(resource.label_i18n),
        "definition_i18n": deepcopy(resource.definition_i18n),
        "namespace": {
            "prefix": resource.namespace.prefix,
            "iri": resource.namespace.iri,
        },
        "parent_ids": list(
            session.scalars(
                select(ResourceParent.parent_id)
                .where(ResourceParent.child_id == resource.id)
                .order_by(ResourceParent.parent_id)
            )
        ),
        "resource_refs": [
            {"target_id": ref.target_id, "role": ref.role}
            for ref in session.scalars(
                select(ResourceRef)
                .where(ResourceRef.source_id == resource.id)
                .order_by(ResourceRef.role, ResourceRef.target_id)
            )
        ],
    }
    # 属性/关系约束一并冻结：否则发布版本拿不到 data type、基数与 OWL 特征，
    # 「不静默影响下游」就只剩端点引用一层（M-07 补齐）。
    # 属性明细挂在属性子资源上，按引用聚合；关系明细挂在关系资源自身上。
    prop_details: list[dict[str, object]] = []
    for ref in session.scalars(
        select(ResourceRef)
        .where(
            ResourceRef.source_id == resource.id,
            ResourceRef.role.in_(["data_prop", "assoc_attribute"]),
        )
        .order_by(ResourceRef.id)
    ):
        detail = session.get(DatatypePropDetail, ref.target_id)
        if detail is None:
            continue
        prop = session.get(ModelResource, ref.target_id)
        prop_details.append(
            {
                "role": ref.role,
                "name": detail.prop_name,
                "iri": prop.iri if prop is not None else None,
                "label_i18n": deepcopy(prop.label_i18n) if prop is not None else None,
                "datatype": detail.datatype,
                "enum_dict_id": detail.enum_dict_id,
                "nullable": detail.nullable,
                "default_value": detail.default_value,
            }
        )
    if prop_details:
        payload["datatype_props"] = prop_details

    object_detail = session.get(ObjectPropDetail, resource.id)
    if object_detail is not None:
        payload["object_prop"] = {
            "domain_cardinality": {
                "min": object_detail.domain_min,
                "max": object_detail.domain_max,
                "role_label_i18n": deepcopy(object_detail.domain_cardinality_role_i18n),
            },
            "range_cardinality": {
                "min": object_detail.range_min,
                "max": object_detail.range_max,
                "role_label_i18n": deepcopy(object_detail.range_cardinality_role_i18n),
            },
            "domain_role_i18n": deepcopy(object_detail.domain_role_i18n),
            "range_role_i18n": deepcopy(object_detail.range_role_i18n),
            "owl": deepcopy(object_detail.owl),
        }
    rev = ResourceRevision(
        resource_id=resource.id,
        revision=new_rev,
        payload=payload,
        checksum=_checksum(payload),
    )
    session.add(rev)
    resource.current_revision = new_rev
    resource.status = ResourceStatus.PUBLISHED
    session.flush()
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
