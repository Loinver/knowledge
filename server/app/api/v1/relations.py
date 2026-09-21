"""关系类型库路由（H-12）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.domain.relation_service import (
    create_relation_type,
    get_assoc_attributes,
    get_relation_meta,
    get_relation_type,
    list_relation_types,
    publish_relation_type,
    update_relation_type,
)
from app.models.resource import ModelResource
from app.schemas.relation import (
    EndpointSpec,
    OwlFeatures,
    RelationTypeBrief,
    RelationTypeCreate,
    RelationTypeOut,
    RelationTypeUpdate,
)
from app.schemas.type import RevisionOut as TypeRevisionOut

router = APIRouter(prefix="/relations", tags=["relations"])


def _to_out(
    session: Session, resource: ModelResource, payload: RelationTypeCreate | None
) -> RelationTypeOut:
    """组装 RelationTypeOut。优先用请求 payload（创建时），否则从 meta 重建。"""
    meta = get_relation_meta(session, resource)
    if payload is not None:
        domain_spec = payload.domain_spec
        range_spec = payload.range_spec
        owl = payload.owl
        union_of = payload.union_of
        intersection_of = payload.intersection_of
        enable_attributes = payload.enable_attributes
        inverse_of = payload.inverse_of
    else:
        # 重建端点 spec（更新/查询路径）：基数默认，role_i18n 从 meta 取不到最小回退
        domain_id = meta["domain_ids"][0] if meta["domain_ids"] else 0
        range_id = meta["range_ids"][0] if meta["range_ids"] else 0
        domain_spec = EndpointSpec(type_id=domain_id)
        range_spec = EndpointSpec(type_id=range_id)
        owl = OwlFeatures()
        union_of = meta["union_of"]
        intersection_of = meta["intersection_of"]
        enable_attributes = meta["assoc_resource_id"] is not None
        inverse_of = meta["inverse_of"]

    attribute_defs: list = []
    if meta["assoc_resource_id"] is not None:
        assoc = session.get(ModelResource, meta["assoc_resource_id"])
        if assoc is not None:
            attribute_defs = get_assoc_attributes(session, assoc)

    return RelationTypeOut(
        id=resource.id,
        kind=resource.kind,
        name=resource.name,
        iri=resource.iri,
        namespace_id=resource.namespace_id,
        label_i18n=resource.label_i18n,
        definition_i18n=resource.definition_i18n,
        status=resource.status,
        current_revision=resource.current_revision,
        domain_spec=domain_spec,
        range_spec=range_spec,
        inverse_of=inverse_of,
        owl=owl,
        union_of=union_of,
        intersection_of=intersection_of,
        enable_attributes=enable_attributes,
        assoc_resource_id=meta["assoc_resource_id"],
        attribute_defs=attribute_defs,
    )


@router.get("", response_model=list[RelationTypeBrief])
def list_relations(
    q: str = Query(""),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    session: Session = Depends(get_session),
) -> list[RelationTypeBrief]:
    items, _total = list_relation_types(session, q, page, page_size)
    out: list[RelationTypeBrief] = []
    for res in items:
        meta = get_relation_meta(session, res)
        out.append(
            RelationTypeBrief(
                id=res.id,
                name=res.name,
                iri=res.iri,
                label_i18n=res.label_i18n,
                status=res.status,
                current_revision=res.current_revision,
                enable_attributes=meta["assoc_resource_id"] is not None,
                inverse_of=meta["inverse_of"],
            )
        )
    return out


@router.post("", response_model=RelationTypeOut, status_code=201)
def create_relation(
    payload: RelationTypeCreate, session: Session = Depends(get_session)
) -> RelationTypeOut:
    resource = create_relation_type(session, payload)
    session.commit()
    return _to_out(session, resource, payload)


@router.get("/{relation_id}", response_model=RelationTypeOut)
def get_relation(
    relation_id: int, session: Session = Depends(get_session)
) -> RelationTypeOut:
    resource = get_relation_type(session, relation_id)
    return _to_out(session, resource, None)


@router.put("/{relation_id}", response_model=RelationTypeOut)
def update_relation(
    relation_id: int,
    payload: RelationTypeUpdate,
    session: Session = Depends(get_session),
) -> RelationTypeOut:
    resource = get_relation_type(session, relation_id)
    update_relation_type(session, resource, payload)
    session.commit()
    return _to_out(session, resource, None)


@router.post("/{relation_id}/publish", response_model=TypeRevisionOut)
def publish_relation(
    relation_id: int, session: Session = Depends(get_session)
) -> TypeRevisionOut:
    resource = get_relation_type(session, relation_id)
    revision = publish_relation_type(session, resource)
    session.commit()
    return TypeRevisionOut(revision=revision, checksum="")
