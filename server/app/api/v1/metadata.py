"""元数据采集与目录路由（H-21）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.domain.metadata_service import (
    capture_metadata,
    find_table_references,
    get_latest_snapshot,
    get_snapshot,
    list_snapshots,
)
from app.schemas.metadata import (
    MetadataSnapshotBrief,
    MetadataSnapshotOut,
    ReferenceItem,
    TableReferenceResponse,
)

router = APIRouter(prefix="/datasources", tags=["metadata"])


@router.post(
    "/{ds_id}/metadata/capture", response_model=MetadataSnapshotOut, status_code=201
)
def capture(ds_id: int, session: Session = Depends(get_session)) -> MetadataSnapshotOut:
    snap = capture_metadata(session, ds_id)
    session.commit()
    return MetadataSnapshotOut.model_validate(snap)


@router.get("/{ds_id}/metadata/snapshots", response_model=list[MetadataSnapshotBrief])
def list_snap(
    ds_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    session: Session = Depends(get_session),
) -> list[MetadataSnapshotBrief]:
    items, _total = list_snapshots(session, ds_id, page, page_size)
    return [MetadataSnapshotBrief.model_validate(i) for i in items]


@router.get("/{ds_id}/metadata/latest", response_model=MetadataSnapshotOut)
def get_latest(
    ds_id: int, session: Session = Depends(get_session)
) -> MetadataSnapshotOut:
    snap = get_latest_snapshot(session, ds_id)
    if snap is None:
        from app.core.error_codes import ErrorCode
        from app.core.errors import KGError

        raise KGError(
            ErrorCode.RESOURCE_NOT_FOUND,
            {"datasource_id": ds_id, "reason": "no_snapshot"},
        )
    return MetadataSnapshotOut.model_validate(snap)


@router.get("/metadata/{snapshot_id}", response_model=MetadataSnapshotOut)
def get_snap(
    snapshot_id: int, session: Session = Depends(get_session)
) -> MetadataSnapshotOut:
    snap = get_snapshot(session, snapshot_id)
    return MetadataSnapshotOut.model_validate(snap)


@router.get(
    "/metadata/tables/{table_name}/references", response_model=TableReferenceResponse
)
def table_refs(
    table_name: str, session: Session = Depends(get_session)
) -> TableReferenceResponse:
    refs = find_table_references(session, table_name)
    return TableReferenceResponse(
        table=table_name,
        references=[ReferenceItem(**r) for r in refs],
    )
