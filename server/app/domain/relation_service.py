"""关系类型库领域服务（H-12）。

关系是对象属性（OBJECT_PROP kind）。核心职责：
1. 定义域/值域引用实体类型，按 IRI 去重，可跨业务域。
2. 基数注明约束方向（domain/range 各持一份 CardinalitySpec）。
3. OWL 特征兼容性校验（对称+传递不兼容某些组合等）。
4. 启用关系属性时生成关联实体（ASSOC），端点通过 ResourceRef.role 标注，
   关系属性不塞进三元组——这是 A06（同一对实体两次业务关系分别保存）的前提。

分层纪律：本模块只写业务规则编排，不 import FastAPI，不感知 HTTP。
"""

from __future__ import annotations

from typing import Literal, TypedDict

from pydantic import ValidationError
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.domain.iri_service import build_resource_iri, validate_name
from app.domain.status_service import lock_resource_edit, publish_resource
from app.domain.type_service import set_data_props
from app.models.enums import ResourceKind, ResourceStatus
from app.models.resource import (
    DatatypePropDetail,
    ModelResource,
    Namespace,
    ObjectPropDetail,
    ResourceRef,
)
from app.schemas.relation import (
    AttributeDefOut,
    CardinalitySpec,
    EndpointSpec,
    OwlFeatures,
    RelationTypeCreate,
    RelationTypeUpdate,
)
from app.schemas.type import DataTypePropCreate

# ---------------------------------------------------------------------------
# OWL 特征兼容性校验
# ---------------------------------------------------------------------------


def validate_owl_compatibility(owl: OwlFeatures) -> None:
    """OWL 关系特征兼容性校验。

    不兼容组合返回 KG.VALIDATION_VIOLATION（422）。规则依据 OWL-DL 语义：
    - symmetric + functional 不兼容：对称关系意味着两端互为对象，
      functional 要求每个主体最多一个值，两者同时成立只可能是空关系或单元素自环，
      OWL-DL 推理器会报不一致。
    - symmetric + inverse_functional 同理不兼容（对称性的对偶矛盾）。
    - transitive + functional 不兼容：传递闭包会让 functional 约束失效
     （A->B, B->C 传递出 A->C，但 functional 要求 A 只有一个值）。
    - transitive + inverse_functional 不兼容（对偶同理）。
    """
    violations: list[str] = []
    if owl.symmetric and owl.functional:
        violations.append("symmetric+functional")
    if owl.symmetric and owl.inverse_functional:
        violations.append("symmetric+inverse_functional")
    if owl.transitive and owl.functional:
        violations.append("transitive+functional")
    if owl.transitive and owl.inverse_functional:
        violations.append("transitive+inverse_functional")
    if violations:
        raise KGError(
            ErrorCode.VALIDATION_VIOLATION,
            {"owl_conflicts": violations, "reason": "incompatible_owl_features"},
        )


# ---------------------------------------------------------------------------
# 关系类型 CRUD
# ---------------------------------------------------------------------------


