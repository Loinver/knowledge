"""异步抽取任务（第三批 P1-04）：后台执行、取消、进度、增量水位。

必测断言：
- 任务异步执行产生与同步运行一致的图谱发布
- run_after 调度：未到期不执行、到期后执行
- 取消：PENDING 直接取消；RUNNING 在阶段边界协作生效且不发布结果集
- 增量水位：第二次增量运行只处理新增行，水位按类型取 max
"""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from app.core.db import Base
from app.core.errors import KGError
from app.domain import extraction_task_service as tasks
from app.domain.extraction_service import get_current_graph, start_run, switch_current
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
from app.models.data_access import Mapping
from app.models.domain import Ontology, OntologyRevision
from app.models.extraction import (
    EntityIdentity,
    ExtractionRun,
    ExtractionTask,
    FactEvidence,
    GraphRevision,
    GraphTriple,
)
from app.schemas.datasource import DatasourceCreate
from app.schemas.mapping import (
    EntityMapCreate,
    FieldMap,
    MappingCreate,
    MappingRevisionCreate,
    RelMapCreate,
)
from sqlalchemy import create_engine, func, select, text
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
    # Only one source row is read, but the published graph is a complete snapshot.
    assert second.progress.get("entity_count") == 2
    assert second.progress.get("new_entity_row_count") == 1
    assert (second.watermark or {}).get("delta_item") == {"field": "id", "value": 2}
    current = get_current_graph(session)
    assert current is not None
    second_graph = current.id
    entities = list(
        session.scalars(
            select(EntityIdentity).where(EntityIdentity.graph_revision_id == current.id)
        )
    )
    assert {item.attrs["name"] for item in entities} == {"甲", "乙"}
    inherited = session.scalar(
        select(FactEvidence).where(
            FactEvidence.graph_revision_id == current.id,
            FactEvidence.row_key == "1",
            FactEvidence.evidence_type == "ENTITY",
        )
    )
    assert inherited is not None and inherited.run_id == first.run_id
    assert inherited.mapping_revision_id == revision.id
    assert inherited.column_transforms[0]["column"] == "name"
    # A no-op does not replace current or yield a switchable incomplete graph.
    noop = create_task(
        session, revision.id, ds.id, "https://example.org/kg/", incremental=True
    )
    session.commit()
    noop = _wait_task(session, noop.id, {"SUCCESS"})
    assert noop.progress["no_op"] == 1
    assert noop.watermark == second.watermark
    assert get_current_graph(session).id == second_graph
    candidate = session.scalar(
        select(GraphRevision).where(GraphRevision.run_id == noop.run_id)
    )
    assert candidate is not None and not candidate.publishable
    with pytest.raises(KGError):
        switch_current(session, candidate.id)
    _add_row(source_db, 3, "丙")
    third = create_task(
        session, revision.id, ds.id, "https://example.org/kg/", incremental=True
    )
    session.commit()
    third = _wait_task(session, third.id, {"SUCCESS"})
    assert third.progress["entity_count"] == 3
    assert third.progress["new_entity_row_count"] == 1
    assert third.watermark["delta_item"]["value"] == 3


def test_first_incremental_records_explicit_full_initialization(
    session: Session, source_db: str
) -> None:
    revision, ds = _setup(session, source_db)
    task = create_task(
        session, revision.id, ds.id, "https://example.org/kg/", incremental=True
    )
    session.commit()
    task = _wait_task(session, task.id, {"SUCCESS"})
    # Initialization is visible in the frozen execution configuration.
    assert task.progress.get("entity_count") == 1
    assert (
        session.get(ExtractionRun, task.run_id).cfg_snapshot["incremental"]["mode"]
        == "INITIAL_FULL"
    )


