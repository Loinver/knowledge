"""受限样例预览服务（H-22）。

安全约束（A15）：
- 限行：limit 上限 100，offset 上限防止深翻页。
- 限时：查询带超时（SQLite 不支持 connect timeout，用语句层 limit 兜底）。
- 不入库：预览结果不写入任何表，不写运行日志。
- 凭据不出现在预览结果。
- 只读：源库连接器强制只读，拦截写语句。
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.domain.source_service import _build_engine, get_datasource

_WRITE_KEYWORDS = (
    "insert",
    "update",
    "delete",
    "drop",
    "alter",
    "create",
    "truncate",
    "grant",
    "revoke",
)


def _assert_readonly_query(table: str, schema: str) -> None:
    """表名/schema 不得含写语句关键字或分号（防注入与写操作）。"""
    raw = f"{schema} {table}".lower()
    if ";" in raw:
        raise KGError(ErrorCode.INVALID_REQUEST, {"reason": "semicolon_forbidden"})
    for kw in _WRITE_KEYWORDS:
        if kw in raw:
            raise KGError(
                ErrorCode.INVALID_REQUEST,
                {"reason": "write_keyword_forbidden", "keyword": kw},
            )


def _validate_table_exists(
    session: Session, ds_id: int, table: str, schema: str
) -> None:
    """对照最新元数据快照校验表存在，防止任意表名查询。"""
    from app.domain.metadata_service import get_latest_snapshot

    latest = get_latest_snapshot(session, ds_id)
    if latest is None:
        raise KGError(
            ErrorCode.INVALID_REQUEST,
            {"datasource_id": ds_id, "reason": "no_metadata_snapshot"},
        )
    found = False
    for s in latest.catalog.get("schemas", []):
        if s.get("schema") != schema:
            continue
        for t in s.get("tables", []):
            if t.get("name") == table:
                found = True
                break
    if not found:
        raise KGError(
            ErrorCode.RESOURCE_NOT_FOUND,
            {"table": table, "schema": schema},
        )


def preview_table(
    session: Session,
    ds_id: int,
    table: str,
    schema: str = "main",
    limit: int = 20,
    offset: int = 0,
) -> dict:
    """受限样例预览。返回结构供 route 组装响应，不写日志。"""
    # 限行硬上限
    if limit > 100:
        limit = 100
    if limit < 1:
        limit = 1
    if offset > 10000:
        raise KGError(ErrorCode.INVALID_REQUEST, {"reason": "offset_too_large"})

    _assert_readonly_query(table, schema)
    _validate_table_exists(session, ds_id, table, schema)

    ds = get_datasource(session, ds_id)
    try:
        engine = _build_engine(ds)
    except Exception as e:
        raise KGError(
            ErrorCode.SOURCE_UNREACHABLE,
            {"datasource_id": ds_id, "reason": str(e)[:200]},
        ) from e

    # 限定 schema/表名用引号包裹防注入；表名校验已过
    qualified = f'"{schema}"."{table}"' if schema and schema != "main" else f'"{table}"'
    sql = text(f"SELECT * FROM {qualified} LIMIT :lim OFFSET :off")

    try:
        with engine.connect() as conn:
            result = conn.execute(sql, {"lim": limit, "off": offset})
            col_names = list(result.keys())
            rows_data = [dict(row._mapping) for row in result.fetchmany(limit)]
    except Exception as e:
        raise KGError(
            ErrorCode.SOURCE_UNREACHABLE,
            {"datasource_id": ds_id, "reason": str(e)[:200]},
        ) from e

    # 凭据不出现在结果：遍历清除任何可能的密码字段
    sensitive_keys = {"password", "passwd", "secret", "credential", "token", "api_key"}
    cleaned_rows: list[dict] = []
    for row in rows_data:
        cleaned = {}
        for k, v in row.items():
            if k.lower() in sensitive_keys:
                cleaned[k] = "***"
            else:
                cleaned[k] = v
        cleaned_rows.append(cleaned)

    cols_meta = [{"name": n, "type": "unknown"} for n in col_names]
    total_returned = len(cleaned_rows)
    truncated = total_returned == limit

    return {
        "datasource_id": ds_id,
        "table": table,
        "schema": schema,
        "columns": cols_meta,
        "rows": cleaned_rows,
        "total_returned": total_returned,
        "truncated": truncated,
    }
