"""Lifespan-owned, bounded workers for the durable knowledge ingestion queue."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial

from sqlalchemy.orm import Session, sessionmaker

from app.core import knowledge_ai
from app.core.db import get_engine
from app.core.errors import ErrorCode, KGError
from app.core.knowledge_transactions import run_knowledge_transaction
from app.domain import knowledge_service as service
from app.domain.knowledge_parser import parse_knowledge_file

logger = logging.getLogger(__name__)
JOB_TIMEOUT_SECONDS = 180
HEARTBEAT_SECONDS = 10


class _OwnershipLostError(Exception):
    """An archived, replaced or expired job must stop its model request."""


@dataclass
class _JobControl:
    deadline: float


class KnowledgeRuntime:
    def __init__(
        self, factory: sessionmaker[Session] | None = None, *, concurrency: int = 1
    ) -> None:
        if not 1 <= concurrency <= 2:
            raise ValueError("knowledge_concurrency_must_be_one_or_two")
        self.factory = (
            factory
            if factory is not None
            else sessionmaker(bind=get_engine(), expire_on_commit=False)
        )
        self.concurrency = concurrency
        self._workers: list[asyncio.Task[None]] = []
        self._worker_ids: list[str] = []

    async def _database[T](
        self,
        operation: Callable[[Session], T],
        control: _JobControl | None = None,
    ) -> T:
        return await run_knowledge_transaction(
            self.factory,
            operation,
            deadline=control.deadline if control else None,
        )

    async def start(self) -> None:
        if self._workers:
            return
        self._worker_ids = [uuid.uuid4().hex for _ in range(self.concurrency)]
        self._workers = [
            asyncio.create_task(self._worker(worker_id), name=f"knowledge-{worker_id}")
            for worker_id in self._worker_ids
        ]

    async def stop(self) -> None:
        for worker in self._workers:
            worker.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        if self._worker_ids:
            await self._database(
                lambda session: service.interrupt_workers(session, self._worker_ids)
            )
        self._workers.clear()
        self._worker_ids.clear()

    async def _worker(self, worker_id: str) -> None:
        while True:
            try:
                await self._database(service.interrupt_expired)
                claim = await self._database(
                    lambda session: service.claim_task(session, worker_id)
                )
                if claim is not None:
                    await self.process_claim(claim)
                    continue
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.error(
                    "knowledge_worker_iteration_failed worker_id=%s", worker_id
                )
            await asyncio.sleep(1)

    async def _heartbeat(
        self, claim: service.ClaimedTask, control: _JobControl
    ) -> None:
        while True:
            await asyncio.sleep(HEARTBEAT_SECONDS)
            if not await self._database(
                lambda session: service.heartbeat(session, claim), control
            ):
                raise _OwnershipLostError

    async def _run_owned(self, claim: service.ClaimedTask) -> None:
        control = _JobControl(time.monotonic() + JOB_TIMEOUT_SECONDS)
        heartbeat = asyncio.create_task(self._heartbeat(claim, control))
        ingestion = asyncio.create_task(self._ingest(claim, control))
        try:
            async with asyncio.timeout(JOB_TIMEOUT_SECONDS):
                await asyncio.wait(
                    {heartbeat, ingestion}, return_when=asyncio.FIRST_COMPLETED
                )
                if heartbeat.done():
                    await heartbeat
                await ingestion
        finally:
            # Drain inference and database transactions before recording failure
            # or disposing the engine. Preserve terminal archive/replace states.
            heartbeat.cancel()
            ingestion.cancel()
            await asyncio.gather(heartbeat, ingestion, return_exceptions=True)

    async def process_claim(self, claim: service.ClaimedTask) -> None:
        """Process a committed claim; exposed for deterministic isolated tests."""
        try:
            await self._run_owned(claim)
        except _OwnershipLostError:
            return
        except asyncio.CancelledError:
            await self._database(
                lambda session: service.finish_failure(
                    session,
                    claim,
                    ErrorCode.INTERNAL_ERROR.value,
                    "knowledge_worker_stopped",
                    interrupted=True,
                )
            )
            raise
        except (KGError, TimeoutError) as exc:
            code = (
                exc.code.value
                if isinstance(exc, KGError)
                else ErrorCode.INTERNAL_ERROR.value
            )
            reason = (
                str(exc.params.get("reason", "knowledge_ingestion_failed"))
                if isinstance(exc, KGError)
                else "knowledge_job_timeout"
            )
            await self._database(
                lambda session: service.finish_failure(session, claim, code, reason)
            )
        except Exception:
            await self._database(
                lambda session: service.finish_failure(
                    session,
                    claim,
                    ErrorCode.INTERNAL_ERROR.value,
                    "knowledge_ingestion_failed",
                )
            )
            logger.error("knowledge_ingestion_failed task_id=%s", claim.id)

    async def _ingest(self, claim: service.ClaimedTask, control: _JobControl) -> None:
        parsed = await asyncio.to_thread(
            parse_knowledge_file,
            claim.content,
            filename=claim.filename,
            content_type=claim.media_type,
        )
        configured = knowledge_ai.embedding_configured()
        client = knowledge_ai.embedding_client() if configured else None
        version = knowledge_ai.embedding_version() if configured else None
        index_id = await self._database(
            lambda session: service.stage_index(
                session,
                claim,
                parsed,
                embedding_version=version,
                embedding_model=client.endpoint.model if client else None,
            ),
            control,
        )
        if index_id is None:
            return
        vectors: list[list[float]] | None = None
        code, reason = None, None
        if client is not None:
            vectors = []
            chunks = sorted(parsed.chunks, key=lambda chunk: chunk.id)
            try:
                for start in range(0, len(chunks), 32):
                    batch = await client.embed(
                        [chunk.text for chunk in chunks[start : start + 32]]
                    )
                    if vectors and len(vectors[0]) != len(batch[0]):
                        raise KGError(
                            ErrorCode.LLM_RESPONSE_INVALID,
                            {"reason": "embedding_dimension_mismatch"},
                        )
                    vectors.extend(batch)
                    if not await self._database(
                        partial(service.heartbeat, claim=claim, processed=len(vectors)),
                        control,
                    ):
                        return
            except KGError as exc:
                vectors, code = None, exc.code.value
                reason = str(exc.params.get("reason", "knowledge_embedding_failed"))
        await self._database(
            lambda session: service.publish_index(
                session, claim, index_id, vectors, error_code=code, error_reason=reason
            ),
            control,
        )
