"""已登录用户的工作台汇总统计。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.v1.deps import current_user
from app.core.db import get_session
from app.domain import dashboard_service
from app.schemas.dashboard import DashboardStatsOut
from app.schemas.response import ApiResponse

router = APIRouter(
    prefix="/dashboard", tags=["dashboard"], dependencies=[Depends(current_user)]
)


@router.get("/stats", response_model=ApiResponse[DashboardStatsOut])
def read_stats(session: Session = Depends(get_session)) -> DashboardStatsOut:
    return DashboardStatsOut.model_validate(dashboard_service.get_stats(session))
