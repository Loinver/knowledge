"""实体类型库路由（H-11）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.domain.type_service import (
    create_entity_type,
    get_entity_type,
    get_parent_ids,
    list_entity_types,
    publish_entity_type,
    update_entity_type,
)
from app.schemas.type import (
    EntityTypeBrief,
    EntityTypeCreate,
    EntityTypeOut,
    EntityTypeUpdate,
    RevisionOut,
)

router = APIRouter(prefix="/entity-types", tags=["entity-types"])


@router.get("", response_model=list[EntityTypeBrief])
def list_types(
    q: str = Query(""),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    session: Session = Depends(get_session),
) -> list[EntityTypeBrief]:
    items, _total = list_entity_types(session, q, page, page_size)
    return [EntityTypeBrief.model_validate(i) for i in items]


@router.post("", response_model=EntityTypeOut, status_code=201)
def create_type(
    payload: EntityTypeCreate, session: Session = Depends(get_session)
) -> EntityTypeOut:
    resource = create_entity_type(session, payload)
    session.commit()
    return EntityTypeOut(
        id=resource.id,
        kind=resource.kind,
        name=resource.name,
        iri=resource.iri,
        namespace_id=resource.namespace_id,
        label_i18n=resource.label_i18n,
        definition_i18n=resource.definition_i18n,
        status=resource.status,
        current_revision=resource.current_revision,
        data_props=[],
        parent_ids=get_parent_ids(session, resource),
    )


@router.get("/{type_id}", response_model=EntityTypeOut)
def get_type(type_id: int, session: Session = Depends(get_session)) -> EntityTypeOut:
    resource = get_entity_type(session, type_id)
    return EntityTypeOut(
        id=resource.id,
        kind=resource.kind,
        name=resource.name,
        iri=resource.iri,
        namespace_id=resource.namespace_id,
        label_i18n=resource.label_i18n,
        definition_i18n=resource.definition_i18n,
        status=resource.status,
        current_revision=resource.current_revision,
        data_props=[],
        parent_ids=get_parent_ids(session, resource),
    )


@router.put("/{type_id}", response_model=EntityTypeOut)
def update_type(
    type_id: int,
    payload: EntityTypeUpdate,
    session: Session = Depends(get_session),
) -> EntityTypeOut:
    resource = get_entity_type(session, type_id)
    update_entity_type(session, resource, payload)
    session.commit()
    return EntityTypeOut(
        id=resource.id,
        kind=resource.kind,
        name=resource.name,
        iri=resource.iri,
        namespace_id=resource.namespace_id,
        label_i18n=resource.label_i18n,
        definition_i18n=resource.definition_i18n,
        status=resource.status,
        current_revision=resource.current_revision,
        data_props=[],
        parent_ids=get_parent_ids(session, resource),
    )


@router.post("/{type_id}/publish", response_model=RevisionOut)
def publish_type(type_id: int, session: Session = Depends(get_session)) -> RevisionOut:
    resource = get_entity_type(session, type_id)
    revision = publish_entity_type(session, resource)
    session.commit()
    return RevisionOut(revision=revision, checksum="")
