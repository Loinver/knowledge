"""异步抽取任务（第三批 P1-04）：后台执行、取消、调度与增量水位。

执行模型：进程内线程池（默认 2 并发）+ 调度线程轮询 PENDING 任务。
任务在阶段边界协作式取消（ExtractionCancelledError），失败不发布结果集；
SUCCESS/PARTIAL 后按来源表记录增量字段最大值，供下次增量运行过滤。
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.db import bound_scope
from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.domain.extraction_service import (
    ExtractionCancelledError,
    start_run,
)
from app.models.data_access import MappingRevision
from app.models.enums import RunResult
from app.models.extraction import ExtractionTask

_POLL_SECONDS = 2.0
_MAX_WORKERS = 2

_executor = ThreadPoolExecutor(
    max_workers=_MAX_WORKERS, thread_name_prefix="kg-extraction"
)
_cancel_flags: dict[int, threading.Event] = {}
# 任务归属引擎：随创建会话注册（生产为全局单引擎；测试为各库内存/文件引擎）。
_engines: set[Engine] = set()
# 运行中任务的实时进度（进程内）：SQLite 下跨连接写进度会与工作事务抢锁，
# 因此进度驻留内存，任务结束前的最终计数以 run.counts 落库为准。
_progress_memory: dict[int, dict] = {}
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
        task.status = "CANCELLED"
        task.finished_at = datetime.now(UTC)
        task.error = "cancelled_before_start"
        session.flush()
        return task
    if task.status == "RUNNING":
        flag = _cancel_flags.get(task.id)
        if flag is not None:
            flag.set()
        return task
    raise KGError(
        ErrorCode.VALIDATION_VIOLATION,
        {"reason": "task_not_cancellable", "status": task.status, "task_id": task.id},
    )


def _submit(task_id: int, engine: Engine) -> None:
    flag = threading.Event()
    _cancel_flags[task_id] = flag
    _executor.submit(_run_task, task_id, flag, engine)


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


def _load_watermarks(session: Session, task: ExtractionTask) -> dict | None:
    """增量运行的上次水位：同 (mapping, datasource) 最近成功任务的写出水。"""
    if not task.incremental:
        return None
    previous = session.scalars(
        select(ExtractionTask)
        .where(
            ExtractionTask.mapping_revision_id == task.mapping_revision_id,
            ExtractionTask.datasource_id == task.datasource_id,
            ExtractionTask.status.in_(("SUCCESS", "PARTIAL")),
            ExtractionTask.id != task.id,
        )
        .order_by(ExtractionTask.id.desc())
        .limit(1)
    ).first()
    return previous.watermark if previous is not None else None


def _run_task(task_id: int, cancel_flag: threading.Event, engine: Engine) -> None:
    """线程池入口：独立 session 执行，任务行状态机全程由本函数维护。"""
    with bound_scope(sessionmaker(bind=engine, expire_on_commit=False)) as session:
        task = session.get(ExtractionTask, task_id)
        if task is None or task.status != "PENDING":
            _cancel_flags.pop(task_id, None)
            return
        if cancel_flag.is_set():
            task.status = "CANCELLED"
            task.finished_at = datetime.now(UTC)
            task.error = "cancelled_before_start"
            _cancel_flags.pop(task_id, None)
            return
        task.status = "RUNNING"
        task.started_at = datetime.now(UTC)
        watermarks = _load_watermarks(session, task)
        _progress_memory[task_id] = {"phase": "entities"}

        def progress(phase: str, extra: dict) -> None:
            _progress_memory[task_id] = {"phase": phase, **extra}

        watermark_out: dict = {}
        try:
            run = start_run(
                session,
                task.mapping_revision_id,
                task.datasource_id,
                task.namespace,
                progress=progress,
                cancel_check=cancel_flag.is_set,
                watermarks=watermarks,
                watermark_out=watermark_out,
            )
        except ExtractionCancelledError:
            # 协作式取消：本事务内已写入的候选行随提交保留（run 无发布，
            # is_current 不受影响），任务如实记 CANCELLED。
            task.status = "CANCELLED"
            task.finished_at = datetime.now(UTC)
            task.error = "cancelled_by_request"
            _progress_memory.pop(task_id, None)
            _cancel_flags.pop(task_id, None)
            return
        except KGError as exc:
            task.status = "FAILED"
            task.finished_at = datetime.now(UTC)
            task.error = f"{exc.code.value}"
            _progress_memory.pop(task_id, None)
            _cancel_flags.pop(task_id, None)
            return
        except Exception:
            task.status = "FAILED"
            task.finished_at = datetime.now(UTC)
            task.error = "task_execution_failed"
            _progress_memory.pop(task_id, None)
            _cancel_flags.pop(task_id, None)
            return
        task.run_id = run.id
        task.status = run.status.value
        task.finished_at = datetime.now(UTC)
        if run.status in (RunResult.SUCCESS, RunResult.PARTIAL):
            counts = run.counts if isinstance(run.counts, dict) else {}
            task.progress = {"phase": "done", **counts}
            task.watermark = watermark_out or None
        _progress_memory.pop(task_id, None)
        _cancel_flags.pop(task_id, None)


def live_progress(task_id: int) -> dict | None:
    """运行中任务的内存进度；任务结束或不存在返回 None。"""
    return _progress_memory.get(task_id)
