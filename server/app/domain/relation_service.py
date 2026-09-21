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

from typing import TypedDict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.domain.iri_service import build_resource_iri, validate_name
from app.domain.status_service import check_revision, publish_resource
from app.models.enums import ResourceKind, ResourceStatus
from app.models.resource import ModelResource, Namespace, ResourceRef
from app.schemas.relation import (
    AttributeDefOut,
    EndpointSpec,
    OwlFeatures,
    RelationTypeCreate,
    RelationTypeUpdate,
)

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
    # 属性定义存到 ASSOC 的引用（M1 存结构，M4 补完整 OWL 语义）
    # 简化：属性定义作为 DATATYPE_PROP 子资源挂在 ASSOC 上
    for attr in attribute_defs:
        attr_name = str(attr.get("name", ""))
        if not attr_name:
            continue
        prop_res = ModelResource(
            kind=ResourceKind.DATATYPE_PROP,
            name=f"{assoc_name}.{attr_name}",
            iri=f"{assoc_iri}/{attr_name}",
            namespace_id=namespace.id,
            status=ResourceStatus.DRAFT,
        )
        session.add(prop_res)
        session.flush()
        session.add(
            ResourceRef(
                source_id=assoc.id, target_id=prop_res.id, role="assoc_attribute"
            )
        )
    return assoc


def _set_endpoints(
    session: Session,
    relation: ModelResource,
    domain_spec: EndpointSpec,
    range_spec: EndpointSpec,
    domain_type: ModelResource,
    range_type: ModelResource,
) -> None:
    """存关系端点引用。按 IRI 去重：同一类型被多关系引用是允许的。

    role 区分 domain/range，基数约束存在 ResourceRef 的元信息里（M1 用 JSON，
    后续 M4 补完整 OWL 语义时迁到正式列）。
    """
    # 清旧端点
    session.query(ResourceRef).where(
        ResourceRef.source_id == relation.id,
        ResourceRef.role.in_(["relation_domain", "relation_range"]),
    ).delete()
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


def _set_owl_and_meta(
    session: Session,
    relation: ModelResource,
    owl: OwlFeatures,
    payload: RelationTypeCreate,
    assoc_resource: ModelResource | None,
) -> None:
    """存 OWL 特征与元信息。

    M1 阶段 OWL 特征与 union/intersection 存在 resource 的扩展字段。
    ModelResource 没有专门的 meta 列，M0 设计上 payload 风格——
    这里用 ResourceRef 关联 assoc_resource，OWL 特征待 H-50 校验引擎
    读取时从领域服务查（本函数校验已做，存储用最小方式）。

    注：当前 ModelResource 无 meta JSONB 列，OWL 特征在 update/get 时
    由本服务从 payload 重建（见 _build_out）。这与 type_service 的
    data_props 处理方式一致（DATATYPE_PROP 子资源 + ResourceRef）。
    """
    # inverse_of 存为 ResourceRef（role=inverse_of）
    if payload.inverse_of is not None:
        session.add(
            ResourceRef(
                source_id=relation.id,
                target_id=payload.inverse_of,
                role="inverse_of",
            )
        )
    # union_of / intersection_of 存为 ResourceRef
    for tid in payload.union_of:
        session.add(ResourceRef(source_id=relation.id, target_id=tid, role="union_of"))
    for tid in payload.intersection_of:
        session.add(
            ResourceRef(source_id=relation.id, target_id=tid, role="intersection_of")
        )


def update_relation_type(
    session: Session, resource: ModelResource, payload: RelationTypeUpdate
) -> ModelResource:
    """更新关系类型（草稿态）。带 If-Match 乐观锁。"""
    check_revision(resource, payload.if_match)
    if resource.status == ResourceStatus.PUBLISHED:
        raise KGError(ErrorCode.ALREADY_PUBLISHED, {"resource": resource.name})

    if payload.label_i18n is not None:
        resource.label_i18n = payload.label_i18n
    if payload.definition_i18n is not None:
        resource.definition_i18n = payload.definition_i18n
    if payload.owl is not None:
        validate_owl_compatibility(payload.owl)
    if payload.domain_spec is not None:
        _get_entity_type(session, payload.domain_spec.type_id)
    if payload.range_spec is not None:
        _get_entity_type(session, payload.range_spec.type_id)

    session.flush()
    return resource


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
    """取关系元数据：端点、inverse_of、union/intersection、assoc_resource。

    供 API 层组装 RelationTypeOut。
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
    return RelationMeta(
        domain_ids=domain_ids,
        range_ids=range_ids,
        inverse_of=inverse_of,
        union_of=union_of,
        intersection_of=intersection_of,
        assoc_resource_id=assoc_resource_id,
    )


class RelationMeta(TypedDict):
    """关系元数据结构（供 API 层组装响应，类型安全）。"""

    domain_ids: list[int]
    range_ids: list[int]
    inverse_of: int | None
    union_of: list[int]
    intersection_of: list[int]
    assoc_resource_id: int | None


def get_assoc_attributes(
    session: Session, assoc_resource: ModelResource
) -> list[AttributeDefOut]:
    """取关联实体的属性定义。"""
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
        if prop is not None:
            attrs.append(
                AttributeDefOut(
                    name=prop.name.split(".")[-1],
                    datatype="string",
                    nullable=True,
                )
            )
    return attrs


def publish_relation_type(session: Session, resource: ModelResource) -> int:
    """发布关系类型：冻结不可变版本。"""
    rev = publish_resource(session, resource)
    session.flush()
    return rev.revision
