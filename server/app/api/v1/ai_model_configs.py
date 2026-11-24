"""Administrator CRUD for persisted AI model endpoints and defaults."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.orm import Session

from app.api.v1.deps import require_admin
from app.core.db import get_session
from app.domain import ai_model_service as service
from app.models.account import User
from app.models.ai_model import AiModelCapability, AiModelConfig
from app.schemas.ai_model import (
    AiModelConfigCreate,
    AiModelConfigOut,
    AiModelConfigPage,
    AiModelConfigUpdate,
    AiModelDefaultOut,
    AiModelDefaultUpdate,
    AiModelSort,
)
from app.schemas.response import ApiResponse

router = APIRouter(
    prefix="/ai",
    tags=["ai-model-configs"],
    dependencies=[Depends(require_admin)],
)


def _out(
    session: Session, item: AiModelConfig, default_ids: set[int] | None = None
) -> AiModelConfigOut:
    if default_ids is None:
        default_ids = {
            row.config_id
            for row in service.list_defaults(session)
            if row.config_id is not None
        }
    return AiModelConfigOut(
        id=item.id,
        name=item.name,
        capability=item.capability,
        base_url=item.base_url,
        model=item.model,
        timeout_seconds=item.timeout_seconds,
        model_version=item.model_version,
        enabled=item.enabled,
        has_key=bool(item.credential_cipher),
        api_key_mask="***" if item.credential_cipher else None,
        is_default=item.id in default_ids,
        revision=item.revision,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


@router.get("/model-configs", response_model=ApiResponse[AiModelConfigPage])
def list_model_configs(
    q: str = Query("", max_length=200),
    capability: AiModelCapability | None = None,
    enabled: bool | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    sort: AiModelSort = "-created_at",
    session: Session = Depends(get_session),
) -> AiModelConfigPage:
    items, total, default_ids = service.list_configs(
        session,
        q=q,
        capability=capability,
        enabled=enabled,
        page=page,
        page_size=page_size,
        sort=sort,
    )
    return AiModelConfigPage(
        items=[_out(session, item, default_ids) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/model-configs", response_model=ApiResponse[AiModelConfigOut], status_code=201
)
def create_model_config(
    payload: AiModelConfigCreate,
    _admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
) -> AiModelConfigOut:
    item = service.create_config(session, payload)
    result = _out(session, item)
    session.commit()
    return result


@router.get("/model-configs/{config_id}", response_model=ApiResponse[AiModelConfigOut])
def get_model_config(
    config_id: int,
    _admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
) -> AiModelConfigOut:
    return _out(session, service.get_config(session, config_id))


@router.put("/model-configs/{config_id}", response_model=ApiResponse[AiModelConfigOut])
def update_model_config(
    config_id: int,
    payload: AiModelConfigUpdate,
    if_match: str | None = Header(None, alias="If-Match"),
    _admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
) -> AiModelConfigOut:
    item = service.update_config(
        session, config_id, payload, service.parse_if_match(if_match)
    )
    result = _out(session, item)
    session.commit()
    return result


@router.delete("/model-configs/{config_id}", response_model=ApiResponse[None])
def delete_model_config(
    config_id: int,
    if_match: str | None = Header(None, alias="If-Match"),
    _admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
) -> None:
    service.delete_config(session, config_id, service.parse_if_match(if_match))
    session.commit()


@router.get("/model-defaults", response_model=ApiResponse[list[AiModelDefaultOut]])
def list_model_defaults(
    _admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
) -> list[AiModelDefaultOut]:
    rows = {row.capability: row for row in service.list_defaults(session)}
    return [
        AiModelDefaultOut(
            capability=capability,
            config_id=rows[capability].config_id if capability in rows else None,
            revision=rows[capability].revision if capability in rows else 1,
        )
        for capability in (AiModelCapability.CHAT, AiModelCapability.EMBEDDING)
    ]


@router.put(
    "/model-defaults/{capability}", response_model=ApiResponse[AiModelDefaultOut]
)
def update_model_default(
    capability: AiModelCapability,
    payload: AiModelDefaultUpdate,
    if_match: str | None = Header(None, alias="If-Match"),
    _admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
) -> AiModelDefaultOut:
    row = service.set_default(
        session,
        capability,
        payload.config_id,
        service.parse_if_match(if_match),
    )
    result = AiModelDefaultOut(
        capability=row.capability,
        config_id=row.config_id,
        revision=row.revision,
    )
    session.commit()
    return result
