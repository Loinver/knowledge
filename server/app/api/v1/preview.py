"""受限样例预览路由（H-22）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.domain.preview_service import preview_table
from app.schemas.preview import PreviewColumnMeta, PreviewRequest, PreviewResponse

router = APIRouter(prefix="/datasources", tags=["preview"])


@router.post("/preview", response_model=PreviewResponse)
def preview(
    payload: PreviewRequest,
    session: Session = Depends(get_session),
) -> PreviewResponse:
    result = preview_table(
        session,
        payload.datasource_id,
        payload.table,
        payload.db_schema,
        payload.limit,
        payload.offset,
    )
    return PreviewResponse(
        datasource_id=result["datasource_id"],
        table=result["table"],
        db_schema=result["schema"],
        columns=[PreviewColumnMeta(**c) for c in result["columns"]],
        rows=result["rows"],
        total_returned=result["total_returned"],
        truncated=result["truncated"],
    )
