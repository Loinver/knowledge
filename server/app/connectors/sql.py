"""源库 SQL 连接：只读、限时，并在每次操作后释放连接资源。"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from time import monotonic
from typing import Any

from sqlalchemy import (
    URL,
    Engine,
    Select,
    create_engine,
    event,
    literal_column,
    quoted_name,
    select,
    table,
)
from sqlalchemy.pool import NullPool

from app.core.error_codes import ErrorCode
from app.core.errors import KGError

CONNECT_TIMEOUT_SECONDS = 5
QUERY_TIMEOUT_SECONDS = 10

_SQLITE_READ_ACTIONS = {
    sqlite3.SQLITE_SELECT,
    sqlite3.SQLITE_READ,
    sqlite3.SQLITE_FUNCTION,
    sqlite3.SQLITE_TRANSACTION,
    sqlite3.SQLITE_SAVEPOINT,
    sqlite3.SQLITE_RECURSIVE,
}
_SQLITE_METADATA_PRAGMAS = {
    "table_info",
    "table_xinfo",
    "foreign_key_list",
    "index_list",
    "index_info",
    "index_xinfo",
}
_SQLITE_VALUE_PRAGMAS = {
    "database_list",
    "table_list",
    "query_only",
    "read_uncommitted",
    "schema_version",
}


def _authorize_sqlite(
    action: int,
    first: str | None,
    second: str | None,
    _database: str | None,
    _trigger: str | None,
) -> int:
    if action == sqlite3.SQLITE_PRAGMA:
        name = (first or "").lower()
        allowed = name in _SQLITE_METADATA_PRAGMAS or (
            name in _SQLITE_VALUE_PRAGMAS and second is None
        )
    else:
        allowed = action in _SQLITE_READ_ACTIONS and not (
            action == sqlite3.SQLITE_FUNCTION
            and (second or "").lower() in {"load_extension", "writefile"}
        )
    return sqlite3.SQLITE_OK if allowed else sqlite3.SQLITE_DENY


def _configure_sqlite(connection: sqlite3.Connection, _record: object) -> None:
    connection.execute("PRAGMA query_only = ON").close()
    connection.set_authorizer(_authorize_sqlite)


def _sqlite_query_deadline(
    _connection: object,
    cursor: sqlite3.Cursor,
    _statement: str,
    _parameters: object,
    _context: object,
    _executemany: bool,
) -> None:
    # 保留到 fetch 完成；after_cursor_execute 时结果可能还没读完。
    deadline = monotonic() + QUERY_TIMEOUT_SECONDS
    cursor.connection.set_progress_handler(lambda: int(monotonic() >= deadline), 1000)


def _configure_mysql(connection: Any, _record: object) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            f"SET SESSION MAX_EXECUTION_TIME = {QUERY_TIMEOUT_SECONDS * 1000}"
        )


def _connection_options(
    kind: str, params: dict, credential: str | None
) -> tuple[URL, dict]:
    if kind == "sqlite":
        database = params.get("database", params.get("path"))
        if not isinstance(database, str) or not database or database == ":memory:":
            raise KGError(
                ErrorCode.INVALID_REQUEST, {"reason": "invalid_source_config"}
            )
        # as_uri 转义路径中的 ?/#/%，不能通过路径注入 mode=rw 等 URI 参数。
        uri = Path(database).expanduser().resolve().as_uri()
        return URL.create(
            "sqlite", database=uri, query={"mode": "ro", "uri": "true"}
        ), {
            "timeout": CONNECT_TIMEOUT_SECONDS,
        }
    if kind not in {"postgresql", "mysql"}:
        raise KGError(ErrorCode.INVALID_REQUEST, {"reason": "unsupported_source_kind"})
    url = URL.create(
        "postgresql+psycopg2" if kind == "postgresql" else "mysql+pymysql",
        username=params.get("user", ""),
        password=credential if credential is not None else params.get("password", ""),
        host=params.get("host", "localhost"),
        port=int(params.get("port", 5432 if kind == "postgresql" else 3306)),
        database=params.get("database", ""),
    )
    if kind == "postgresql":
        return url, {
            "connect_timeout": CONNECT_TIMEOUT_SECONDS,
            "options": (
                "-c default_transaction_read_only=on "
                f"-c statement_timeout={QUERY_TIMEOUT_SECONDS * 1000}"
            ),
        }
    return url, {
        "connect_timeout": CONNECT_TIMEOUT_SECONDS,
        "read_timeout": QUERY_TIMEOUT_SECONDS,
        "write_timeout": CONNECT_TIMEOUT_SECONDS,
        "init_command": "SET SESSION TRANSACTION READ ONLY",
    }


@contextmanager
def readonly_engine(
    kind: str, params: dict, credential: str | None = None
) -> Iterator[Engine]:
    """所有源库入口共用此边界；驱动失败只暴露稳定错误码。"""
    engine: Engine | None = None
    try:
        try:
            url, connect_args = _connection_options(kind, params, credential)
            engine = create_engine(
                url,
                connect_args=connect_args,
                poolclass=NullPool,
                hide_parameters=True,
            )
            if kind == "sqlite":
                event.listen(engine, "connect", _configure_sqlite)
                event.listen(engine, "before_cursor_execute", _sqlite_query_deadline)
            elif kind == "mysql":
                event.listen(engine, "connect", _configure_mysql)
            yield engine
        finally:
            if engine is not None:
                engine.dispose()
    except KGError:
        raise
    except Exception:
        raise KGError(
            ErrorCode.SOURCE_UNREACHABLE, {"reason": "source_unreachable"}
        ) from None


def select_source_rows(
    table_name: str,
    schema: str,
    *,
    limit: int | None = None,
    offset: int | None = None,
) -> Select[Any]:
    """保持原始标识符，由执行时的方言统一转义一次。"""
    source = table(
        quoted_name(table_name, True),
        schema=quoted_name(schema, True) if schema and schema != "main" else None,
    )
    statement: Select[Any] = select(literal_column("*")).select_from(source)
    if limit is not None:
        statement = statement.limit(limit)
    if offset is not None:
        statement = statement.offset(offset)
    return statement
