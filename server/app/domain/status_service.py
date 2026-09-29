"""资源状态机与修订号并发控制（H-01 / H-02）。"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.domain.enum_dictionary_service import get_snapshot
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


def publish_resource(session: Session, resource: ModelResource) -> ResourceRevision:
    """发布资源：冻结当前内容为不可变版本。

    resource_revision 只增不改；current_revision 前移。
    已发布状态的资源不能再次发布（需先改草稿再发新版本）。
    并发双发布：用带 status 条件的原子 UPDATE 抢占发布权，输家拿到
    409 ALREADY_PUBLISHED，而不是双双通过后撞 (resource_id, revision)
    唯一约束变成 503。
    """
    claimed = session.scalar(
        update(ModelResource)
        .where(
            ModelResource.id == resource.id,
            ModelResource.status == ResourceStatus.DRAFT,
        )
        .values(edit_revision=ModelResource.edit_revision + 1)
        .returning(ModelResource)
        .execution_options(populate_existing=True)
    )
    if claimed is None:
        session.refresh(resource)
        raise KGError(ErrorCode.ALREADY_PUBLISHED, {"resource": resource.name})
    resource = claimed
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
    property_owners = [
        resource.id,
        *session.scalars(
            select(ResourceRef.target_id).where(
                ResourceRef.source_id == resource.id,
                ResourceRef.role == "assoc_resource",
            )
        ),
    ]
    for ref in session.scalars(
        select(ResourceRef)
        .where(
            ResourceRef.source_id.in_(property_owners),
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
                "enum_dict_revision": detail.enum_dict_revision,
                "enum_dictionary": get_snapshot(
                    session, detail.enum_dict_id, detail.enum_dict_revision
                )
                if detail.enum_dict_id is not None
                and detail.enum_dict_revision is not None
                else None,
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
    # edit_revision 已在抢占发布的原子 UPDATE 里递增，使在途编辑令牌全部失效。
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