def create_relation_type(
    session: Session, payload: RelationTypeCreate
) -> ModelResource:
    """创建关系类型。

    1. 校验 name 合法性与唯一性。
    2. 校验 domain/range 端点引用的实体类型存在。
    3. 校验 OWL 特征兼容性。
    4. 校验 inverse_of 指向的是 OBJECT_PROP。
    5. enable_attributes=True 时生成 ASSOC 资源承载属性清单。
    6. 端点通过 ResourceRef（role=relation_domain/relation_range）关联。
    """
    validate_name(payload.name)
    validate_owl_compatibility(payload.owl)

    namespace = session.get(Namespace, payload.namespace_id)
    if namespace is None:
        raise KGError(
            ErrorCode.RESOURCE_NOT_FOUND,
            {"namespace_id": payload.namespace_id},
        )

    iri = build_resource_iri(namespace, payload.name)
    _ensure_name_unique(session, payload.name)

    # 校验端点引用的实体类型存在
    domain_type = _get_entity_type(session, payload.domain_spec.type_id)
    range_type = _get_entity_type(session, payload.range_spec.type_id)

    # 校验端点去重（按 IRI）：domain 与 range 不能指向同一类型除非显式自环
    # 这里不禁止自环（Employee 管理 Employee 合法），但记录用于后续语义校验。

    # 校验 inverse_of
    if payload.inverse_of is not None:
        inverse = session.get(ModelResource, payload.inverse_of)
        if inverse is None or inverse.kind != ResourceKind.OBJECT_PROP:
            raise KGError(
                ErrorCode.VALIDATION_VIOLATION,
                {"inverse_of": payload.inverse_of, "reason": "not_a_relation"},
            )

    resource = ModelResource(
        kind=ResourceKind.OBJECT_PROP,
        name=payload.name,
        iri=iri,
        namespace_id=namespace.id,
        label_i18n=payload.label_i18n,
        definition_i18n=payload.definition_i18n,
        status=ResourceStatus.DRAFT,
    )
    session.add(resource)
    session.flush()

    # 关联实体模式：生成 ASSOC 资源承载属性
    assoc_resource: ModelResource | None = None
    if payload.enable_attributes:
        assoc_resource = _create_assoc_resource(
            session, namespace, resource, payload.attribute_defs
        )

    # 存关系元数据到 resource 的 payload 风格——M1 用 ResourceRef 关联端点
    _set_endpoints(
        session,
        resource,
        payload.domain_spec,
        payload.range_spec,
        domain_type,
        range_type,
    )
    _set_owl_and_meta(session, resource, payload.owl, payload, assoc_resource)
    session.flush()
    return resource


def _ensure_name_unique(session: Session, name: str) -> None:
    existing = session.execute(
        select(ModelResource).where(ModelResource.name == name)
    ).scalar_one_or_none()
    if existing is not None:
        raise KGError(
            ErrorCode.ALREADY_PUBLISHED,
            {"name": name, "reason": "name_taken"},
        )


def _get_entity_type(session: Session, type_id: int) -> ModelResource:
    """取实体类型，不存在或非 ENTITY 抛错。"""
    res = session.get(ModelResource, type_id)
    if res is None or res.kind != ResourceKind.ENTITY:
        raise KGError(
            ErrorCode.RESOURCE_NOT_FOUND,
            {"type_id": type_id, "reason": "not_an_entity_type"},
        )
    return res


def _create_assoc_resource(
    session: Session,
    namespace: Namespace,
    relation: ModelResource,
    attribute_defs: list[dict[str, object]],
) -> ModelResource:
    """生成关联实体（ASSOC kind）承载关系属性。

    关系属性不塞进三元组：ASSOC 资源是独立的 ModelResource，
    端点通过 ResourceRef.role 标注角色，M3 抽取时为每条业务关系
    生成一个 ASSOC 实例而非三元组——这是 A06 的前提。
    """
    assoc_name = f"{relation.name}Association"
    assoc_iri = build_resource_iri(namespace, assoc_name)
    # ASSOC 名也要唯一
    _ensure_name_unique(session, assoc_name)
    assoc = ModelResource(
        kind=ResourceKind.ASSOC,
        name=assoc_name,
        iri=assoc_iri,
        namespace_id=namespace.id,
        label_i18n=relation.label_i18n,
        definition_i18n={
            "zh-CN": f"{relation.name} 的关联实体",
            "en-US": f"{relation.name} association",
        },
        status=ResourceStatus.DRAFT,
    )
    session.add(assoc)
    session.flush()
    # 关系 -> ASSOC：role=assoc_resource
    session.add(
        ResourceRef(source_id=relation.id, target_id=assoc.id, role="assoc_resource")
    )
    set_data_props(session, assoc, _attribute_inputs(attribute_defs), "assoc_attribute")
    return assoc


def _attribute_inputs(
    attribute_defs: list[dict[str, object]],
) -> list[DataTypePropCreate]:
    try:
        return [
            DataTypePropCreate.model_validate({"datatype": "string", **attr})
            for attr in attribute_defs
        ]
    except ValidationError as exc:
        raise KGError(
            ErrorCode.INVALID_REQUEST, {"reason": "invalid_attribute_definition"}
        ) from exc


