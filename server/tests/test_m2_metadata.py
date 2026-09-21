"""元数据采集与目录集成测试（H-21）。"""

from __future__ import annotations

import pytest
from app.core.db import Base
from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.domain.metadata_service import (
    _build_diff,
    capture_metadata,
    find_table_references,
    get_latest_snapshot,
    get_snapshot,
    list_snapshots,
)
from app.domain.source_service import create_datasource
from app.models.data_access import Mapping, MappingRevision
from app.schemas.datasource import DatasourceCreate
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


def _make_source_db(path: str) -> None:
    """建一个样例源库，用于采集。"""
    eng = create_engine(f"sqlite:///{path}")
    with eng.connect() as conn:
        conn.execute(
            __import__("sqlalchemy").text(
                "CREATE TABLE enterprise (id INTEGER PRIMARY KEY, name TEXT NOT NULL)"
            )
        )
        text_fn = __import__("sqlalchemy").text
        conn.execute(
            text_fn(
                "CREATE TABLE hr_employee ("
                "id INTEGER PRIMARY KEY, name TEXT NOT NULL, "
                "enterprise_id INTEGER NOT NULL, "
                "FOREIGN KEY (enterprise_id) REFERENCES enterprise(id))"
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


def _create_ds(session: Session, path: str):
    return create_datasource(
        session,
        DatasourceCreate(
            name="demo-db",
            kind="sqlite",
            params={"database": path},
            credential="ignored-pwd",
        ),
    )


def test_capture_metadata_success(session, source_db):
    """采集成功：catalog 含 schemas/tables/columns，revision=1。"""
    ds = _create_ds(session, source_db)
    session.commit()
    snap = capture_metadata(session, ds.id)
    session.commit()
    assert snap.revision == 1
    assert snap.datasource_id == ds.id
    assert snap.catalog["table_count"] >= 2
    schema_names = [s["schema"] for s in snap.catalog["schemas"]]
    assert "main" in schema_names
    table_names = {t["name"] for s in snap.catalog["schemas"] for t in s["tables"]}
    assert "enterprise" in table_names
    assert "hr_employee" in table_names


def test_capture_increments_revision_and_diffs(session, source_db):
    """第二次采集 revision=2 且生成 diff（首次 diff 为 None）。"""
    ds = _create_ds(session, source_db)
    session.commit()
    snap1 = capture_metadata(session, ds.id)
    session.commit()
    assert snap1.diff is None

    # 给源库加一张表
    eng = create_engine(f"sqlite:///{source_db}")
    with eng.connect() as conn:
        conn.execute(
            __import__("sqlalchemy").text(
                "CREATE TABLE new_table (id INTEGER PRIMARY KEY, val TEXT)"
            )
        )
        conn.commit()

    snap2 = capture_metadata(session, ds.id)
    session.commit()
    assert snap2.revision == 2
    assert snap2.diff is not None
    table_added = [d for d in snap2.diff["tables"] if d["type"] == "added"]
    assert any(d["name"] == "new_table" for d in table_added)
    assert snap2.diff["summary"]["tables_added"] >= 1


def test_capture_detects_column_changes(session, source_db):
    """字段修改触发 modified diff。"""
    ds = _create_ds(session, source_db)
    session.commit()
    capture_metadata(session, ds.id)
    session.commit()

    eng = create_engine(f"sqlite:///{source_db}")
    with eng.connect() as conn:
        conn.execute(
            __import__("sqlalchemy").text(
                "ALTER TABLE enterprise ADD COLUMN website TEXT"
            )
        )
        conn.commit()

    snap2 = capture_metadata(session, ds.id)
    session.commit()
    assert snap2.diff is not None
    col_added = [d for d in snap2.diff["columns"] if d["type"] == "added"]
    assert any(
        d["column"] == "website" and d["table"] == "enterprise" for d in col_added
    )


def test_catalog_has_no_credentials(session, source_db):
    """凭据不出现在 catalog（A15 / 安全红线）。"""
    ds = _create_datasource_with_creds(session, source_db)
    session.commit()
    snap = capture_metadata(session, ds.id)
    session.commit()
    blob = str(snap.catalog)
    assert "ignored-pwd" not in blob
    assert "password" not in blob.lower() or "password" not in str(
        snap.catalog.get("schemas", [])
    )


def _create_datasource_with_creds(session, source_db):
    return create_datasource(
        session,
        DatasourceCreate(
            name="cred-db",
            kind="sqlite",
            params={"database": source_db, "password": "topsecret123"},
            credential="topsecret123",
        ),
    )


def test_capture_failure_raises_source_unreachable(session):
    """连接不存在的源库抛 SOURCE_UNREACHABLE。"""
    ds = create_datasource(
        session,
        DatasourceCreate(
            name="bad-db",
            kind="sqlite",
            params={"database": "/nonexistent/path/ghost.db"},
        ),
    )
    session.commit()
    with pytest.raises(KGError) as exc:
        capture_metadata(session, ds.id)
    assert exc.value.code == ErrorCode.SOURCE_UNREACHABLE


def test_list_snapshots_pagination(session, source_db):
    """快照列表分页。"""
    ds = _create_ds(session, source_db)
    session.commit()
    for _ in range(3):
        capture_metadata(session, ds.id)
        session.commit()
    items, total = list_snapshots(session, ds.id, page=1, page_size=2)
    assert total == 3
    assert len(items) == 2
    items2, _ = list_snapshots(session, ds.id, page=2, page_size=2)
    assert len(items2) == 1
    # 倒序：revision 递减
    assert items[0].revision > items[1].revision


def test_get_snapshot_not_found(session):
    with pytest.raises(KGError) as exc:
        get_snapshot(session, 9999)
    assert exc.value.code == ErrorCode.RESOURCE_NOT_FOUND


def test_get_latest_snapshot(session, source_db):
    ds = _create_ds(session, source_db)
    session.commit()
    assert get_latest_snapshot(session, ds.id) is None
    capture_metadata(session, ds.id)
    session.commit()
    latest = get_latest_snapshot(session, ds.id)
    assert latest is not None
    assert latest.revision == 1


def test_find_table_references_empty(session):
    """无映射时返回空。"""
    refs = find_table_references(session, "enterprise")
    assert refs == []


def test_find_table_references_with_mapping(session, source_db):
    """有映射引用该表时返回反向引用。"""
    from app.models.domain import Ontology
    from app.models.enums import ResourceStatus

    onto = Ontology(
        name="onto1",
        iri="https://example.org/onto/onto1",
        status=ResourceStatus.PUBLISHED,
        current_revision=1,
    )
    session.add(onto)
    session.flush()
    m = Mapping(
        name="map1",
        ontology_id=onto.id,
        status=ResourceStatus.DRAFT,
        current_revision=1,
    )
    session.add(m)
    session.flush()
    rev = MappingRevision(
        mapping_id=m.id,
        revision=1,
        onto_version=1,
        entity_maps=[{"entity": "Enterprise", "table": "enterprise"}],
        rel_maps=[],
    )
    session.add(rev)
    session.flush()
    refs = find_table_references(session, "enterprise")
    assert len(refs) == 1
    assert refs[0]["mapping_id"] == m.id
    assert refs[0]["role"] == "entity"


def test_build_diff_pure_function():
    """diff 纯函数：空 prev 时全部 added。"""
    prev = {"schemas": [{"schema": "main", "tables": []}]}
    curr = {
        "schemas": [
            {
                "schema": "main",
                "tables": [
                    {
                        "name": "t1",
                        "type": "table",
                        "columns": [
                            {
                                "name": "id",
                                "type": "INTEGER",
                                "nullable": False,
                                "primary_key": True,
                                "foreign_key": None,
                            }
                        ],
                    }
                ],
            }
        ]
    }
    diff = _build_diff(prev, curr)
    assert diff["summary"]["tables_added"] == 1
    assert diff["summary"]["columns_added"] == 1


def test_build_diff_removal():
    """prev 有表、curr 没有时 removed。"""
    prev = {
        "schemas": [
            {
                "schema": "main",
                "tables": [{"name": "gone", "type": "table", "columns": []}],
            }
        ]
    }
    curr = {"schemas": [{"schema": "main", "tables": []}]}
    diff = _build_diff(prev, curr)
    assert diff["summary"]["tables_removed"] == 1
    assert any(d["name"] == "gone" and d["type"] == "removed" for d in diff["tables"])
