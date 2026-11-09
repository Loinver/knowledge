"""Bounded SQL transactions for the async knowledge ingestion runtime."""

from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Callable

from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker


async def run_knowledge_transaction[T](
    factory: sessionmaker[Session],
    operation: Callable[[Session], T],
    *,
    deadline: float | None = None,
) -> T:
    """Own SQL resources on a worker, serialize cancellation with final commit.

    Cancellation that wins the commit gate rolls back. Once COMMIT has entered
    the gate, it completes first; no cancellation can undo an accepted commit.
    Both paths join the thread before the runtime can dispose its engine.
    """
    cancelled = threading.Event()
    commit_gate = threading.Lock()

    def check() -> None:
        if cancelled.is_set():
            raise TimeoutError("knowledge_database_cancelled")
        if deadline is not None and time.monotonic() >= deadline:
            raise TimeoutError("knowledge_job_timeout")

    def budget_ms() -> int:
        remaining = 1.0
        if deadline is not None:
            remaining = min(remaining, deadline - time.monotonic())
        return max(1, int(remaining * 1000))

    def transaction() -> T:
        check()
        with factory() as probe:
            engine = probe.get_bind().engine
        with engine.connect() as connection:
            sqlite = connection.dialect.name == "sqlite"
            old_timeout = None
            if sqlite:
                old_timeout = connection.exec_driver_sql(
                    "PRAGMA busy_timeout"
                ).scalar_one()
                connection.exec_driver_sql(f"PRAGMA busy_timeout={budget_ms()}")
                connection.commit()
            try:
                with factory(bind=connection) as session:
                    if connection.dialect.name == "postgresql":
                        for setting in ("lock_timeout", "statement_timeout"):
                            session.execute(
                                text("SELECT set_config(:setting, :value, true)"),
                                {"setting": setting, "value": f"{budget_ms()}ms"},
                            )
                    check()
                    result = operation(session)
                    session.flush()
                    if sqlite:
                        connection.exec_driver_sql(f"PRAGMA busy_timeout={budget_ms()}")
                    with commit_gate:
                        # No blocking SQL belongs between this check and commit.
                        check()
                        session.commit()
                    return result
            except OperationalError:
                check()
                raise
            finally:
                if connection.in_transaction():
                    connection.rollback()
                if old_timeout is not None:
                    connection.exec_driver_sql(
                        f"PRAGMA busy_timeout={int(old_timeout)}"
                    )
                    connection.rollback()

    def cancel_before_commit() -> None:
        with commit_gate:
            cancelled.set()

    work = asyncio.create_task(asyncio.to_thread(transaction))
    try:
        return await asyncio.shield(work)
    except asyncio.CancelledError:
        # Taking the gate on another thread never blocks the event loop if a
        # commit is already in progress. Repeated cancellation still drains it.
        cancellation = asyncio.create_task(asyncio.to_thread(cancel_before_commit))
        while not cancellation.done():
            try:
                await asyncio.shield(cancellation)
            except asyncio.CancelledError:
                continue
        cancellation.result()
        while not work.done():
            try:
                await asyncio.shield(work)
            except asyncio.CancelledError:
                continue
            except Exception:
                break
        if not work.cancelled():
            work.exception()
        raise