def _relation_detail(session: Session, relation: ModelResource) -> ObjectPropDetail:
    """取（或建）关系的约束明细行。端点基数与 OWL 特征落在这里。"""
    detail = session.get(ObjectPropDetail, relation.id)
    if detail is None:
        detail = ObjectPropDetail(resource_id=relation.id)
        session.add(detail)
        session.flush()
    return detail


def _set_endpoints(
    session: Session,
    relation: ModelResource,
    domain_spec: EndpointSpec,
    range_spec: EndpointSpec,
    domain_type: ModelResource,
    range_type: ModelResource,
) -> None:
    """存关系端点引用与基数约束。

    role 区分 domain/range，端点引用按 IRI 去重：同一类型被多关系引用是允许的。
    基数与角色标签落 object_prop_detail 的正式列（M-07 补齐，此前读写往返丢失）。
    """
    # 清旧端点
    session.execute(
        delete(ResourceRef).where(
            ResourceRef.source_id == relation.id,
            ResourceRef.role.in_(["relation_domain", "relation_range"]),
        )
    )
    session.add(
        ResourceRef(
            source_id=relation.id,
            target_id=domain_type.id,
            role="relation_domain",
        )
    )
    session.add(
        ResourceRef(
            source_id=relation.id,
            target_id=range_type.id,
            role="relation_range",
        )
    )

    detail = _relation_detail(session, relation)
    detail.domain_min = domain_spec.cardinality.min
    detail.domain_max = domain_spec.cardinality.max
    detail.domain_role_i18n = domain_spec.role_i18n
    detail.domain_cardinality_role_i18n = domain_spec.cardinality.role_label_i18n
    detail.range_min = range_spec.cardinality.min
    detail.range_max = range_spec.cardinality.max
    detail.range_role_i18n = range_spec.role_i18n
    detail.range_cardinality_role_i18n = range_spec.cardinality.role_label_i18n


def _set_owl_and_meta(
    session: Session,
    relation: ModelResource,
    owl: OwlFeatures,
    payload: RelationTypeCreate | RelationTypeUpdate,
    assoc_resource: ModelResource | None,
) -> None:
    """存 OWL 特征与端点外的元信息。

    OWL 特征落 object_prop_detail.owl（M-07 补齐）；
    inverse_of / union_of / intersection_of 存为 ResourceRef。
    传 `None` 的列表字段视为「不修改」，显式传空列表表示清空。
    """
    detail = _relation_detail(session, relation)
    detail.owl = owl.model_dump()

    # 关系型引用整体重写：先清旧，再按 payload 重建（None = 不改）
    refs_to_rewrite = (
        payload.inverse_of is not None
        or payload.union_of is not None
        or payload.intersection_of is not None
    )
    if not refs_to_rewrite:
        return
    session.execute(
        delete(ResourceRef).where(
            ResourceRef.source_id == relation.id,
            ResourceRef.role.in_(["inverse_of", "union_of", "intersection_of"]),
        )
    )
    if payload.inverse_of is not None:
        session.add(
            ResourceRef(
                source_id=relation.id,
                target_id=payload.inverse_of,
                role="inverse_of",
            )
        )
    for tid in payload.union_of or []:
        session.add(ResourceRef(source_id=relation.id, target_id=tid, role="union_of"))
    for tid in payload.intersection_of or []:
        session.add(
            ResourceRef(source_id=relation.id, target_id=tid, role="intersection_of")
        )


def _endpoint_spec(
    meta: RelationMeta, side: Literal["domain", "range"]
) -> EndpointSpec:
    """从已存约束重建端点，供「只改一侧端点」的更新用。"""
    if side == "domain":
        ids = meta["domain_ids"]
        cardinality = CardinalitySpec(
            min=meta["domain_min"],
            max=meta["domain_max"],
            role_label_i18n=meta["domain_cardinality_role_i18n"],
        )
        role_i18n = meta["domain_role_i18n"]
    else:
        ids = meta["range_ids"]
        cardinality = CardinalitySpec(
            min=meta["range_min"],
            max=meta["range_max"],
            role_label_i18n=meta["range_cardinality_role_i18n"],
        )
        role_i18n = meta["range_role_i18n"]
    if not ids:
        raise KGError(
            ErrorCode.RESOURCE_NOT_FOUND,
            {f"{side}_ids": [], "reason": "endpoint_missing"},
        )
    return EndpointSpec(type_id=ids[0], cardinality=cardinality, role_i18n=role_i18n)


