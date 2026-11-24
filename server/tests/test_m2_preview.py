"""受限样例预览集成测试（H-22）。"""

from __future__ import annotations

import pytest
from app.core.db import Base
from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.domain.metadata_service import capture_metadata
from app.domain.preview_service import preview_table
from app.domain.source_service import create_datasource
from app.schemas.datasource import DatasourceCreate
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker


def _make_source_db(path: str) -> None:
    eng = create_engine(f"sqlite:///{path}")
    with eng.connect() as conn:
        conn.execute(
            text(
                "CREATE TABLE enterprise ("
                "id INTEGER PRIMARY KEY, name TEXT, secret TEXT)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO enterprise (id, name, secret) "
                "VALUES (1, 'A', 'pwd-123'), (2, 'B', 'pwd-456')"
            )
        )
        conn.commit()


@pytest.fixture()
def session(tmp_path):
    url = f"sqlite:///{tmp_path}/kg.db"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    sf = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
    sess = sf()
    yield sess
    sess.close()
    Base.metadata.drop_all(engine)


@pytest.fixture()
def source_db(tmp_path):
    path = str(tmp_path / "source.db")
    _make_source_db(path)
    yield path


def _setup(session, source_db):
    ds = create_datasource(
        session,
        DatasourceCreate(
            name="demo",
            kind="sqlite",
            params={"database": source_db},
            credential="ignored",
        ),
    )
    session.commit()
    capture_metadata(session, ds.id)
    session.commit()
    return ds


def test_preview_returns_rows(session, source_db):
    ds = _setup(session, source_db)
    result = preview_table(session, ds.id, "enterprise", "main", limit=10, offset=0)
    assert result["table"] == "enterprise"
    assert result["total_returned"] == 2
    assert result["truncated"] is False
    col_names = [c["name"] for c in result["columns"]]
    assert "id" in col_names
    assert "name" in col_names


def test_preview_limit_caps_at_100(session, source_db):
    ds = _setup(session, source_db)
    result = preview_table(session, ds.id, "enterprise", "main", limit=999, offset=0)
    # 限制后 limit=100，但源库只有2行
    assert result["total_returned"] == 2


def test_preview_credentials_masked(session, source_db):
    """凭据/敏感字段不出现在预览结果（A15）。"""
    ds = _setup(session, source_db)
    result = preview_table(session, ds.id, "enterprise", "main", limit=10, offset=0)
    for row in result["rows"]:
        assert row.get("secret") == "***"
        assert "pwd-123" not in str(row)
        assert "pwd-456" not in str(row)


def test_preview_requires_metadata_snapshot(session, source_db):
    """无元数据快照时拒绝预览（先采集后预览）。"""
    ds = create_datasource(
        session,
        DatasourceCreate(name="nosnap", kind="sqlite", params={"database": source_db}),
    )
    session.commit()
    with pytest.raises(KGError) as exc:
        preview_table(session, ds.id, "enterprise", "main")
    assert exc.value.code == ErrorCode.INVALID_REQUEST


def test_preview_unknown_table_rejected(session, source_db):
    """表名不在快照里时拒绝（防任意表查询）。"""
    ds = _setup(session, source_db)
    with pytest.raises(KGError) as exc:
        preview_table(session, ds.id, "ghost_table", "main")
    assert exc.value.code == ErrorCode.RESOURCE_NOT_FOUND


def test_preview_rejects_write_keywords_in_tablename(session, source_db):
    """表名含写关键字时拒绝。"""
    ds = _setup(session, source_db)
    with pytest.raises(KGError) as exc:
        preview_table(session, ds.id, "enterprise; DROP TABLE x", "main")
    assert exc.value.code == ErrorCode.INVALID_REQUEST


def test_preview_offset_too_large(session, source_db):
    ds = _setup(session, source_db)
    with pytest.raises(KGError) as exc:
        preview_table(session, ds.id, "enterprise", "main", offset=99999)
    assert exc.value.code == ErrorCode.INVALID_REQUEST


def test_preview_not_persisted(session, source_db):
    """预览结果不入库：metadata_snapshot 表没有预览记录。"""
    from app.models.data_access import MetadataSnapshot

    ds = _setup(session, source_db)
    before = list(session.execute(_select_all(MetadataSnapshot)).scalars())
    preview_table(session, ds.id, "enterprise", "main")
    session.flush()
    after = list(session.execute(_select_all(MetadataSnapshot)).scalars())
    assert len(before) == len(after)


def _select_all(model):
    from sqlalchemy import select

    return select(model)
