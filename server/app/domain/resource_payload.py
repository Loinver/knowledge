"""构造资源的完整语义载荷；只读取数据，不发布或提交。"""

from __future__ import annotations

from copy import deepcopy

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.enum_dictionary_service import get_snapshot
from app.models.enums import ResourceKind
from app.models.resource import (
    DatatypePropDetail,
    ModelResource,
    ObjectPropDetail,
    ResourceParent,
    ResourceRef,
)


def _property_snapshot(
    session: Session,
    prop: ModelResource,
    detail: DatatypePropDetail,
    role: str,
) -> dict[str, object]:
    return {
        "role": role,
        "name": detail.prop_name,
        "iri": prop.iri,
        "label_i18n": deepcopy(prop.label_i18n),
        "definition_i18n": deepcopy(prop.definition_i18n),
        "synonyms": deepcopy(prop.synonyms),
        "datatype": detail.datatype,
        "enum_dict_id": detail.enum_dict_id,
        "enum_dict_revision": detail.enum_dict_revision,
        "enum_dictionary": get_snapshot(
            session, detail.enum_dict_id, detail.enum_dict_revision
        )
        if detail.enum_dict_id is not None and detail.enum_dict_revision is not None
        else None,
        "nullable": detail.nullable,
        "default_value": detail.default_value,
        "min_cardinality": detail.min_cardinality,
        "max_cardinality": detail.max_cardinality,
        "min_value": detail.min_value,
        "max_value": detail.max_value,
        "source_clause_ref": detail.source_clause_ref,
    }


def build_resource_payload(
    session: Session,
    resource: ModelResource,
    owned_versions: dict[str, int] | None = None,
) -> dict:
    """工作草稿与资源发布复用同一字段投影。"""
    payload = {
        "name": resource.name,
        "iri": resource.iri,
        "kind": resource.kind.value,
        "label_i18n": deepcopy(resource.label_i18n),
        "definition_i18n": deepcopy(resource.definition_i18n),
        "synonyms": deepcopy(resource.synonyms),
        "namespace": {
            "prefix": resource.namespace.prefix,
            "iri": resource.namespace.iri,
        }
        if resource.namespace is not None
        else {},
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
        "owned_versions": owned_versions or {},
    }
    # 属性/关系约束一并冻结：否则发布版本拿不到 data type、基数与 OWL 特征，
    # 「不静默影响下游」就只剩端点引用一层（M-07 补齐）。
    # 属性明细挂在属性子资源上，按引用聚合；关系明细挂在关系资源自身上。
    prop_details: list[dict[str, object]] = []
    if resource.kind == ResourceKind.DATATYPE_PROP:
        own_detail = session.get(DatatypePropDetail, resource.id)
        if own_detail is not None:
            prop_details.append(
                _property_snapshot(session, resource, own_detail, "self")
            )
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
        if prop is not None:
            prop_details.append(_property_snapshot(session, prop, detail, ref.role))
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
    return payload
