"""数据源连接管理领域服务（H-20）。"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.connectors.sql import readonly_engine
from app.core.crypto import decrypt, encrypt, mask_credential
from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.models.data_access import Datasource
from app.schemas.datasource import DatasourceCreate


def create_datasource(session: Session, payload: DatasourceCreate) -> Datasource:
    """创建数据源。凭据加密后存，浏览器只拿脱敏参数。"""
    existing = session.execute(
        select(Datasource).where(Datasource.name == payload.name)
    ).scalar_one_or_none()
    if existing is not None:
        raise KGError(
            ErrorCode.ALREADY_PUBLISHED,
            {"name": payload.name, "reason": "datasource_name_taken"},
        )
    credential_cipher = None
    if payload.credential:
        credential_cipher = encrypt(payload.credential)
    ds = Datasource(
        name=payload.name,
        kind=payload.kind,
        params=payload.params,
        credential_cipher=credential_cipher,
        status="DISCONNECTED",
    )
    session.add(ds)
    session.flush()
    return ds


def get_datasource(session: Session, ds_id: int) -> Datasource:
    ds = session.get(Datasource, ds_id)
    if ds is None:
        raise KGError(ErrorCode.RESOURCE_NOT_FOUND, {"datasource_id": ds_id})
    return ds


def list_datasources(
    session: Session, q: str = "", page: int = 1, page_size: int = 50
) -> tuple[list[Datasource], int]:
    stmt = select(Datasource)
    if q:
        stmt = stmt.where(Datasource.name.ilike(f"%{q}%"))
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    stmt = (
        stmt.order_by(Datasource.name).offset((page - 1) * page_size).limit(page_size)
    )
    items = list(session.execute(stmt).scalars())
    return items, total


@contextmanager
def datasource_engine(ds: Datasource) -> Iterator[Engine]:
    """解密后端凭据，源库访问与释放统一交给连接器。"""
    try:
        credential = decrypt(ds.credential_cipher) if ds.credential_cipher else None
        with readonly_engine(ds.kind, ds.params or {}, credential) as engine:
            yield engine
    except KGError as exc:
        raise KGError(exc.code, {**exc.params, "datasource_id": ds.id}) from None
    except Exception:
        raise KGError(
            ErrorCode.SOURCE_UNREACHABLE,
            {"datasource_id": ds.id, "reason": "source_unreachable"},
        ) from None


def test_connection(kind: str, params: dict, credential: str | None = None) -> dict:
    """测试连接：读权限检查 + 超时。"""
    try:
        with (
            readonly_engine(kind, params, credential) as engine,
            engine.connect() as conn,
        ):
            conn.execute(text("SELECT 1")).fetchone()
            if kind == "sqlite":
                sql = "SELECT count(*) FROM sqlite_master WHERE type = 'table'"
            else:
                sql = "SELECT count(*) FROM information_schema.tables"
            row = conn.execute(text(sql)).fetchone()
            count = row[0] if row is not None else None
        return {"ok": True, "message": "connected", "table_count": count}
    except KGError as exc:
        return {"ok": False, "message": exc.params["reason"], "table_count": None}


def get_display_params(ds: Datasource) -> dict:
    """返回给浏览器的脱敏参数。"""
    return mask_credential(ds.params or {})


def delete_datasource(session: Session, ds_id: int) -> None:
    ds = get_datasource(session, ds_id)
    session.delete(ds)
    session.flush()
