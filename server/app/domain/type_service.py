"""实体类型库领域服务（H-11）。"""

from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.domain.enum_dictionary_service import lock_dictionary, resolve_reference
from app.domain.iri_service import build_resource_iri, validate_name
from app.domain.status_service import lock_resource_edit, publish_resource
from app.models.enums import ResourceKind, ResourceStatus
from app.models.resource import (
    DatatypePropDetail,
    ModelResource,
    ResourceParent,
    ResourceRef,
)
from app.schemas.type import (
    DataTypePropCreate,
    EntityTypeCreate,
    EntityTypeUpdate,
)


def create_entity_type(session: Session, payload: EntityTypeCreate) -> ModelResource:
    """创建实体类型。校验 name 唯一性与合法性，生成 IRI。"""
    from app.models.resource import Namespace

    validate_name(payload.name)
    namespace = session.get(Namespace, payload.namespace_id)
    if namespace is None:
        raise KGError(
            ErrorCode.RESOURCE_NOT_FOUND, {"namespace_id": payload.namespace_id}
        )
    iri = build_resource_iri(namespace, payload.name)
    existing = session.execute(
        select(ModelResource).where(ModelResource.name == payload.name)
    ).scalar_one_or_none()
    if existing is not None:
        raise KGError(
            ErrorCode.ALREADY_PUBLISHED,
            {"name": payload.name, "reason": "name_taken"},
        )
    resource = ModelResource(
        kind=ResourceKind.ENTITY,
        name=payload.name,
        iri=iri,
        namespace_id=namespace.id,
        label_i18n=payload.label_i18n,
        definition_i18n=payload.definition_i18n,
        status=ResourceStatus.DRAFT,
    )
    session.add(resource)
    session.flush()
    _set_parents(session, resource, payload.parent_ids)
    set_data_props(session, resource, payload.data_props)
    session.flush()
    return resource


def _set_parents(
    session: Session, resource: ModelResource, parent_ids: list[int]
) -> None:
    """设置类型层级（继承）。按 IRI 去重，避免环。"""
    session.execute(
        select(ResourceParent).where(ResourceParent.child_id == resource.id)
    )
    # 清除旧的
    session.query(ResourceParent).filter(
        ResourceParent.child_id == resource.id
    ).delete()
    seen: set[int] = set()
    for pid in parent_ids:
        if pid == resource.id or pid in seen:
            continue
        parent = session.get(ModelResource, pid)
        if parent is None:
            raise KGError(ErrorCode.RESOURCE_NOT_FOUND, {"parent_id": pid})
        session.add(ResourceParent(child_id=resource.id, parent_id=pid))
        seen.add(pid)


def set_data_props(
    session: Session,
    resource: ModelResource,
    props: list[DataTypePropCreate],
    role: str = "data_prop",
) -> None:
    """存数据属性：DATATYPE_PROP 子资源 + ResourceRef + 约束明细。

    数据类型、枚举引用、可空性与默认值落 datatype_prop_detail 正式列
    （M-07 补齐；此前只在 API 层接受，写库时静默丢弃）。

    注：被替换掉的旧属性子资源保留不删——已发布版本的历史 payload 里
    仍以 id 引用它们，删掉会让历史版本指向空。
    """
    names = [prop.name for prop in props]
    if len(set(names)) != len(names) or any(not name.strip() for name in names):
        raise KGError(
            ErrorCode.INVALID_REQUEST, {"reason": "duplicate_or_empty_property_name"}
        )
    existing_details = {
        detail.prop_name: detail
        for detail in session.scalars(
            select(DatatypePropDetail)
            .join(ResourceRef, ResourceRef.target_id == DatatypePropDetail.resource_id)
            .where(ResourceRef.source_id == resource.id, ResourceRef.role == role)
        )
    }
    # 多字典按稳定顺序加锁，避免两个属性列表顺序相反时形成死锁。
    for dictionary_id in sorted(
        {prop.enum_dict_id for prop in props if prop.enum_dict_id is not None}
    ):
        lock_dictionary(session, dictionary_id)
    pins: list[int | None] = []
    for prop in props:
        old = existing_details.get(prop.name)
        pin = prop.enum_dict_revision
        if pin is None and old is not None and old.enum_dict_id == prop.enum_dict_id:
            pin = old.enum_dict_revision
        pins.append(
            resolve_reference(
                session, prop.datatype, prop.enum_dict_id, pin, prop.default_value
            )
        )
    old_ids = list(
        session.scalars(
            select(ResourceRef.target_id).where(
                ResourceRef.source_id == resource.id,
                ResourceRef.role == role,
            )
        )
    )
    if old_ids:
        session.execute(
            delete(DatatypePropDetail).where(
                DatatypePropDetail.resource_id.in_(old_ids)
            )
        )
    session.execute(
        delete(ResourceRef).where(
            ResourceRef.source_id == resource.id, ResourceRef.role == role
        )
    )
    for prop, pin in zip(props, pins, strict=True):
        prop_resource = session.scalar(
            select(ModelResource).where(
                ModelResource.name == f"{resource.name}.{prop.name}",
                ModelResource.kind == ResourceKind.DATATYPE_PROP,
            )
        )
        if prop_resource is None:
            prop_resource = ModelResource(
                kind=ResourceKind.DATATYPE_PROP,
                name=f"{resource.name}.{prop.name}",
                iri=f"{resource.iri}/{prop.name}",
                namespace_id=resource.namespace_id,
                status=ResourceStatus.DRAFT,
            )
            session.add(prop_resource)
            session.flush()
        prop_resource.label_i18n = prop.label_i18n
        prop_resource.definition_i18n = prop.definition_i18n
        session.add(
            ResourceRef(source_id=resource.id, target_id=prop_resource.id, role=role)
        )
        session.add(
            DatatypePropDetail(
                resource_id=prop_resource.id,
                prop_name=prop.name,
                datatype=prop.datatype,
                enum_dict_id=prop.enum_dict_id,
                enum_dict_revision=pin,
                nullable=prop.nullable,
                default_value=prop.default_value,
            )
        )