def update_relation_type(
    session: Session, resource: ModelResource, payload: RelationTypeUpdate
) -> ModelResource:
    """更新关系类型（草稿态）。带 If-Match 乐观锁。

    端点基数、角色标签、OWL 特征、逆关系与 union/intersection 都会真正落库——
    M1 阶段这些字段被接受后丢弃，等于静默丢用户输入。
    """
    resource = lock_resource_edit(
        session, resource, payload.if_match, payload.edit_revision
    )

    if payload.attribute_defs is not None:
        assoc_id = get_relation_meta(session, resource)["assoc_resource_id"]
        if assoc_id is None:
            raise KGError(ErrorCode.INVALID_REQUEST, {"reason": "association_required"})
        assoc = session.get(ModelResource, assoc_id)
        if assoc is None or assoc.status != ResourceStatus.DRAFT:
            raise KGError(ErrorCode.ALREADY_PUBLISHED, {"resource_id": assoc_id})
        set_data_props(
            session, assoc, _attribute_inputs(payload.attribute_defs), "assoc_attribute"
        )

    if payload.label_i18n is not None:
        resource.label_i18n = payload.label_i18n
    if payload.definition_i18n is not None:
        resource.definition_i18n = payload.definition_i18n
    if payload.owl is not None:
        validate_owl_compatibility(payload.owl)
    if payload.inverse_of is not None:
        inverse = session.get(ModelResource, payload.inverse_of)
        if inverse is None or inverse.kind != ResourceKind.OBJECT_PROP:
            raise KGError(
                ErrorCode.VALIDATION_VIOLATION,
                {"inverse_of": payload.inverse_of, "reason": "not_a_relation"},
            )

    if payload.domain_spec is not None or payload.range_spec is not None:
        meta = get_relation_meta(session, resource)
        domain_spec = payload.domain_spec or _endpoint_spec(meta, "domain")
        range_spec = payload.range_spec or _endpoint_spec(meta, "range")
        _set_endpoints(
            session,
            resource,
            domain_spec,
            range_spec,
            _get_entity_type(session, domain_spec.type_id),
            _get_entity_type(session, range_spec.type_id),
        )

    owl = payload.owl if payload.owl is not None else _stored_owl(session, resource)
    _set_owl_and_meta(session, resource, owl, payload, None)

    session.flush()
    return resource


def _stored_owl(session: Session, relation: ModelResource) -> OwlFeatures:
    detail = session.get(ObjectPropDetail, relation.id)
    if detail is None or not detail.owl:
        return OwlFeatures()
    return OwlFeatures(**detail.owl)


def get_relation_type(session: Session, relation_id: int) -> ModelResource:
    resource = session.get(ModelResource, relation_id)
    if resource is None or resource.kind != ResourceKind.OBJECT_PROP:
        raise KGError(ErrorCode.RESOURCE_NOT_FOUND, {"id": relation_id})
    return resource


