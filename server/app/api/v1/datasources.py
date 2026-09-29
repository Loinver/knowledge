"""数据源连接路由（H-20）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.domain.source_service import (
    create_datasource,
    delete_datasource,
    get_datasource,
    get_display_params,
    list_datasources,
    test_connection,
    test_stored_connection,
    update_datasource,
)
from app.schemas.datasource import (
    DatasourceBrief,
    DatasourceCreate,
    DatasourceOut,
    DatasourceUpdate,
    TestConnectionRequest,
    TestConnectionResponse,
)
from app.schemas.response import ApiResponse

router = APIRouter(prefix="/datasources", tags=["datasources"])


@router.get("", response_model=ApiResponse[list[DatasourceBrief]])
def list_ds(
    q: str = Query(""),
    session: Session = Depends(get_session),
) -> list[DatasourceBrief]:
    items, _total = list_datasources(session, q)
    return [DatasourceBrief.model_validate(i) for i in items]


@router.post("", response_model=ApiResponse[DatasourceOut], status_code=201)
def create_ds(
    payload: DatasourceCreate, session: Session = Depends(get_session)
) -> DatasourceOut:
    ds = create_datasource(session, payload)
    session.commit()
    return DatasourceOut(
        id=ds.id,
        name=ds.name,
        kind=ds.kind,
        params=get_display_params(ds),
        status=ds.status,
    )


@router.get("/{ds_id}", response_model=ApiResponse[DatasourceOut])
def get_ds(ds_id: int, session: Session = Depends(get_session)) -> DatasourceOut:
    ds = get_datasource(session, ds_id)
    return DatasourceOut(
        id=ds.id,
        name=ds.name,
        kind=ds.kind,
        params=get_display_params(ds),
        status=ds.status,
    )


@router.delete("/{ds_id}", response_model=ApiResponse[None])
def remove_ds(ds_id: int, session: Session = Depends(get_session)) -> None:
    delete_datasource(session, ds_id)
    session.commit()


@router.put("/{ds_id}", response_model=ApiResponse[DatasourceOut])
def update_ds(
    ds_id: int, payload: DatasourceUpdate, session: Session = Depends(get_session)
) -> DatasourceOut:
    """更新连接信息（改名/换参数/换凭据），凭据脱敏后返回。"""
    ds = update_datasource(session, ds_id, payload)
    session.commit()
    return DatasourceOut(
        id=ds.id,
        name=ds.name,
        kind=ds.kind,
        params=get_display_params(ds),
        status=ds.status,
    )


@router.post(
    "/{ds_id}/test-connection", response_model=ApiResponse[TestConnectionResponse]
)
def test_stored_conn(
    ds_id: int, session: Session = Depends(get_session)
) -> TestConnectionResponse:
    """用库里保存的参数与凭据测试连接，并把结果落到 status。"""
    result = test_stored_connection(session, ds_id)
    session.commit()
    return TestConnectionResponse(
        ok=result["ok"], message=result["message"], table_count=result["table_count"]
    )


@router.post("/test-connection", response_model=ApiResponse[TestConnectionResponse])
def test_conn(payload: TestConnectionRequest) -> TestConnectionResponse:
    result = test_connection(payload.kind, payload.params, payload.credential)
    return TestConnectionResponse(**result)