def test_incremental_preserves_unchanged_table_and_links_new_to_old_endpoint(
    session: Session, source_db: str
) -> None:
    revision, ds = _setup(session, source_db)
    source = create_engine(f"sqlite:///{source_db}")
    with source.begin() as conn:
        conn.execute(
            text("CREATE TABLE department (id INTEGER PRIMARY KEY, name TEXT)")
        )
        conn.execute(text("INSERT INTO department VALUES (1, '研发')"))
        conn.execute(
            text(
                "ALTER TABLE delta_item ADD COLUMN department_id INTEGER "
                "REFERENCES department(id)"
            )
        )
        conn.execute(text("UPDATE delta_item SET department_id=1"))
    capture_metadata(session, ds.id)
    mapping = create_mapping(
        session,
        MappingCreate(
            name="delta-rel",
            ontology_id=session.get(Mapping, revision.mapping_id).ontology_id,
        ),
    )
    save_draft(
        session,
        mapping.id,
        MappingRevisionCreate(
            entity_maps=[
                EntityMapCreate.model_validate(revision.entity_maps[0]),
                EntityMapCreate(
                    entity_type="Department",
                    table="department",
                    key_fields=["id"],
                    incremental_field="id",
                    field_maps=[FieldMap(target_attr="name", source_field="name")],
                ),
            ],
            rel_maps=[
                RelMapCreate(
                    relation_type="WorksFor",
                    mode="FK",
                    table="delta_item",
                    fk_field="department_id",
                )
            ],
        ),
        if_match=0,
    )
    revision = publish_mapping(session, mapping.id, if_match=0)
    session.commit()
    first = create_task(
        session, revision.id, ds.id, "https://example.org/kg/", incremental=True
    )
    session.commit()
    first = _wait_task(session, first.id, {"SUCCESS", "FAILED"})
    assert first.status == "SUCCESS", first.error
    with source.begin() as conn:
        conn.execute(text("INSERT INTO delta_item VALUES (2, '乙', 1)"))
    second = create_task(
        session, revision.id, ds.id, "https://example.org/kg/", incremental=True
    )
    session.commit()
    second = _wait_task(session, second.id, {"SUCCESS", "FAILED"})
    assert second.status == "SUCCESS", second.error
    assert second.progress["entity_count"] == 3
    assert second.progress["triple_count"] == 2
    assert second.progress["new_entity_row_count"] == 1
    assert second.watermark["department"] == {"field": "id", "value": 1}
    graph = get_current_graph(session)
    edges = list(
        session.scalars(
            select(GraphTriple).where(GraphTriple.graph_revision_id == graph.id)
        )
    )
    assert {edge.object_ for edge in edges} == {"https://example.org/kg/Department/1"}
    assert {edge.subject for edge in edges} == {
        "https://example.org/kg/DeltaItem/1",
        "https://example.org/kg/DeltaItem/2",
    }
    source.dispose()


def test_incremental_big_integer_watermark_and_failure_preserve_current(
    session: Session, source_db: str
) -> None:
    revision, ds = _setup(session, source_db)
    _add_row(source_db, 9007199254740992, "大一")
    first = create_task(
        session, revision.id, ds.id, "https://example.org/kg/", incremental=True
    )
    session.commit()
    first = _wait_task(session, first.id, {"SUCCESS"})
    _add_row(source_db, 9007199254740993, "大二")
    second = create_task(
        session, revision.id, ds.id, "https://example.org/kg/", incremental=True
    )
    session.commit()
    second = _wait_task(session, second.id, {"SUCCESS"})
    assert second.watermark["delta_item"]["value"] == 9007199254740993
    graph_id = get_current_graph(session).id
    # Corrupted historical chains must never silently fall back to older data.
    second.watermark = {}
    session.commit()
    third = create_task(
        session, revision.id, ds.id, "https://example.org/kg/", incremental=True
    )
    session.commit()
    third = _wait_task(session, third.id, {"FAILED", "SUCCESS"})
    assert third.status == "FAILED"
    assert third.error == "incremental_watermark_mismatch"
    assert get_current_graph(session).id == graph_id


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


@pytest.mark.parametrize(
    "bad_watermark", [{}, {"delta_item": {"field": "id", "value": 99}}]
)
def test_incremental_rejects_watermark_drift(
    session: Session, source_db: str, bad_watermark: dict
) -> None:
    revision, ds = _setup(session, source_db)
    first = create_task(
        session, revision.id, ds.id, "https://example.org/kg/", incremental=True
    )
    session.commit()
    first = _wait_task(session, first.id, {"SUCCESS", "FAILED"})
    assert first.status == "SUCCESS"
    current_id = get_current_graph(session).id
    first.watermark = bad_watermark
    session.commit()
    _add_row(source_db, 2, "second")
    _add_row(source_db, 100, "last")
    second = create_task(
        session, revision.id, ds.id, "https://example.org/kg/", incremental=True
    )
    session.commit()
    second = _wait_task(session, second.id, {"SUCCESS", "FAILED"})
    assert second.status == "FAILED"
    assert second.error == "incremental_watermark_mismatch"
    assert second.watermark is None
    assert get_current_graph(session).id == current_id