def get_prop_detail(session: Session, prop_id: int) -> DatatypePropDetail | None:
    """取数据属性的约束明细；历史行可能没有明细，调用方需有保守回退。"""
    return session.get(DatatypePropDetail, prop_id)


def update_entity_type(
    session: Session, resource: ModelResource, payload: EntityTypeUpdate
) -> ModelResource:
    """更新实体类型（草稿态）。带 If-Match 乐观锁。"""
    resource = lock_resource_edit(
        session, resource, payload.if_match, payload.edit_revision
    )
    if payload.label_i18n is not None:
        resource.label_i18n = payload.label_i18n
    if payload.definition_i18n is not None:
        resource.definition_i18n = payload.definition_i18n
    if payload.parent_ids is not None:
        _set_parents(session, resource, payload.parent_ids)
    if payload.data_props is not None:
        set_data_props(session, resource, payload.data_props)
    session.flush()
    return resource


def get_entity_type(session: Session, type_id: int) -> ModelResource:
    resource = session.get(ModelResource, type_id)
    if resource is None or resource.kind != ResourceKind.ENTITY:
        raise KGError(ErrorCode.RESOURCE_NOT_FOUND, {"id": type_id})
    return resource


def list_entity_types(
    session: Session, q: str = "", page: int = 1, page_size: int = 50
) -> tuple[list[ModelResource], int]:
    """分页列表 + 名称/IRI 搜索。"""
    stmt = select(ModelResource).where(ModelResource.kind == ResourceKind.ENTITY)
    if q:
        stmt = stmt.where(ModelResource.name.ilike(f"%{q}%"))
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    stmt = (
        stmt.order_by(ModelResource.name)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = list(session.execute(stmt).scalars())
    return items, total


def get_data_props(session: Session, resource: ModelResource) -> list[ModelResource]:
    """取实体类型的数据属性。"""
    refs = (
        session.execute(
            select(ResourceRef).where(
                ResourceRef.source_id == resource.id, ResourceRef.role == "data_prop"
            )
        )
        .scalars()
        .all()
    )
    result: list[ModelResource] = []
    for r in refs:
        prop = session.get(ModelResource, r.target_id)
        if prop is not None:
            result.append(prop)
    return result


def get_parent_ids(session: Session, resource: ModelResource) -> list[int]:
    parents = (
        session.execute(
            select(ResourceParent).where(ResourceParent.child_id == resource.id)
        )
        .scalars()
        .all()
    )
    return [p.parent_id for p in parents]


def publish_entity_type(session: Session, resource: ModelResource) -> int:
    """发布实体类型：冻结不可变版本。"""
    rev = publish_resource(session, resource)
    session.flush()
    return rev.revision
