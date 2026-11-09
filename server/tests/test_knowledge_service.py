"""Isolated ingestion regression: no developer database or external AI calls."""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import AsyncIterator, Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier
from types import SimpleNamespace

import app.models  # noqa: F401
import httpx
import pytest
from app.api import knowledge_runtime
from app.api.errors import install_error_handler
from app.api.knowledge_runtime import KnowledgeRuntime
from app.api.v1.knowledge import router
from app.core import knowledge_ai
from app.core.db import Base, bound_scope, get_session
from app.core.errors import ErrorCode, KGError
from app.domain import knowledge_service as service
from app.domain.knowledge_parser import MAX_FILE_BYTES, parse_knowledge_file
from app.models.account import User
from app.models.knowledge import (
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeIndex,
    KnowledgeTask,
)
from app.schemas.knowledge import KnowledgeBaseCreate, KnowledgeDocumentOut
from fastapi import FastAPI
from sqlalchemy import create_engine, event, func, inspect, select, update
from sqlalchemy.orm import Session, sessionmaker


@pytest.fixture
def factory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[sessionmaker[Session]]:
    monkeypatch.setattr(knowledge_ai, "embedding_configured", lambda: False)
    engine = create_engine(
        f"sqlite:///{tmp_path}/knowledge.db", connect_args={"check_same_thread": False}
    )

    @event.listens_for(engine, "connect")
    def foreign_keys(connection: object, _record: object) -> None:
        connection.execute("PRAGMA foreign_keys=ON")  # type: ignore[attr-defined]

    Base.metadata.create_all(engine)
    maker = sessionmaker(bind=engine, expire_on_commit=False)
    with bound_scope(maker) as session:
        session.add(
            User(
                id="actor",
                username="actor",
                email="actor@example.test",
                password_hash="unused",
            )
        )
        session.flush()
        service.create_base(session, KnowledgeBaseCreate(name="Knowledge"), "actor")
    yield maker
    engine.dispose()


def upload(
    factory: sessionmaker[Session],
    content: bytes = b"First paragraph.\n\nSecond paragraph.",
    name: str = "notes.txt",
) -> KnowledgeDocumentOut:
    with bound_scope(factory) as session:
        return service.upload_document(session, 1, name, None, content)


def claim(
    factory: sessionmaker[Session], worker: str = "worker"
) -> service.ClaimedTask:
    with bound_scope(factory) as session:
        result = service.claim_task(session, worker)
        assert result is not None
        return result


def output(factory: sessionmaker[Session], docid: str) -> KnowledgeDocumentOut:
    with factory() as session:
        return service.document_out(session, service.get_document(session, 1, docid))


def process(factory: sessionmaker[Session]) -> None:
    asyncio.run(KnowledgeRuntime(factory).process_claim(claim(factory)))


def stage(factory: sessionmaker[Session], owned: service.ClaimedTask) -> str:
    parsed = parse_knowledge_file(owned.content, filename=owned.filename)
    with bound_scope(factory) as session:
        index_id = service.stage_index(
            session, owned, parsed, embedding_version=None, embedding_model=None
        )
        assert index_id is not None
        return index_id


def test_duplicate_raw_hash_and_committed_queue(factory: sessionmaker[Session]) -> None:
    first = upload(factory, b"same\r\n")
    duplicate = upload(factory, b"same\r\n", "renamed.md")
    normalized_equivalent = upload(factory, b"same\n")
    assert not first.duplicate and duplicate.duplicate
    assert duplicate.id == first.id and duplicate.name == "notes.txt"
    assert first.content_hash == hashlib.sha256(b"same\r\n").hexdigest()
    assert normalized_equivalent.id != first.id
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(KnowledgeTask)) == 2


