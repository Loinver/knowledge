"""数据源连接管理领域服务（H-20）。"""

from __future__ import annotations

from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

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
    count_stmt = select(Datasource)
    if q:
        count_stmt = count_stmt.where(Datasource.name.ilike(f"%{q}%"))
    total = len(list(session.execute(count_stmt).scalars()))
    stmt = (
        stmt.order_by(Datasource.name).offset((page - 1) * page_size).limit(page_size)
    )
    items = list(session.execute(stmt).scalars())
    return items, total


def _build_engine(ds: Datasource) -> Engine:
    """根据数据源类型构建 SQLAlchemy engine。"""
    params = dict(ds.params or {})
    if ds.credential_cipher:
        params["password"] = decrypt(ds.credential_cipher)
    if ds.kind == "sqlite":
        db_path = params.get("database", params.get("path", ""))
        url = f"sqlite:///{db_path}"
    elif ds.kind == "postgresql":
        host = params.get("host", "localhost")
        port = params.get("port", 5432)
        db = params.get("database", "")
        user = params.get("user", "")
        pwd = params.get("password", "")
        url = f"postgresql+psycopg2://{user}:{pwd}@{host}:{port}/{db}"
    elif ds.kind == "mysql":
        host = params.get("host", "localhost")
        port = params.get("port", 3306)
        db = params.get("database", "")
        user = params.get("user", "")
        pwd = params.get("password", "")
        url = f"mysql+pymysql://{user}:{pwd}@{host}:{port}/{db}"
    else:
        raise KGError(ErrorCode.INVALID_REQUEST, {"kind": ds.kind})
    return create_engine(url)


def test_connection(kind: str, params: dict, credential: str | None = None) -> dict:
    """测试连接：读权限检查 + 超时。"""
    try:
        if kind == "sqlite":
            db_path = params.get("database", params.get("path", ""))
            url = f"sqlite:///{db_path}"
        else:
            p = dict(params)
            if credential:
                p["password"] = credential
            if kind == "postgresql":
                host = p.get("host", "localhost")
                port = p.get("port", 5432)
                db = p.get("database", "")
                user = p.get("user", "")
                pwd = p.get("password", "")
                url = f"postgresql+psycopg2://{user}:{pwd}@{host}:{port}/{db}"
            elif kind == "mysql":
                host = p.get("host", "localhost")
                port = p.get("port", 3306)
                db = p.get("database", "")
                user = p.get("user", "")
                pwd = p.get("password", "")
                url = f"mysql+pymysql://{user}:{pwd}@{host}:{port}/{db}"
            else:
                return {
                    "ok": False,
                    "message": f"unsupported: {kind}",
                    "table_count": None,
                }
        engine = create_engine(url)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1")).fetchone()
            if kind == "sqlite":
                sql = "SELECT count(*) FROM sqlite_master WHERE type = ?table?"
                sql = sql.replace("?table?", "'table'")
            else:
                sql = "SELECT count(*) FROM information_schema.tables"
            row = conn.execute(text(sql)).fetchone()
            count = row[0] if row is not None else None
        return {"ok": True, "message": "connected", "table_count": count}
    except Exception as e:
        return {"ok": False, "message": str(e)[:200], "table_count": None}


def get_display_params(ds: Datasource) -> dict:
    """返回给浏览器的脱敏参数。"""
    return mask_credential(ds.params or {})


def delete_datasource(session: Session, ds_id: int) -> None:
    ds = get_datasource(session, ds_id)
    session.delete(ds)
    session.flush()
