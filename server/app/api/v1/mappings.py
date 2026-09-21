"""映射方案路由（H-30）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.domain.mapping_service import (
    create_mapping,
    delete_mapping,
    get_draft_revision,
    get_mapping,
    get_published_revision,
    list_mappings,
    publish_mapping,
    save_draft,
)
from app.schemas.mapping import (
    MappingBrief,
    MappingCreate,
    MappingOut,
    MappingRevisionCreate,
    MappingRevisionOut,
)

router = APIRouter(prefix="/mappings", tags=["mappings"])


class SaveDraftRequest(BaseModel):
    draft: MappingRevisionCreate
    if_match: int


class PublishRequest(BaseModel):
    if_match: int


@router.get("", response_model=list[MappingBrief])
def list_m(
    q: str = Query(""),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    session: Session = Depends(get_session),
) -> list[MappingBrief]:
    items, _total = list_mappings(session, q, page, page_size)
    return [MappingBrief.model_validate(i) for i in items]


@router.post("", response_model=MappingOut, status_code=201)
def create_m(
    payload: MappingCreate, session: Session = Depends(get_session)
) -> MappingOut:
    m = create_mapping(session, payload)
    session.commit()
    return MappingOut.model_validate(m)


@router.get("/{mapping_id}", response_model=MappingOut)
def get_m(mapping_id: int, session: Session = Depends(get_session)) -> MappingOut:
    m = get_mapping(session, mapping_id)
    return MappingOut.model_validate(m)


@router.delete("/{mapping_id}", status_code=204)
def remove_m(mapping_id: int, session: Session = Depends(get_session)) -> None:
    delete_mapping(session, mapping_id)
    session.commit()


@router.put("/{mapping_id}/draft", response_model=MappingRevisionOut)
def put_draft(
    mapping_id: int,
    payload: SaveDraftRequest,
    session: Session = Depends(get_session),
) -> MappingRevisionOut:
    rev = save_draft(session, mapping_id, payload.draft, payload.if_match)
    session.commit()
    return MappingRevisionOut.model_validate(rev)


@router.get("/{mapping_id}/draft", response_model=MappingRevisionOut | None)
def get_draft(
    mapping_id: int, session: Session = Depends(get_session)
) -> MappingRevisionOut | None:
    rev = get_draft_revision(session, mapping_id)
    if rev is None:
        return None
    return MappingRevisionOut.model_validate(rev)


@router.post("/{mapping_id}/publish", response_model=MappingRevisionOut)
def publish_m(
    mapping_id: int,
    payload: PublishRequest,
    session: Session = Depends(get_session),
) -> MappingRevisionOut:
    rev = publish_mapping(session, mapping_id, payload.if_match)
    session.commit()
    return MappingRevisionOut.model_validate(rev)


@router.get("/{mapping_id}/published", response_model=MappingRevisionOut)
def get_pub(
    mapping_id: int, session: Session = Depends(get_session)
) -> MappingRevisionOut:
    rev = get_published_revision(session, mapping_id)
    return MappingRevisionOut.model_validate(rev)
