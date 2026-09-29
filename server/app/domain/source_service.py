"""数据源连接管理领域服务（H-20）。"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.connectors.sql import readonly_engine
from app.core.crypto import (
    SENSITIVE_PARAM_KEYS,
    decrypt,
    encrypt,
    is_legacy_ciphertext,
    mask_credential,
)
from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.models.data_access import Datasource, MetadataSnapshot
from app.models.extraction import ExtractionTask, FactEvidence
from app.schemas.datasource import DatasourceCreate, DatasourceUpdate


def create_datasource(session: Session, payload: DatasourceCreate) -> Datasource:
    """创建数据源。凭据加密后存，浏览器只拿脱敏参数。"""
    existing = session.execute(
        select(Datasource).where(Datasource.name == payload.name)
    ).scalar_one_or_none()
    if existing is not None:
        raise KGError(
            ErrorCode.ALREADY_EXISTS,
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


def update_datasource(
    session: Session, ds_id: int, payload: DatasourceUpdate
) -> Datasource:
    """更新连接信息：改名、换参数、换凭据。

    凭据重新加密后存；参数或凭据变化后旧连接状态不再可信，重置为
    DISCONNECTED，等下一次显式测试连接再翻转。
    """
    ds = get_datasource(session, ds_id)
    if payload.name is not None and payload.name != ds.name:
        existing = session.execute(
            select(Datasource).where(Datasource.name == payload.name)
        ).scalar_one_or_none()
        if existing is not None:
            raise KGError(
                ErrorCode.ALREADY_EXISTS,
                {"name": payload.name, "reason": "datasource_name_taken"},
            )
        ds.name = payload.name
    if payload.params is not None:
        ds.params = payload.params
        ds.status = "DISCONNECTED"
    if payload.credential is not None:
        ds.credential_cipher = encrypt(payload.credential)
        ds.status = "DISCONNECTED"
    session.flush()
    return ds


def test_stored_connection(session: Session, ds_id: int) -> dict:
    """用库里的参数与凭据测试连接，并把结果落到 status。

    之前 test_connection 只返回结果不落库，status 建库后永远是
    DISCONNECTED，前端的状态列是死值。
    """
    ds = get_datasource(session, ds_id)
    try:
        credential = decrypt(ds.credential_cipher) if ds.credential_cipher else None
    except KGError:
        result = {"ok": False, "message": "credential_unreadable", "table_count": None}
    else:
        result = test_connection(ds.kind, ds.params or {}, credential)
    ds.status = "CONNECTED" if result["ok"] else "DISCONNECTED"
    session.flush()
    return {**result, "status": ds.status}


def delete_datasource(session: Session, ds_id: int) -> None:
    ds = get_datasource(session, ds_id)
    # 快照、抽取任务、证据都按 datasource_id 钉住来源；删源会让证据链
    # 反向追溯（/evidence/trace/reverse）断链。有引用一律拒绝删除。
    referenced = (
        (
            session.scalar(
                select(func.count())
                .select_from(MetadataSnapshot)
                .where(MetadataSnapshot.datasource_id == ds_id)
            )
            or 0
        )
        + (
            session.scalar(
                select(func.count())
                .select_from(ExtractionTask)
                .where(ExtractionTask.datasource_id == ds_id)
            )
            or 0
        )
        + (
            session.scalar(
                select(func.count())
                .select_from(FactEvidence)
                .where(FactEvidence.source_id == ds_id)
            )
            or 0
        )
    )
    if referenced:
        raise KGError(
            ErrorCode.RESOURCE_IN_USE,
            {
                "datasource_id": ds_id,
                "count": referenced,
                "reason": "datasource_in_use",
            },
        )
    session.delete(ds)
    session.flush()


def reencrypt_datasources(session: Session, *, previous_key: str | None = None) -> int:
    """Convert legacy ciphertext and embedded secrets in one caller-owned transaction.

    Supplying the previous key also rotates existing AES-GCM records. A mismatch
    between two stored secret locations aborts the whole transaction.
    """
    changed = 0
    for ds in session.scalars(select(Datasource)):
        params = ds.params or {}
        embedded = [
            value
            for name, value in params.items()
            if str(name).lower() in SENSITIVE_PARAM_KEYS
        ]
        if any(not isinstance(value, str) for value in embedded):
            raise ValueError(f"Datasource {ds.id} has an invalid embedded secret")
        if len(set(embedded)) > 1:
            raise ValueError(f"Datasource {ds.id} has conflicting embedded secrets")
        stored = (
            decrypt(ds.credential_cipher, key=previous_key)
            if ds.credential_cipher
            else None
        )
        if stored is not None and embedded and stored != embedded[0]:
            raise ValueError(f"Datasource {ds.id} has conflicting credentials")
        if (
            not embedded
            and not previous_key
            and (
                not ds.credential_cipher
                or not is_legacy_ciphertext(ds.credential_cipher)
            )
        ):
            continue
        secret = stored if stored is not None else (embedded[0] if embedded else None)
        if secret is not None:
            ds.credential_cipher = encrypt(secret)
        ds.params = {
            name: value
            for name, value in params.items()
            if str(name).lower() not in SENSITIVE_PARAM_KEYS
        }
        changed += 1
    session.flush()
    return changed
