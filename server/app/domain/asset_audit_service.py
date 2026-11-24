"""最小资产审计数据和只读检索；事务由 API 边界控制。"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Connection, cast, func, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.types import String

from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.models.asset_audit import AssetAuditAction, AssetAuditLog, AssetType
from app.models.data_access import Datasource, Mapping
from app.models.domain import AssemblyTemplate, BusinessDomain, Ontology
from app.models.enum_dictionary import EnumDictionary
from app.models.enums import AuditResult
from app.models.extraction import GraphRevision
from app.models.governance import Rule, StandardClause
from app.models.resource import ModelResource, Namespace
from app.schemas.asset_audit import AssetAuditSort, AssetAuditVersion

_ASSETS = {
    AssetType.NAMESPACE: Namespace.__table__,
    AssetType.ENTITY_TYPE: ModelResource.__table__,
    AssetType.RELATION_TYPE: ModelResource.__table__,
    AssetType.BUSINESS_DOMAIN: BusinessDomain.__table__,
    AssetType.ONTOLOGY: Ontology.__table__,
    AssetType.MAPPING: Mapping.__table__,
    AssetType.DATASOURCE: Datasource.__table__,
    AssetType.RULE: Rule.__table__,
    AssetType.ASSEMBLY_TEMPLATE: AssemblyTemplate.__table__,
    AssetType.ENUM_DICTIONARY: EnumDictionary.__table__,
    AssetType.STANDARD_CLAUSE: StandardClause.__table__,
    AssetType.GRAPH_REVISION: GraphRevision.__table__,
}


def read_asset_version(
    connection: Connection,
    object_type: AssetType,
    object_id: int | None,
    *,
    lock: bool = False,
) -> dict[str, int | None] | None:
    """只读取白名单数字列；不把 ORM 业务对象序列化进审计记录。

    支持 after_begin 事件提供的 Connection，不在事务事件里重入 Session。
    """
    if object_id is None:
        return None
    table = _ASSETS[object_type]
    if lock:
        quoted = connection.dialect.identifier_preparer.format_table(table)
        if connection.dialect.name == "sqlite":
            # A zero-row write acquires SQLite's transaction write lock without
            # touching asset values, timestamps or triggers.
            connection.exec_driver_sql(f"UPDATE {quoted} SET id = id WHERE 1 = 0")
        elif object_type == AssetType.GRAPH_REVISION:
            # The old version is a global pointer, so locking only the target
            # graph cannot serialize switches to different graph IDs.
            connection.exec_driver_sql(
                f"LOCK TABLE {quoted} IN SHARE ROW EXCLUSIVE MODE"
            )
    keys = [
        key
        for key in ("revision", "current_revision", "edit_revision", "run_id")
        if key in table.c
    ]
    statement = select(table.c.id, *(table.c[key] for key in keys)).where(
        table.c.id == object_id
    )
    if lock:
        statement = statement.with_for_update()
    row = connection.execute(statement).mappings().first()
    if row is None:
        return None
    version = {key: row[key] for key in keys}
    if object_type == AssetType.GRAPH_REVISION:
        version["current_graph_revision_id"] = connection.scalar(
            select(GraphRevision.id).where(GraphRevision.is_current.is_(True))
        )
    return version


def record_asset_audit(
    session: Session,
    *,
    actor_id: str,
    action: AssetAuditAction,
    object_type: AssetType,
    object_id: int | None,
    version_before: dict[str, int | None] | None,
    version_after: dict[str, int | None] | None,
    result: AuditResult,
    correlation_id: str,
    error_code: ErrorCode | None = None,
) -> AssetAuditLog:
    """仅接受受限字段；调用方不得传请求、响应、异常文本或业务快照。"""

    def version(value: dict[str, int | None] | None) -> dict[str, int | None] | None:
        if value is None:
            return None
        return AssetAuditVersion.model_validate(value).model_dump(exclude_none=True)

    entry = AssetAuditLog(
        actor_id=actor_id,
        action=action,
        object_type=object_type,
        object_id=object_id,
        version_before=version(version_before),
        version_after=version(version_after),
        result=result,
        error_code=error_code,
        correlation_id=correlation_id,
    )
    session.add(entry)
    return entry


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        raise KGError(ErrorCode.INVALID_REQUEST, {"reason": "timezone_required"})
    return value.astimezone(UTC)


def list_asset_audit(
    session: Session,
    *,
    page: int,
    page_size: int,
    q: str = "",
    actor_id: str | None = None,
    action: AssetAuditAction | None = None,
    object_type: AssetType | None = None,
    object_id: int | None = None,
    result: AuditResult | None = None,
    correlation_id: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    sort: AssetAuditSort = "-created_at",
) -> tuple[list[AssetAuditLog], int]:
    since, until = _utc(since), _utc(until)
    if since is not None and until is not None and since > until:
        raise KGError(ErrorCode.INVALID_REQUEST, {"reason": "invalid_time_range"})
    filters = []
    for column, value in (
        (AssetAuditLog.actor_id, actor_id),
        (AssetAuditLog.action, action),
        (AssetAuditLog.object_type, object_type),
        (AssetAuditLog.object_id, object_id),
        (AssetAuditLog.result, result),
        (AssetAuditLog.correlation_id, correlation_id),
    ):
        if value is not None:
            filters.append(column == value)
    if q.strip():
        keyword = q.strip()
        filters.append(
            or_(
                AssetAuditLog.actor_id.contains(keyword, autoescape=True),
                AssetAuditLog.correlation_id.contains(keyword, autoescape=True),
                cast(AssetAuditLog.object_id, String).contains(
                    keyword, autoescape=True
                ),
            )
        )
    if since is not None:
        filters.append(AssetAuditLog.created_at >= since)
    if until is not None:
        filters.append(AssetAuditLog.created_at <= until)
    total = (
        session.scalar(select(func.count()).select_from(AssetAuditLog).where(*filters))
        or 0
    )
    order = (
        (AssetAuditLog.created_at.asc(), AssetAuditLog.id.asc())
        if sort == "created_at"
        else (AssetAuditLog.created_at.desc(), AssetAuditLog.id.desc())
    )
    items = list(
        session.scalars(
            select(AssetAuditLog)
            .where(*filters)
            .order_by(*order)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return items, total
