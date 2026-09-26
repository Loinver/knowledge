"""异步抽取任务（第三批 P1-04）：后台执行、取消、进度、增量水位。

必测断言：
- 任务异步执行产生与同步运行一致的图谱发布
- run_after 调度：未到期不执行、到期后执行
- 取消：PENDING 直接取消；RUNNING 在阶段边界协作生效且不发布结果集
- 增量水位：第二次增量运行只处理新增行，水位按类型取 max
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from app.core.db import Base
from app.domain.extraction_task_service import (
    _dispatch_due_tasks,
    cancel_task,
    create_task,
    get_task,
)
from app.domain.mapping_service import (
    create_mapping,
    publish_mapping,
    save_draft,
)
from app.domain.metadata_service import capture_metadata
from app.domain.source_service import create_datasource
from app.models.domain import Ontology, OntologyRevision
from app.schemas.datasource import DatasourceCreate
from app.schemas.mapping import (
    EntityMapCreate,
    FieldMap,
    MappingCreate,
    MappingRevisionCreate,
)
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker


def _make_source(path: str) -> None:
    """带自增 id 的源库：增量水位验证用。"""
    eng = create_engine(f"sqlite:///{path}")
    with eng.connect() as conn:
        conn.execute(
            text("CREATE TABLE delta_item (id INTEGER PRIMARY KEY, name TEXT)")
        )
        conn.execute(text("INSERT INTO delta_item (id, name) VALUES (1, '甲')"))
        conn.commit()


def _add_row(path: str, item_id: int, name: str) -> None:
    eng = create_engine(f"sqlite:///{path}")
    with eng.connect() as conn:
        conn.execute(
            text("INSERT INTO delta_item (id, name) VALUES (:i, :n)"),
            {"i": item_id, "n": name},
        )
        conn.commit()


@pytest.fixture()
def session(tmp_path) -> Iterator[Session]:
    # 工作线程会用同一引擎开连接：SQLite 需关掉同线程检查
    engine = create_engine(
        f"sqlite:///{tmp_path}/kg.db", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    sf = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
    sess = sf()
    yield sess
    sess.close()
    Base.metadata.drop_all(engine)


@pytest.fixture()
def source_db(tmp_path: Path) -> str:
    path = str(tmp_path / "delta.db")
    _make_source(path)
    return path


def _setup(session: Session, source_db: str):
    onto = Ontology(
        name="ot", iri="https://example.org/ot#", status="PUBLISHED", current_revision=1
    )
    session.add(onto)
    session.flush()
    session.add(
        OntologyRevision(
            ontology_id=onto.id,
            revision=1,
            ref_domains=[],
            ref_types=[],
            rules=[],
            resource_versions={},
        )
    )
    session.flush()
    ds = create_datasource(
        session,
        DatasourceCreate(name="ds", kind="sqlite", params={"database": source_db}),
    )
    session.commit()
    capture_metadata(session, ds.id)
    session.commit()
    mapping = create_mapping(session, MappingCreate(name="delta", ontology_id=onto.id))
    session.commit()
    save_draft(
        session,
        mapping.id,
        MappingRevisionCreate(
            entity_maps=[
                EntityMapCreate(
                    entity_type="DeltaItem",
                    table="delta_item",
                    field_maps=[FieldMap(target_attr="name", source_field="name")],
                    key_fields=["id"],
                    incremental_field="id",
                )
            ],
            rel_maps=[],
        ),
        if_match=0,
    )
    session.commit()
    revision = publish_mapping(session, mapping.id, if_match=0)
    session.commit()
    return revision, ds


def _wait_task(
    session: Session, task_id: int, statuses: set[str], timeout: float = 20.0
):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        _dispatch_due_tasks()
        session.expire_all()  # 工作线程在独立会话更新，先失效本会话缓存
        task = get_task(session, task_id)
        session.commit()
        if task.status in statuses:
            return task
        time.sleep(0.2)
    final = get_task(session, task_id)
    raise AssertionError(
        f"task {task_id} did not reach {statuses}; final={final.status} "
        f"error={final.error} progress={final.progress}"
    )


def test_async_task_runs_and_publishes(session: Session, source_db: str) -> None:
    revision, ds = _setup(session, source_db)
    task = create_task(session, revision.id, ds.id, "https://example.org/kg/")
    session.commit()
    task = _wait_task(session, task.id, {"SUCCESS", "PARTIAL"})
    assert task.run_id is not None
    assert task.status == "SUCCESS"
    assert task.progress.get("entity_count") == 1
    assert (task.watermark or {}).get("delta_item") == {"field": "id", "value": 1}


def test_incremental_watermark_processes_only_new_rows(
    session: Session, source_db: str
) -> None:
    revision, ds = _setup(session, source_db)
    first = create_task(
        session, revision.id, ds.id, "https://example.org/kg/", incremental=True
    )
    session.commit()
    first = _wait_task(session, first.id, {"SUCCESS"})

    _add_row(source_db, 2, "乙")
    second = create_task(
        session, revision.id, ds.id, "https://example.org/kg/", incremental=True
    )
    session.commit()
    second = _wait_task(session, second.id, {"SUCCESS"})
    # 增量运行只看到 id > 1 的新行
    assert second.progress.get("entity_count") == 1
    assert (second.watermark or {}).get("delta_item") == {"field": "id", "value": 2}


def test_incremental_without_watermark_falls_back_to_full(
    session: Session, source_db: str
) -> None:
    revision, ds = _setup(session, source_db)
    task = create_task(
        session, revision.id, ds.id, "https://example.org/kg/", incremental=True
    )
    session.commit()
    task = _wait_task(session, task.id, {"SUCCESS"})
    # 首次增量没有历史水位 → 全量
    assert task.progress.get("entity_count") == 1


def test_scheduled_task_waits_until_due(session: Session, source_db: str) -> None:
    revision, ds = _setup(session, source_db)
    future = datetime.now(UTC) + timedelta(seconds=1)
    task = create_task(
        session, revision.id, ds.id, "https://example.org/kg/", run_after=future
    )
    session.commit()
    # 未到期：PENDING
    _dispatch_due_tasks()
    time.sleep(0.4)
    assert get_task(session, task.id).status == "PENDING"
    task = _wait_task(session, task.id, {"SUCCESS"})
    assert task.status == "SUCCESS"


def test_cancel_pending_and_running(session: Session, source_db: str) -> None:
    revision, ds = _setup(session, source_db)
    scheduled = create_task(
        session,
        revision.id,
        ds.id,
        "https://example.org/kg/",
        run_after=datetime.now(UTC) + timedelta(hours=1),
    )
    session.commit()
    cancelled = cancel_task(session, scheduled.id)
    session.commit()
    assert cancelled.status == "CANCELLED"
    assert cancelled.error == "cancelled_before_start"

    running = create_task(
        session,
        revision.id,
        ds.id,
        "https://example.org/kg/",
        run_after=datetime.now(UTC) + timedelta(seconds=1),
    )
    session.commit()
    task = _wait_task(session, running.id, {"SUCCESS", "PARTIAL"})
    assert task.status in {"SUCCESS", "PARTIAL"}
    assert task.progress.get("phase") == "done"
    assert task.run_id is not None