def test_concurrent_upload_and_claim_are_idempotent(
    factory: sessionmaker[Session],
) -> None:
    barrier = Barrier(2)

    def add() -> KnowledgeDocumentOut:
        barrier.wait(timeout=5)
        return upload(factory)

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: add(), range(2)))
    assert len({item.id for item in outcomes}) == 1
    assert sorted(item.duplicate for item in outcomes) == [False, True]
    barrier = Barrier(2)

    def take(worker: str) -> service.ClaimedTask | None:
        barrier.wait(timeout=5)
        with bound_scope(factory) as session:
            return service.claim_task(session, worker)

    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(take, ["worker-one", "worker-two"]))
    assert sum(item is not None for item in claims) == 1


def test_keyword_index_evidence_and_partial_parse(
    factory: sessionmaker[Session],
) -> None:
    document = upload(factory, b'name,value\n"good",42\n"unfinished', "data.csv")
    process(factory)
    result = output(factory, document.id)
    assert result.searchable and result.semantic_status == "NOT_CONFIGURED"
    assert (
        result.active_index is not None
        and result.active_index.parse_status == "PARTIAL"
    )
    assert result.active_index.warnings[0]["reason"] == "knowledge_csv_malformed"
    assert result.latest_task is not None and result.latest_task.status == "PARTIAL"
    with factory() as session:
        index = session.get(KnowledgeIndex, result.active_index.id)
        assert index is not None
        chunks = session.scalars(
            select(KnowledgeChunk).where(KnowledgeChunk.index_id == index.id)
        )
        for chunk in chunks:
            start, end = chunk.location["start_offset"], chunk.location["end_offset"]
            assert chunk.text == index.normalized_text[start:end]
            assert chunk.vector is None and chunk.location["row_number"] is not None


def test_invalid_utf8_is_uploaded_then_fails_job(
    factory: sessionmaker[Session],
) -> None:
    document = upload(factory, b"\xffbroken")
    assert document.latest_task is not None and document.latest_task.status == "QUEUED"
    process(factory)
    result = output(factory, document.id)
    assert not result.searchable and result.active_generation is None
    assert result.latest_task is not None and result.latest_task.status == "FAILED"
    assert result.latest_task.error_reason == "knowledge_invalid_utf8"


