"""异步抽取任务（第三批 P1-04）：后台执行、取消、调度与增量水位。

执行模型：进程内线程池（默认 2 并发）+ 调度线程轮询 PENDING 任务。
任务在阶段边界协作式取消（ExtractionCancelledError），失败不发布结果集；
SUCCESS/PARTIAL 后按来源表记录增量字段最大值，供下次增量运行过滤。
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import Engine, func, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.core.db import bound_scope
from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.domain.extraction_incremental import invalid_incremental
from app.domain.extraction_service import (
    ExtractionCancelledError,
    _publish_graph_revision,
    start_run,
)
from app.models.data_access import MappingRevision
from app.models.enums import RunResult
from app.models.extraction import ExtractionRun, ExtractionTask, GraphRevision

_POLL_SECONDS = 2.0
_MAX_WORKERS = 2

_executor = ThreadPoolExecutor(
    max_workers=_MAX_WORKERS, thread_name_prefix="kg-extraction"
)


@dataclass
class _TaskControl:
    cancel: threading.Event
    lock: threading.RLock = field(default_factory=threading.RLock)
    finished: bool = False


_controls: dict[tuple[Engine, int], _TaskControl] = {}
_runtime_lock = threading.Lock()
# 任务归属引擎：随创建会话注册（生产为全局单引擎；测试为各库内存/文件引擎）。
_engines: set[Engine] = set()
# 运行中任务的实时进度（进程内）：SQLite 下跨连接写进度会与工作事务抢锁，
# 因此进度驻留内存，任务结束前的最终计数以 run.counts 落库为准。
_progress_memory: dict[tuple[Engine, int], dict] = {}
_scheduler_started = threading.Event()
_scheduler_lock = threading.Lock()


def create_task(
    session: Session,
    mapping_revision_id: int,
    datasource_id: int,
    namespace: str,
    *,
    incremental: bool = False,
    run_after: datetime | None = None,
) -> ExtractionTask:
    """创建任务并提交执行（run_after 非空时由调度线程到期执行）。"""
    rev = session.get(MappingRevision, mapping_revision_id)
    if rev is None:
        raise KGError(
            ErrorCode.RESOURCE_NOT_FOUND, {"mapping_revision_id": mapping_revision_id}
        )
    if rev.revision == 0:
        raise KGError(
            ErrorCode.VALIDATION_VIOLATION,
            {"reason": "cannot_run_draft", "revision": mapping_revision_id},
        )
    task = ExtractionTask(
        mapping_revision_id=mapping_revision_id,
        datasource_id=datasource_id,
        namespace=namespace,
        status="PENDING",
        incremental=incremental,
        run_after=run_after,
        progress={},
    )
    session.add(task)
    session.flush()
    bind = session.get_bind()
    assert isinstance(bind, Engine)
    _engines.add(bind)
    # 提交后由调度线程统一分发（含立即执行的任务，轮询间隔见 _POLL_SECONDS）；
    # 在创建事务提交前直接投递会读不到未提交行。
    _ensure_scheduler()
    return task


def get_task(session: Session, task_id: int) -> ExtractionTask:
    task = session.get(ExtractionTask, task_id)
    if task is None:
        raise KGError(ErrorCode.RESOURCE_NOT_FOUND, {"task_id": task_id})
    return task


def list_tasks(
    session: Session, page: int = 1, page_size: int = 50
) -> tuple[list[ExtractionTask], int]:
    stmt = select(ExtractionTask).order_by(ExtractionTask.id.desc())
    total = session.scalar(select(func.count()).select_from(ExtractionTask)) or 0
    items = list(
        session.execute(stmt.offset((page - 1) * page_size).limit(page_size)).scalars()
    )
    return items, total


def cancel_task(session: Session, task_id: int) -> ExtractionTask:
    """取消任务：PENDING 直接取消；RUNNING 置协作标志，阶段边界生效。"""
    task = get_task(session, task_id)
    if task.status == "PENDING":
        changed = session.scalar(
            update(ExtractionTask)
            .where(ExtractionTask.id == task_id, ExtractionTask.status == "PENDING")
            .values(
                status="CANCELLED",
                finished_at=datetime.now(UTC),
                error="cancelled_before_start",
            )
            .returning(ExtractionTask.id)
        )
        session.refresh(task)
        if changed is not None:
            return task
    if task.status == "RUNNING":
        bind = session.get_bind()
        assert isinstance(bind, Engine)
        with _runtime_lock:
            control = _controls.get((bind, task.id))
        if control is None:
            raise KGError(
                ErrorCode.INVALID_REQUEST,
                {"reason": "task_worker_not_available", "task_id": task.id},
            )
        with control.lock:
            if not control.finished:
                control.cancel.set()
                return task
    raise KGError(
        ErrorCode.VALIDATION_VIOLATION,
        {"reason": "task_not_cancellable", "status": task.status, "task_id": task.id},
    )


def _submit(task_id: int, engine: Engine) -> None:
    key = (engine, task_id)
    with _runtime_lock:
        if key in _controls:
            return
        control = _TaskControl(threading.Event())
        _controls[key] = control
    try:
        _executor.submit(_run_task, task_id, control.cancel, engine)
    except Exception:
        with _runtime_lock:
            _controls.pop(key, None)
        raise


def _ensure_scheduler() -> None:
    """调度线程懒启动：进程内单例，轮询到期任务。"""
    if _scheduler_started.is_set():
        return
    with _scheduler_lock:
        if _scheduler_started.is_set():
            return

        def _loop() -> None:
            while True:
                try:
                    _dispatch_due_tasks()
                except Exception:  # 调度器不退出，单次失败只记录
                    import logging

                    logging.getLogger(__name__).warning(
                        "task scheduler dispatch failed", exc_info=True
                    )
                threading.Event().wait(_POLL_SECONDS)

        threading.Thread(target=_loop, name="kg-task-scheduler", daemon=True).start()
        _scheduler_started.set()


def _dispatch_due_tasks() -> None:
    """把到期 PENDING 任务提交线程池。

    调度语义：run_after 为空视为立即执行；非空则到期后执行。
    已提交（RUNNING）任务不再出现在 PENDING 集合，不会重复分发。
    """
    now = datetime.now(UTC)
    for engine in list(_engines):
        try:
            with sessionmaker(bind=engine, expire_on_commit=False)() as session:
                due = list(
                    session.scalars(
                        select(ExtractionTask.id).where(
                            ExtractionTask.status == "PENDING",
                            (ExtractionTask.run_after.is_(None))
                            | (ExtractionTask.run_after <= now),
                        )
                    )
                )
        except Exception:
            # 单个引擎不可用（如测试库已析构）不影响其他引擎的分发
            continue
        for task_id in due:
            _submit(task_id, engine)


def _load_incremental_base(
    session: Session, task: ExtractionTask
) -> tuple[int | None, dict | None]:
    """增量运行的上次水位：同 (mapping, datasource) 最近成功任务的写出水。"""
    if not task.incremental:
        return None, None
    previous = session.execute(
        select(ExtractionTask, ExtractionRun, GraphRevision)
        .join(ExtractionRun, ExtractionRun.id == ExtractionTask.run_id)
        .join(GraphRevision, GraphRevision.run_id == ExtractionRun.id)
        .where(
            ExtractionTask.mapping_revision_id == task.mapping_revision_id,
            ExtractionTask.datasource_id == task.datasource_id,
            ExtractionTask.namespace == task.namespace,
            ExtractionTask.status == "SUCCESS",
            ExtractionRun.status == RunResult.SUCCESS,
            GraphRevision.publishable.is_(True),
            ExtractionTask.id != task.id,
        )
        .order_by(ExtractionTask.finished_at.desc(), ExtractionTask.id.desc())
        .limit(1)
    ).first()
    if previous is None:
        return None, None
    predecessor, run, graph = previous
    if (
        predecessor.incremental
        and (run.cfg_snapshot.get("incremental") or {}).get("version") != 1
    ):
        raise invalid_incremental("incremental_base_requires_full_rebuild")
    frozen_watermark = run.cfg_snapshot.get("output_watermarks")
    if (
        not isinstance(frozen_watermark, dict)
        or frozen_watermark != predecessor.watermark
    ):
        raise invalid_incremental("incremental_watermark_mismatch")
    return graph.id, frozen_watermark


def _run_task(task_id: int, cancel_flag: threading.Event, engine: Engine) -> None:
    """Claim in a short transaction; serialize cancellation with the final commit."""
    key = (engine, task_id)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with _runtime_lock:
        control = _controls.setdefault(key, _TaskControl(cancel_flag))
    claimed = False
    try:
        with bound_scope(factory) as session:
            claimed = (
                session.scalar(
                    update(ExtractionTask)
                    .where(
                        ExtractionTask.id == task_id, ExtractionTask.status == "PENDING"
                    )
                    .values(status="RUNNING", started_at=datetime.now(UTC))
                    .returning(ExtractionTask.id)
                )
                is not None
            )
        if not claimed:
            return

        watermark_out: dict = {}

        def finalize(session: Session) -> None:
            task = get_task(session, task_id)
            run = session.get(ExtractionRun, task.run_id) if task.run_id else None
            if control.cancel.is_set():
                task.status = "CANCELLED"
                task.error = "cancelled_by_request"
                if run is not None:
                    run.status = RunResult.CANCELLED
                    run.finished_at = datetime.now(UTC)
                    run.counts = {**run.counts, "error": "extraction_cancelled"}
            elif run is not None and run.status in (
                RunResult.SUCCESS,
                RunResult.PARTIAL,
            ):
                if not run.counts.get("no_op"):
                    _publish_graph_revision(session, run)
                task.progress = {"phase": "done", **run.counts}
                task.watermark = watermark_out or None
            task.finished_at = datetime.now(UTC)
            control.finished = True

        with bound_scope(
            factory, commit_guard=control.lock, before_commit=finalize
        ) as session:
            task = get_task(session, task_id)
            _progress_memory[key] = {"phase": "entities"}

            def progress(phase: str, extra: dict) -> None:
                _progress_memory[key] = {"phase": phase, **extra}

            try:
                session.execute(
                    update(MappingRevision)
                    .where(MappingRevision.id == task.mapping_revision_id)
                    .values(id=MappingRevision.id)
                )
                base_id, watermarks = _load_incremental_base(session, task)
                run = start_run(
                    session,
                    task.mapping_revision_id,
                    task.datasource_id,
                    task.namespace,
                    progress=progress,
                    cancel_check=control.cancel.is_set,
                    watermarks=watermarks,
                    watermark_out=watermark_out,
                    publish=False,
                    incremental=task.incremental,
                    base_graph_revision_id=base_id,
                )
                task.run_id = run.id
                task.status = run.status.value
            except KGError as exc:
                run_id = exc.params.get("run_id")
                task.run_id = run_id if isinstance(run_id, int) else None
                task.status = (
                    "CANCELLED"
                    if isinstance(exc, ExtractionCancelledError)
                    else "FAILED"
                )
                task.error = str(exc.params.get("reason", exc.code.value))
    except Exception:
        # The candidate transaction has rolled back. Persist an honest terminal
        # status in a fresh transaction, including commit/database failures.
        if claimed:
            with bound_scope(factory) as session:
                task = get_task(session, task_id)
                task.status = "FAILED"
                task.error = "task_execution_failed"
                task.finished_at = datetime.now(UTC)
    finally:
        if claimed:
            _progress_memory.pop(key, None)
        with _runtime_lock:
            if _controls.get(key) is control and (
                claimed or control.cancel is cancel_flag
            ):
                _controls.pop(key, None)


def live_progress(task_id: int, engine: object) -> dict | None:
    """运行中任务的内存进度；任务结束或不存在返回 None。"""
    return (
        _progress_memory.get((engine, task_id)) if isinstance(engine, Engine) else None
    )