@pytest.mark.parametrize("mode", ["JUNCTION", "ASSOCIATIVE"])
@pytest.mark.parametrize("candidate", [False, True])
def test_incremental_rejects_relation_business_key(
    session: Session, source_db: str, mode: str, candidate: bool
) -> None:
    revision, ds = _setup(session, source_db)
    current = start_run(session, revision.id, ds.id, "https://example.org/kg/")
    session.commit()
    current_id = get_current_graph(session).id
    endpoint = {"field": "id", "ref_table": "delta_item", "ref_field": "name"}
    revision.rel_maps = [
        {
            "mode": mode,
            "table": "delta_item",
            "relation_type": "Link",
            "source": {"candidates": [endpoint]} if candidate else endpoint,
            "target": {"field": "id", "ref_table": "delta_item", "ref_field": "id"},
        }
    ]
    session.commit()
    task = create_task(
        session, revision.id, ds.id, "https://example.org/kg/", incremental=True
    )
    session.commit()
    task = _wait_task(session, task.id, {"SUCCESS", "FAILED"})
    assert task.status == "FAILED"
    assert task.error == "incremental_endpoint_key_unsupported"
    assert task.watermark is None
    assert get_current_graph(session).id == current_id
    assert get_current_graph(session).run_id == current.id


def test_incremental_rejects_duplicate_entity_type_across_tables(
    session: Session, source_db: str
) -> None:
    revision, ds = _setup(session, source_db)
    source = create_engine(f"sqlite:///{source_db}")
    with source.begin() as conn:
        conn.execute(
            text("CREATE TABLE other_item (id INTEGER PRIMARY KEY, name TEXT)")
        )
        conn.execute(text("INSERT INTO other_item VALUES (1, 'OTHER')"))
    capture_metadata(session, ds.id)
    revision.entity_maps = [
        *revision.entity_maps,
        {**revision.entity_maps[0], "table": "other_item"},
    ]
    session.commit()
    task = create_task(
        session, revision.id, ds.id, "https://example.org/kg/", incremental=True
    )
    session.commit()
    task = _wait_task(session, task.id, {"SUCCESS", "FAILED"})
    assert task.status == "FAILED"
    assert task.error == "incremental_duplicate_entity_type"
    assert task.watermark is None
    assert session.scalar(select(func.count()).select_from(GraphRevision)) == 0
    source.dispose()


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


@pytest.mark.parametrize("phase", ["entities", "relations", "rules", "derivation"])
def test_running_is_visible_cancel_keeps_run_and_previous_graph(
    session: Session, source_db: str, monkeypatch: pytest.MonkeyPatch, phase: str
) -> None:
    monkeypatch.setattr(tasks, "_ensure_scheduler", lambda: None)
    revision, ds = _setup(session, source_db)
    previous_run = start_run(session, revision.id, ds.id)
    session.commit()
    previous_graph = get_current_graph(session)
    assert previous_graph is not None
    previous_graph_id = previous_graph.id
    task = create_task(session, revision.id, ds.id, "https://example.org/kg/")
    session.commit()
    engine = session.get_bind()
    reached = threading.Event()
    release = threading.Event()

    def controlled_start(*args: object, **kwargs: object) -> ExtractionRun:
        progress = kwargs["progress"]

        def checkpoint(current: str, extra: dict) -> None:
            progress(current, extra)  # type: ignore[operator]
            if current == phase:
                reached.set()
                assert release.wait(10)

        kwargs["progress"] = checkpoint
        return start_run(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(tasks, "start_run", controlled_start)
    tasks._submit(task.id, engine)
    try:
        assert reached.wait(10)
        with Session(engine) as observer:
            assert get_task(observer, task.id).status == "RUNNING"
            cancel_task(observer, task.id)
            observer.commit()
        # Repeated dispatch while the worker is paused cannot enqueue duplicates.
        for _ in range(3):
            tasks._dispatch_due_tasks()
    finally:
        release.set()
    finished = _wait_task(session, task.id, {"CANCELLED", "FAILED", "SUCCESS"})
    assert finished.status == "CANCELLED", finished.error
    assert finished.run_id is not None and finished.run_id != previous_run.id
    run = session.get(ExtractionRun, finished.run_id)
    assert run is not None and run.status == "CANCELLED"
    assert get_current_graph(session).id == previous_graph_id
    assert session.scalar(select(func.count()).select_from(ExtractionRun)) == 2


def test_duplicate_workers_atomically_claim_once(
    session: Session, source_db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tasks, "_ensure_scheduler", lambda: None)
    revision, ds = _setup(session, source_db)
    task = create_task(session, revision.id, ds.id, "https://example.org/kg/")
    session.commit()
    engine = session.get_bind()
    workers = [
        threading.Thread(
            target=tasks._run_task, args=(task.id, threading.Event(), engine)
        )
        for _ in range(2)
    ]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(10)
        assert not worker.is_alive()
    session.expire_all()
    assert get_task(session, task.id).status == "SUCCESS"
    assert session.scalar(select(func.count()).select_from(ExtractionRun)) == 1
    assert session.scalar(select(func.count()).select_from(ExtractionTask)) == 1
