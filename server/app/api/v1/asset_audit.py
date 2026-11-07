"""业务资产审计只读接口；没有创建、更新、删除端点。"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.v1.deps import require_admin
from app.core.db import get_session
from app.domain.asset_audit_service import list_asset_audit
from app.models.asset_audit import AssetAuditAction, AssetType
from app.models.enums import AuditResult
from app.schemas.asset_audit import AssetAuditOut, AssetAuditPage, AssetAuditSort
from app.schemas.response import ApiResponse

router = APIRouter(
    prefix="/asset-audit-logs",
    tags=["asset-audit"],
    dependencies=[Depends(require_admin)],
)


@router.get("", response_model=ApiResponse[AssetAuditPage])
def list_asset_audit_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    q: str = Query("", max_length=128),
    actor_id: str | None = Query(None, max_length=32),
    action: AssetAuditAction | None = None,
    object_type: AssetType | None = None,
    object_id: int | None = Query(None, ge=1, le=2**63 - 1),
    result: AuditResult | None = None,
    correlation_id: str | None = Query(None, max_length=32),
    since: datetime | None = None,
    until: datetime | None = None,
    sort: AssetAuditSort = "-created_at",
    session: Session = Depends(get_session),
) -> AssetAuditPage:
    items, total = list_asset_audit(
        session,
        page=page,
        page_size=page_size,
        q=q,
        actor_id=actor_id,
        action=action,
        object_type=object_type,
        object_id=object_id,
        result=result,
        correlation_id=correlation_id,
        since=since,
        until=until,
        sort=sort,
    )
    return AssetAuditPage(
        items=[AssetAuditOut.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )
