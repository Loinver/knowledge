"""只读源连接器的真实 SQLite 行为与远程驱动配置契约。"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path
from time import monotonic
from unittest.mock import MagicMock, Mock

import pytest
from app.connectors import sql
from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.domain import extraction_service, mapping_compiler, source_service
from app.models.extraction import ExtractionRun, GraphRevision
from sqlalchemy import Engine, event, inspect
from sqlalchemy.dialects.mysql import pymysql
from sqlalchemy.dialects.postgresql import psycopg2
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.orm import Session


@pytest.fixture()
def source_path(tmp_path: Path) -> Path:
    # URL 保留字符必须作为文件名处理，不能改变只读连接参数。
    path = tmp_path / "source ?#%.sqlite"
    with closing(sqlite3.connect(path)) as conn:
        conn.execute("CREATE TABLE records (id INTEGER PRIMARY KEY, value TEXT)")
        conn.execute("INSERT INTO records VALUES (1, 'example')")
        conn.execute('CREATE TABLE "odd""%name" (id INTEGER)')
        conn.commit()
    return path


def test_sqlite_reads_and_inspects_existing_file(source_path: Path) -> None:
    with (
        sql.readonly_engine("sqlite", {"database": str(source_path)}) as engine,
        engine.connect() as conn,
    ):
        assert conn.exec_driver_sql("PRAGMA query_only").scalar_one() == 1
        assert (
            conn.exec_driver_sql("SELECT value FROM records").scalar_one() == "example"
        )
        assert inspect(conn).get_pk_constraint("records")["constrained_columns"] == [
            "id"
        ]
        assert conn.execute(sql.select_source_rows('odd"%name', "main")).all() == []


@pytest.mark.parametrize("kind", ["postgresql", "mysql"])
@pytest.mark.parametrize("limit, offset", [(None, None), (20, None), (20, 3)])
def test_compiled_remote_identifiers_survive_dbapi_parameter_substitution(
    kind: str, limit: int | None, offset: int | None
) -> None:
    """真实方言编译及 DBAPI 格式替换后，表/schema 的 % 与引号必须原样保留。"""
    dialect = psycopg2.dialect() if kind == "postgresql" else pymysql.dialect()
    table_name = 'sales%2026"; DROP TABLE records; --`'
    schema_name = 'finance%2026"`'
    statement = sql.select_source_rows(
        table_name, schema_name, limit=limit, offset=offset
    )
    compiled = statement.compile(dialect=dialect)
    if compiled.positional:
        parameters = tuple(compiled.params[name] for name in compiled.positiontup)
    else:
        parameters = compiled.params
    # psycopg2 的 pyformat 与 PyMySQL 的 format 都消费一层百分号转义。
    executed_sql = str(compiled) % parameters
    if kind == "postgresql":
        expected_from = '"finance%2026""`"."sales%2026""; DROP TABLE records; --`"'
    else:
        expected_from = '`finance%2026"```.`sales%2026"; DROP TABLE records; --```'
    assert executed_sql.startswith(f"SELECT * \nFROM {expected_from}")
    assert "%%" not in executed_sql
    if limit is None:
        assert not compiled.params
    elif offset is None:
        assert executed_sql.endswith("LIMIT 20")
    elif kind == "postgresql":
        assert executed_sql.endswith("LIMIT 20 OFFSET 3")
    else:
        assert executed_sql.endswith("LIMIT 3, 20")


@pytest.mark.parametrize(
    "statement",
    [
        "CREATE TABLE forbidden (id INTEGER)",
        "CREATE TEMP TABLE forbidden (id INTEGER)",
        "INSERT INTO records VALUES (2, 'forbidden')",
        "UPDATE records SET value = 'forbidden'",
        "DELETE FROM records",
        "DROP TABLE records",
        "PRAGMA query_only = OFF",
        "PRAGMA writable_schema = ON",
        "ATTACH DATABASE ? AS attached",
    ],
)
def test_sqlite_rejects_writes_and_readonly_bypasses(
    source_path: Path, tmp_path: Path, statement: str
) -> None:
    attached = tmp_path / "must-not-exist.sqlite"
    params = (str(attached),) if statement.startswith("ATTACH") else ()
    with (
        sql.readonly_engine("sqlite", {"database": str(source_path)}) as engine,
        engine.connect() as conn,
    ):
        with pytest.raises(DBAPIError):
            conn.exec_driver_sql(statement, params)
        assert (
            conn.exec_driver_sql("SELECT value FROM records").scalar_one() == "example"
        )
        assert conn.exec_driver_sql("PRAGMA query_only").scalar_one() == 1
    assert not attached.exists()


def test_missing_sqlite_file_is_not_created_by_either_entry(tmp_path: Path) -> None:
    path = tmp_path / "missing.sqlite"
    result = source_service.test_connection("sqlite", {"database": str(path)})
    assert result == {"ok": False, "message": "source_unreachable", "table_count": None}
    with (
        pytest.raises(KGError) as exc,
        sql.readonly_engine("sqlite", {"database": str(path)}) as engine,
        engine.connect(),
    ):
        pass
    assert exc.value.code == ErrorCode.SOURCE_UNREACHABLE
    assert str(path) not in str(exc.value.params)
    assert not path.exists()


@pytest.mark.parametrize("fail", [False, True])
def test_connections_and_engine_are_released_on_all_exits(
    source_path: Path, monkeypatch: pytest.MonkeyPatch, fail: bool
) -> None:
    raw: sqlite3.Connection | None = None
    dispose = Mock()
    failed = False
    try:
        with sql.readonly_engine("sqlite", {"database": str(source_path)}) as engine:
            dispose = Mock(wraps=engine.dispose)
            monkeypatch.setattr(engine, "dispose", dispose)
            with engine.connect() as conn:
                raw = conn.connection.driver_connection
                if fail:
                    raise RuntimeError("private SQL and connection credentials")
    except KGError as exc:
        failed = True
        assert fail
        assert exc.code == ErrorCode.SOURCE_UNREACHABLE
        assert exc.params == {"reason": "source_unreachable"}
    assert failed is fail
    dispose.assert_called_once_with()
    assert raw is not None
    with pytest.raises(sqlite3.ProgrammingError):
        raw.execute("SELECT 1")


def test_connection_setup_failure_closes_raw_connection(
    source_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    opened: list[sqlite3.Connection] = []

    def fail_setup(connection: sqlite3.Connection, _record: object) -> None:
        opened.append(connection)
        raise RuntimeError("private connection configuration")

    monkeypatch.setattr(sql, "_configure_sqlite", fail_setup)
    with (
        pytest.raises(KGError) as exc,
        sql.readonly_engine("sqlite", {"database": str(source_path)}) as engine,
        engine.connect(),
    ):
        pass
    assert exc.value.code == ErrorCode.SOURCE_UNREACHABLE
    assert exc.value.params == {"reason": "source_unreachable"}
    assert len(opened) == 1
    with pytest.raises(sqlite3.ProgrammingError):
        opened[0].execute("SELECT 1")


def test_sqlite_query_timeout_includes_fetch_and_next_query_recovers(
    source_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sql, "QUERY_TIMEOUT_SECONDS", 0.02)
    with (
        sql.readonly_engine("sqlite", {"database": str(source_path)}) as engine,
        engine.connect() as conn,
    ):
        started = monotonic()
        result = conn.exec_driver_sql(
            "WITH RECURSIVE numbers(n) AS (VALUES(1) UNION ALL "
            "SELECT n + 1 FROM numbers WHERE n < 1000000) SELECT n FROM numbers"
        )
        with pytest.raises(OperationalError, match="interrupted"):
            result.fetchall()
        assert monotonic() - started < 2
        assert (
            conn.exec_driver_sql("SELECT value FROM records").scalar_one() == "example"
        )


def test_sqlite_lock_wait_is_bounded(
    source_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sql, "CONNECT_TIMEOUT_SECONDS", 0.02)
    with closing(sqlite3.connect(source_path)) as writer:
        writer.execute("BEGIN EXCLUSIVE")
        started = monotonic()
        with (
            pytest.raises(KGError) as exc,
            sql.readonly_engine("sqlite", {"database": str(source_path)}) as engine,
            engine.connect() as conn,
        ):
            conn.exec_driver_sql("SELECT * FROM records").fetchall()
        assert exc.value.code == ErrorCode.SOURCE_UNREACHABLE
        assert monotonic() - started < 2


@pytest.mark.parametrize("kind", ["postgresql", "mysql"])
def test_remote_urls_readonly_and_timeout_options(
    kind: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """仅验证驱动参数和初始化语句；不假定本机存在远程数据库服务。"""
    engine = Mock(spec=Engine)
    create = Mock(return_value=engine)
    listen = Mock()
    monkeypatch.setattr(sql, "create_engine", create)
    monkeypatch.setattr(sql.event, "listen", listen)
    credential = "p@ss:/?#%word"
    params = {"host": "example.org", "user": "user@name", "database": "db/name"}
    with sql.readonly_engine(kind, params, credential) as opened:
        assert opened is engine
    url = create.call_args.args[0]
    assert url.username == "user@name"
    assert url.password == credential
    assert url.host == "example.org"
    assert url.database == "db/name"
    options = create.call_args.kwargs["connect_args"]
    assert options["connect_timeout"] == sql.CONNECT_TIMEOUT_SECONDS
    assert create.call_args.kwargs["poolclass"] is sql.NullPool
    assert create.call_args.kwargs["hide_parameters"] is True
    if kind == "postgresql":
        assert "default_transaction_read_only=on" in options["options"]
        assert (
            f"statement_timeout={sql.QUERY_TIMEOUT_SECONDS * 1000}"
            in options["options"]
        )
    else:
        assert options["init_command"] == "SET SESSION TRANSACTION READ ONLY"
        assert options["read_timeout"] == sql.QUERY_TIMEOUT_SECONDS
        assert options["write_timeout"] == sql.CONNECT_TIMEOUT_SECONDS
        dbapi = MagicMock()
        listen.call_args.args[2](dbapi, None)
        dbapi.cursor.return_value.__enter__.return_value.execute.assert_called_once_with(
            f"SET SESSION MAX_EXECUTION_TIME = {sql.QUERY_TIMEOUT_SECONDS * 1000}"
        )
    engine.dispose.assert_called_once_with()


def test_connection_failure_never_exposes_raw_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        sql,
        "create_engine",
        Mock(side_effect=RuntimeError("postgresql://user:secret@example.org/private")),
    )
    assert source_service.test_connection("postgresql", {"password": "secret"}) == {
        "ok": False,
        "message": "source_unreachable",
        "table_count": None,
    }


@pytest.mark.parametrize("relation", [False, True])
def test_query_errors_do_not_leak_through_preview_or_quarantine(
    source_path: Path, relation: bool
) -> None:
    def fail_query(*_args: object) -> None:
        raise RuntimeError("private SQL and connection credentials")

    mapping = {"table": "records", "entity_type": "Record", "relation_type": "Related"}
    with sql.readonly_engine("sqlite", {"database": str(source_path)}) as engine:
        event.listen(engine, "before_cursor_execute", fail_query)
        compile_one = (
            mapping_compiler._compile_relation
            if relation
            else mapping_compiler._compile_entity
        )
        _, errors = compile_one(mapping, engine, "sqlite", {"records"}, 20)
        assert errors[0]["code"] == "query_failed"
        assert errors[0]["message"] == "source_query_failed"
        session = Mock(spec=Session)
        phase = (
            extraction_service._phase2_relation
            if relation
            else extraction_service._phase1_entity
        )
        counts = phase(
            session,
            ExtractionRun(id=1),
            GraphRevision(id=1),
            mapping,
            engine,
            {"records"},
            "https://example.org/",
            {},
        )
        assert counts[:2] == (0, 1)
        quarantine = session.add.call_args.args[0]
        assert quarantine.rule_id == "query_failed"
        assert quarantine.raw_value is None