def test_failed_reparse_retains_old_index(
    factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    document = upload(factory)
    process(factory)
    before = output(factory, document.id)
    with bound_scope(factory) as session:
        service.queue_document(session, 1, document.id, before.revision)

    def broken(*args: object, **kwargs: object) -> None:
        raise KGError(ErrorCode.INVALID_REQUEST, {"reason": "knowledge_invalid_utf8"})

    monkeypatch.setattr(knowledge_runtime, "parse_knowledge_file", broken)
    process(factory)
    after = output(factory, document.id)
    assert after.searchable and after.active_generation == before.active_generation
    assert after.active_index == before.active_index
    assert after.latest_task is not None and after.latest_task.status == "FAILED"


def configure_failed_embedding(monkeypatch: pytest.MonkeyPatch) -> None:
    class FailedEmbedding:
        endpoint = SimpleNamespace(model="fake")

        async def embed(self, texts: list[str]) -> list[list[float]]:
            raise KGError(ErrorCode.LLM_UNAVAILABLE, {"reason": "model_unavailable"})

    monkeypatch.setattr(knowledge_ai, "embedding_configured", lambda: True)
    monkeypatch.setattr(knowledge_ai, "embedding_version", lambda: "test-v1")
    monkeypatch.setattr(knowledge_ai, "embedding_client", FailedEmbedding)


def test_first_embedding_failure_keeps_keyword_but_retry_preserves_old(
    factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    configure_failed_embedding(monkeypatch)
    document = upload(factory)
    process(factory)
    first = output(factory, document.id)
    assert first.searchable and first.semantic_status == "FAILED"
    assert first.latest_task is not None and first.latest_task.status == "PARTIAL"
    with bound_scope(factory) as session:
        service.queue_document(session, 1, document.id, first.revision)
    process(factory)
    second = output(factory, document.id)
    assert second.active_generation == first.active_generation
    assert second.active_index == first.active_index
    assert second.latest_task is not None and second.latest_task.status == "FAILED"


def test_embedding_batches_and_stale_configuration(
    factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    batches: list[list[str]] = []

    class Embedding:
        endpoint = SimpleNamespace(model="fake")

        async def embed(self, texts: list[str]) -> list[list[float]]:
            batches.append(texts)
            return [[1.0, 0.0] for _ in texts]

    monkeypatch.setattr(knowledge_ai, "embedding_configured", lambda: True)
    monkeypatch.setattr(knowledge_ai, "embedding_version", lambda: "test-v1")
    monkeypatch.setattr(knowledge_ai, "embedding_client", Embedding)
    document = upload(
        factory, "\n\n".join(f"Paragraph {index}" for index in range(40)).encode()
    )
    process(factory)
    result = output(factory, document.id)
    assert result.semantic_status == "READY" and [len(batch) for batch in batches] == [
        32,
        8,
    ]
    assert (
        result.active_index is not None
        and result.active_index.embedding_dimensions == 2
    )
    with factory() as session:
        persisted = list(
            session.scalars(select(KnowledgeChunk).order_by(KnowledgeChunk.id))
        )
        assert [chunk.text for chunk in persisted] == [
            text for batch in batches for text in batch
        ]
        assert all(chunk.vector == [1.0, 0.0] for chunk in persisted)
    monkeypatch.setattr(knowledge_ai, "embedding_version", lambda: "test-v2")
    assert output(factory, document.id).semantic_status == "STALE"
    with factory() as session:
        assert (
            session.get(KnowledgeIndex, result.active_index.id).semantic_status
            == "READY"
        )


@pytest.mark.parametrize("archive_base", [False, True])
def test_archive_restore_fences_inflight_index(
    factory: sessionmaker[Session], archive_base: bool
) -> None:
    document = upload(factory)
    owned = claim(factory)
    index_id = stage(factory, owned)
    with bound_scope(factory) as session:
        if archive_base:
            service.set_base_archived(session, 1, True, 1)
            service.set_base_archived(session, 1, False, 2)
        else:
            service.set_document_archived(session, 1, document.id, True, 1)
            service.set_document_archived(session, 1, document.id, False, 2)
    with bound_scope(factory) as session:
        assert not service.publish_index(session, owned, index_id, None)
        assert service.claim_task(session, "new-worker") is None
    result = output(factory, document.id)
    assert result.active_generation is None and not result.searchable
    assert result.latest_task is not None and result.latest_task.status == "CANCELLED"


def test_restore_keeps_original_index_and_queues_nothing(
    factory: sessionmaker[Session],
) -> None:
    document = upload(factory)
    process(factory)
    before = output(factory, document.id)
    with bound_scope(factory) as session:
        service.set_document_archived(session, 1, document.id, True, 1)
    assert not output(factory, document.id).searchable
    with bound_scope(factory) as session:
        service.set_document_archived(session, 1, document.id, False, 2)
        assert service.claim_task(session, "unused") is None
    after = output(factory, document.id)
    assert after.searchable and after.active_index == before.active_index
    assert after.latest_task == before.latest_task


def test_new_generation_and_expired_lease_fence_stale_workers(
    factory: sessionmaker[Session],
) -> None:
    document = upload(factory)
    old = claim(factory, "old")
    old_index = stage(factory, old)
    with bound_scope(factory) as session:
        service.queue_document(session, 1, document.id, 1)
        assert not service.publish_index(session, old, old_index, None)
    latest = claim(factory, "latest")
    latest_index = stage(factory, latest)
    with bound_scope(factory) as session:
        session.execute(
            update(KnowledgeTask)
            .where(KnowledgeTask.id == latest.id)
            .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
    with bound_scope(factory) as session:
        assert not service.heartbeat(session, latest)
        assert not service.publish_index(session, latest, latest_index, None)
        service.interrupt_expired(session)
        assert service.claim_task(session, "third") is None
    result = output(factory, document.id)
    assert result.active_generation is None and result.latest_task is not None
    assert result.latest_task.status == "INTERRUPTED"


def test_document_and_chunk_limits_preserve_prior_index(
    factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    document = upload(factory)
    process(factory)
    monkeypatch.setattr(service, "MAX_DOCUMENTS", 1)
    with bound_scope(factory) as session:
        service.set_document_archived(session, 1, document.id, True, 1)
    with pytest.raises(KGError, match=r"KG\.INVALID_REQUEST") as rejected:
        upload(factory, b"different")
    assert rejected.value.params["reason"] == "knowledge_too_many_documents"
    assert upload(factory).duplicate
    with bound_scope(factory) as session:
        service.set_document_archived(session, 1, document.id, False, 2)
        service.queue_document(session, 1, document.id, 3)
    monkeypatch.setattr(service, "MAX_ACTIVE_CHUNKS", 1)
    process(factory)
    result = output(factory, document.id)
    assert result.searchable and result.active_generation == 1
    assert result.latest_task is not None and result.latest_task.status == "FAILED"
    assert result.latest_task.error_reason == "knowledge_too_many_active_chunks"


def test_queued_task_recovered_on_runtime_start(
    factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    document = upload(factory)

    async def run() -> None:
        completed = asyncio.Event()
        original = KnowledgeRuntime.process_claim

        async def observed(self: KnowledgeRuntime, owned: service.ClaimedTask) -> None:
            await original(self, owned)
            completed.set()

        monkeypatch.setattr(KnowledgeRuntime, "process_claim", observed)
        runtime = KnowledgeRuntime(factory)
        await runtime.start()
        try:
            await asyncio.wait_for(completed.wait(), timeout=5)
        finally:
            await runtime.stop()
        assert not runtime._workers

    asyncio.run(run())
    assert output(factory, document.id).latest_task.status == "SUCCESS"


def test_shutdown_interrupts_running_task(
    factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    document = upload(factory)

    async def run() -> None:
        entered = asyncio.Event()

        class BlockedEmbedding:
            endpoint = SimpleNamespace(model="fake")

            async def embed(self, texts: list[str]) -> list[list[float]]:
                entered.set()
                await asyncio.Event().wait()
                return []

        monkeypatch.setattr(knowledge_ai, "embedding_configured", lambda: True)
        monkeypatch.setattr(knowledge_ai, "embedding_version", lambda: "test-v1")
        monkeypatch.setattr(knowledge_ai, "embedding_client", BlockedEmbedding)
        runtime = KnowledgeRuntime(factory)
        await runtime.start()
        await asyncio.wait_for(entered.wait(), timeout=5)
        await asyncio.wait_for(runtime.stop(), timeout=5)
        assert not runtime._workers

    asyncio.run(run())
    result = output(factory, document.id)
    assert not result.searchable and result.latest_task.status == "INTERRUPTED"


def test_job_timeout_is_terminal(
    factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    document = upload(factory)

    async def stuck(
        self: KnowledgeRuntime,
        owned: service.ClaimedTask,
        control: knowledge_runtime._JobControl,
    ) -> None:
        await asyncio.Event().wait()

    monkeypatch.setattr(KnowledgeRuntime, "_ingest", stuck)
    monkeypatch.setattr(knowledge_runtime, "JOB_TIMEOUT_SECONDS", 0.01)
    process(factory)
    result = output(factory, document.id)
    assert result.latest_task.status == "FAILED"
    assert result.latest_task.error_reason == "knowledge_job_timeout"


@pytest.mark.parametrize("phase", ["stage_index", "publish_index"])
def test_database_lock_does_not_block_loop_or_publish_after_timeout(
    factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch, phase: str
) -> None:
    import threading

    document = upload(factory)
    owned = claim(factory)
    locked, release = threading.Event(), threading.Event()
    original = getattr(service, phase)
    blockers: list[threading.Thread] = []

    def hold_lock() -> None:
        with factory() as session:
            session.connection().exec_driver_sql("BEGIN IMMEDIATE")
            locked.set()
            release.wait(2)
            session.rollback()

    def contended(*args, **kwargs):
        blocker = threading.Thread(target=hold_lock)
        blockers.append(blocker)
        blocker.start()
        assert locked.wait(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(service, phase, contended)
    monkeypatch.setattr(knowledge_runtime, "JOB_TIMEOUT_SECONDS", 0.05)

    async def exercise() -> None:
        processing = asyncio.create_task(KnowledgeRuntime(factory).process_claim(owned))
        try:
            assert await asyncio.to_thread(locked.wait, 1)
            await asyncio.sleep(0.08)
            # We can release the external lock from this loop while the worker
            # waits. The old synchronous path could not reach this point.
            release.set()
            await asyncio.wait_for(processing, 2)
        finally:
            release.set()
            for blocker in blockers:
                await asyncio.to_thread(blocker.join, 2)

    asyncio.run(exercise())
    result = output(factory, document.id)
    assert not result.searchable and result.active_generation is None
    assert result.latest_task.status == "FAILED"
    assert result.latest_task.error_reason == "knowledge_job_timeout"
    with factory() as session:
        assert (
            session.connection().exec_driver_sql("PRAGMA busy_timeout").scalar() == 5000
        )


def test_archive_during_model_request_cancels_inference_and_releases_worker(
    factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    first = upload(factory, b"blocked inference")
    first_claim = claim(factory, "first")
    second = upload(factory, b"next document")

    async def exercise() -> None:
        entered, cancelled, completed = (
            asyncio.Event(),
            asyncio.Event(),
            asyncio.Event(),
        )

        class Embedding:
            endpoint = SimpleNamespace(model="fake")

            async def embed(self, texts: list[str]) -> list[list[float]]:
                if "blocked inference" in texts:
                    entered.set()
                    try:
                        await asyncio.Event().wait()
                    finally:
                        cancelled.set()
                completed.set()
                return [[1.0, 0.0] for _ in texts]

        monkeypatch.setattr(knowledge_ai, "embedding_configured", lambda: True)
        monkeypatch.setattr(knowledge_ai, "embedding_version", lambda: "test-v1")
        monkeypatch.setattr(knowledge_ai, "embedding_client", Embedding)
        monkeypatch.setattr(knowledge_runtime, "HEARTBEAT_SECONDS", 0.02)
        runtime = KnowledgeRuntime(factory)
        task = asyncio.create_task(runtime.process_claim(first_claim))
        await asyncio.wait_for(entered.wait(), 2)
        await runtime._database(
            lambda session: service.set_document_archived(session, 1, first.id, True, 1)
        )
        await asyncio.wait_for(task, 2)
        assert cancelled.is_set()
        await runtime.process_claim(claim(factory, "second"))
        assert completed.is_set()

    asyncio.run(exercise())
    assert output(factory, first.id).latest_task.status == "CANCELLED"
    assert output(factory, second.id).latest_task.status == "SUCCESS"


def test_cancellation_wins_before_publication_commit(
    factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    import threading

    document = upload(factory)
    owned = claim(factory)
    reached, release = threading.Event(), threading.Event()
    with factory() as probe:
        engine = probe.get_bind()
    original = service.publish_index

    def publish(*args, **kwargs):
        result = original(*args, **kwargs)
        args[0].connection().info["test_pause_publication"] = True
        return result

    def before_statement(
        connection, cursor, statement, parameters, context, executemany
    ):
        if statement.startswith("PRAGMA busy_timeout=") and connection.info.pop(
            "test_pause_publication", False
        ):
            reached.set()
            release.wait(2)

    monkeypatch.setattr(service, "publish_index", publish)
    event.listen(engine, "before_cursor_execute", before_statement)

    async def exercise() -> None:
        task = asyncio.create_task(KnowledgeRuntime(factory).process_claim(owned))
        try:
            assert await asyncio.to_thread(reached.wait, 2)
            task.cancel()
            # Let the cancellation thread acquire the still-free commit gate;
            # the publication thread remains paused before any COMMIT starts.
            await asyncio.sleep(0.05)
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, 2)
        finally:
            release.set()

    try:
        asyncio.run(exercise())
    finally:
        event.remove(engine, "before_cursor_execute", before_statement)
    result = output(factory, document.id)
    assert result.active_generation is None and not result.searchable
    assert result.latest_task.status == "INTERRUPTED"


def test_bounded_http_upload_and_required_revision(
    factory: sessionmaker[Session],
) -> None:
    app = FastAPI()
    app.include_router(router)
    install_error_handler(app)

    def session_dependency() -> Iterator[Session]:
        with factory() as session:
            yield session

    app.dependency_overrides[get_session] = session_dependency

    async def run() -> None:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            uploaded = await client.post(
                "/knowledge-bases/1/documents?filename=test.txt",
                content=b"\xffbad",
                headers={"Content-Type": "application/octet-stream"},
            )
            assert uploaded.status_code == 201
            assert uploaded.json()["latest_task"]["status"] == "QUEUED"
            docid = uploaded.json()["id"]
            missing = await client.post(f"/knowledge-bases/1/documents/{docid}/archive")
            assert missing.status_code == 422
            stale = await client.post(
                f"/knowledge-bases/1/documents/{docid}/archive",
                headers={"If-Match": "5"},
            )
            assert stale.status_code == 409

            async def oversized() -> AsyncIterator[bytes]:
                yield b"x" * MAX_FILE_BYTES
                yield b"x"

            too_large = await client.post(
                "/knowledge-bases/1/documents?filename=large.txt",
                content=oversized(),
                headers={"Content-Type": "application/octet-stream"},
            )
            assert too_large.status_code == 400
            assert too_large.json()["params"]["reason"] == "knowledge_file_too_large"
            listing = await client.get("/knowledge-bases/1/documents")
            assert listing.json()["total"] == 1

    asyncio.run(run())


def test_summary_and_list_leave_raw_payloads_unloaded(
    factory: sessionmaker[Session],
) -> None:
    document = upload(factory)
    process(factory)
    with factory() as session:
        docs, total = service.list_documents(session, 1)
        assert total == 1 and "content" in inspect(docs[0]).unloaded
        result = service.document_out(session, docs[0])
        assert result.size_bytes == len(b"First paragraph.\n\nSecond paragraph.")
        assert "content" in inspect(docs[0]).unloaded
        active = session.get(KnowledgeIndex, result.active_index.id)
        assert "normalized_text" in inspect(active).unloaded
        summary = service.base_out(session, service.get_base(session, 1))
        assert summary.document_count == summary.searchable_count == 1
        assert (
            summary.semantic_count
            == summary.processing_count
            == summary.failed_count
            == 0
        )
        assert "content" in inspect(docs[0]).unloaded
    with bound_scope(factory) as session:
        service.set_document_archived(session, 1, document.id, True, 1)
        summary = service.base_out(session, service.get_base(session, 1))
        assert summary.document_count == 1 and summary.searchable_count == 0


@pytest.mark.parametrize(
    ("content", "filename", "reason"),
    [
        (b"x" * (MAX_FILE_BYTES + 1), "notes.txt", "knowledge_file_too_large"),
        (b"x", "notes.pdf", "knowledge_unsupported_extension"),
        (b"", "notes.txt", "knowledge_empty_file"),
    ],
)
def test_invalid_upload_metadata_creates_no_document(
    factory: sessionmaker[Session], content: bytes, filename: str, reason: str
) -> None:
    with pytest.raises(KGError) as rejected:
        upload(factory, content, filename)
    assert rejected.value.params["reason"] == reason
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(KnowledgeDocument)) == 0