def list_relation_types(
    session: Session, q: str = "", page: int = 1, page_size: int = 50
) -> tuple[list[ModelResource], int]:
    """分页列表 + 名称搜索。"""
    stmt = select(ModelResource).where(ModelResource.kind == ResourceKind.OBJECT_PROP)
    if q:
        stmt = stmt.where(ModelResource.name.ilike(f"%{q}%"))
    count_stmt = select(ModelResource).where(
        ModelResource.kind == ResourceKind.OBJECT_PROP
    )
    if q:
        count_stmt = count_stmt.where(ModelResource.name.ilike(f"%{q}%"))
    total = len(list(session.execute(count_stmt).scalars()))
    stmt = (
        stmt.order_by(ModelResource.name)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = list(session.execute(stmt).scalars())
    return items, total


def get_relation_meta(session: Session, relation: ModelResource) -> RelationMeta:
    """取关系元数据：端点、基数、角色标签、OWL 特征、inverse_of、assoc_resource。

    供 API 层组装 RelationTypeOut；基数与 OWL 特征来自 object_prop_detail
    正式列（M-07 补齐），不再在读取时按默认值猜。
    """
    refs = (
        session.execute(select(ResourceRef).where(ResourceRef.source_id == relation.id))
        .scalars()
        .all()
    )
    domain_ids: list[int] = []
    range_ids: list[int] = []
    inverse_of: int | None = None
    union_of: list[int] = []
    intersection_of: list[int] = []
    assoc_resource_id: int | None = None
    for r in refs:
        if r.role == "relation_domain":
            domain_ids.append(r.target_id)
        elif r.role == "relation_range":
            range_ids.append(r.target_id)
        elif r.role == "inverse_of":
            inverse_of = r.target_id
        elif r.role == "union_of":
            union_of.append(r.target_id)
        elif r.role == "intersection_of":
            intersection_of.append(r.target_id)
        elif r.role == "assoc_resource":
            assoc_resource_id = r.target_id
    detail = session.get(ObjectPropDetail, relation.id)
    return RelationMeta(
        domain_ids=domain_ids,
        range_ids=range_ids,
        inverse_of=inverse_of,
        union_of=union_of,
        intersection_of=intersection_of,
        assoc_resource_id=assoc_resource_id,
        domain_min=detail.domain_min if detail else 0,
        domain_max=detail.domain_max if detail else -1,
        range_min=detail.range_min if detail else 0,
        range_max=detail.range_max if detail else -1,
        domain_role_i18n=detail.domain_role_i18n if detail else None,
        domain_cardinality_role_i18n=(
            detail.domain_cardinality_role_i18n if detail else None
        ),
        range_role_i18n=detail.range_role_i18n if detail else None,
        range_cardinality_role_i18n=(
            detail.range_cardinality_role_i18n if detail else None
        ),
        owl=dict(detail.owl) if detail else {},
    )


class RelationMeta(TypedDict):
    """关系元数据结构（供 API 层组装响应，类型安全）。"""

    domain_ids: list[int]
    range_ids: list[int]
    inverse_of: int | None
    union_of: list[int]
    intersection_of: list[int]
    assoc_resource_id: int | None
    domain_min: int
    domain_max: int
    range_min: int
    range_max: int
    domain_role_i18n: dict[str, str] | None
    domain_cardinality_role_i18n: dict[str, str] | None
    range_role_i18n: dict[str, str] | None
    range_cardinality_role_i18n: dict[str, str] | None
    owl: dict[str, bool]


def get_assoc_attributes(
    session: Session, assoc_resource: ModelResource
) -> list[AttributeDefOut]:
    """取关联实体的属性定义。

    数据类型与可空性从 datatype_prop_detail 读回（M-07 补齐），
    历史行缺失明细时回退到 string / nullable 的保守默认。
    """
    refs = (
        session.execute(
            select(ResourceRef).where(
                ResourceRef.source_id == assoc_resource.id,
                ResourceRef.role == "assoc_attribute",
            )
        )
        .scalars()
        .all()
    )
    attrs: list[AttributeDefOut] = []
    for r in refs:
        prop = session.get(ModelResource, r.target_id)
        if prop is None:
            continue
        detail = session.get(DatatypePropDetail, prop.id)
        attrs.append(
            AttributeDefOut(
                name=detail.prop_name if detail else prop.name.split(".")[-1],
                datatype=detail.datatype if detail else "string",
                nullable=detail.nullable if detail else True,
                enum_dict_id=detail.enum_dict_id if detail else None,
                enum_dict_revision=detail.enum_dict_revision if detail else None,
                default_value=detail.default_value if detail else None,
            )
        )
    return attrs


def publish_relation_type(session: Session, resource: ModelResource) -> int:
    """发布关系类型：冻结不可变版本。"""
    rev = publish_resource(session, resource)
    session.flush()
    return rev.revision
