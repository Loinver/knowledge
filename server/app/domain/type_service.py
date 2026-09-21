"""实体类型库领域服务（H-11）。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.domain.iri_service import build_resource_iri, validate_name
from app.domain.status_service import check_revision, publish_resource
from app.models.enums import ResourceKind, ResourceStatus
from app.models.resource import ModelResource, ResourceParent, ResourceRef
from app.schemas.type import EntityTypeCreate, EntityTypeUpdate


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
    _set_data_props(session, resource, payload.data_props)
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


def _set_data_props(session: Session, resource: ModelResource, props: list) -> None:
    """存数据属性到 resource 的 payload（M1 用 JSONB 存在关联资源上）。

    简化实现：数据属性作为 DATATYPE_PROP 类型的 ModelResource，通过 ResourceRef 关联。
    """
    from app.schemas.type import DataTypePropCreate

    # 删旧的数据属性引用
    session.query(ResourceRef).where(
        ResourceRef.source_id == resource.id, ResourceRef.role == "data_prop"
    ).delete()
    for prop in props:
        if not isinstance(prop, DataTypePropCreate):
            continue
        prop_resource = ModelResource(
            kind=ResourceKind.DATATYPE_PROP,
            name=f"{resource.name}.{prop.name}",
            iri=f"{resource.iri}/{prop.name}",
            namespace_id=resource.namespace_id,
            label_i18n=prop.label_i18n,
            definition_i18n=prop.definition_i18n,
            status=ResourceStatus.DRAFT,
        )
        session.add(prop_resource)
        session.flush()
        session.add(
            ResourceRef(
                source_id=resource.id, target_id=prop_resource.id, role="data_prop"
            )
        )


def update_entity_type(
    session: Session, resource: ModelResource, payload: EntityTypeUpdate
) -> ModelResource:
    """更新实体类型（草稿态）。带 If-Match 乐观锁。"""
    check_revision(resource, payload.if_match)
    if payload.label_i18n is not None:
        resource.label_i18n = payload.label_i18n
    if payload.definition_i18n is not None:
        resource.definition_i18n = payload.definition_i18n
    if payload.parent_ids is not None:
        _set_parents(session, resource, payload.parent_ids)
    if payload.data_props is not None:
        _set_data_props(session, resource, payload.data_props)
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
    count_stmt = select(ModelResource).where(ModelResource.kind == ResourceKind.ENTITY)
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
