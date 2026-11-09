"""Knowledge storage, generation fencing and atomic index publication.

Callers own transactions. Every mutation of a base or its documents takes the
same base lock before reading mutable state; published index rows are retained.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import case, func, select, update
from sqlalchemy.orm import Session

from app.core import knowledge_ai
from app.core.errors import ErrorCode, KGError
from app.domain.knowledge_parser import ParsedDocument, validate_knowledge_upload
from app.models.knowledge import (
    KnowledgeBase,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeIndex,
    KnowledgeTask,
)
from app.schemas.knowledge import (
    KnowledgeBaseCreate,
    KnowledgeBaseOut,
    KnowledgeBaseUpdate,
    KnowledgeDocumentOut,
    KnowledgeIndexOut,
    KnowledgeTaskOut,
    SemanticStatus,
)

MAX_DOCUMENTS = 100
MAX_ACTIVE_CHUNKS = 10_000
LEASE_SECONDS = 30
LIVE_STATUSES = ("QUEUED", "RUNNING")
ArchiveFilter = Literal["active", "archived", "all"]


def invalid(reason: str, **params: object) -> KGError:
    return KGError(ErrorCode.INVALID_REQUEST, {"reason": reason, **params})


def get_base(session: Session, kb_id: int) -> KnowledgeBase:
    base = session.get(KnowledgeBase, kb_id)
    if base is None:
        raise KGError(ErrorCode.RESOURCE_NOT_FOUND, {"id": kb_id})
    return base


def lock_base(session: Session, kb_id: int) -> KnowledgeBase:
    if session.get_bind().dialect.name == "sqlite":
        # Raw SQL avoids the ORM updated_at hook on this lock-only write.
        session.connection().exec_driver_sql(
            "UPDATE knowledge_base SET id = id WHERE id = ?", (kb_id,)
        )
    base = session.scalar(
        select(KnowledgeBase)
        .where(KnowledgeBase.id == kb_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if base is None:
        raise KGError(ErrorCode.RESOURCE_NOT_FOUND, {"id": kb_id})
    return base


def _check_revision(revision: int, if_match: int) -> None:
    if revision != if_match:
        raise KGError(
            ErrorCode.REVISION_CONFLICT,
            {"expected": revision, "actual": if_match},
        )


def _writable(base: KnowledgeBase, document: KnowledgeDocument | None = None) -> None:
    if base.archived or (document is not None and document.archived):
        raise invalid("knowledge_archived")


def list_bases(
    session: Session,
    q: str = "",
    page: int = 1,
    page_size: int = 20,
    sort: str = "-updated_at",
    status: ArchiveFilter = "active",
) -> tuple[list[KnowledgeBase], int]:
    statement = select(KnowledgeBase)
    if q:
        statement = statement.where(KnowledgeBase.name.contains(q, autoescape=True))
    if status != "all":
        statement = statement.where(KnowledgeBase.archived.is_(status == "archived"))
    total = session.scalar(select(func.count()).select_from(statement.subquery())) or 0
    order = {
        "name": KnowledgeBase.name,
        "created_at": KnowledgeBase.created_at,
        "updated_at": KnowledgeBase.updated_at,
    }.get(sort.lstrip("-"))
    if order is None:
        raise invalid("knowledge_invalid_sort")
    statement = statement.order_by(
        order.desc() if sort.startswith("-") else order, KnowledgeBase.id
    )
    return list(
        session.scalars(statement.offset((page - 1) * page_size).limit(page_size))
    ), total


def create_base(
    session: Session, payload: KnowledgeBaseCreate, actor_id: str
) -> KnowledgeBase:
    base = KnowledgeBase(**payload.model_dump(), created_by=actor_id)
    session.add(base)
    session.flush()
    return base


def edit_base(
    session: Session, kb_id: int, payload: KnowledgeBaseUpdate, if_match: int
) -> KnowledgeBase:
    base = lock_base(session, kb_id)
    _check_revision(base.revision, if_match)
    _writable(base)
    base.name, base.description = payload.name, payload.description
    base.revision += 1
    session.flush()
    return base


def _cancel_document_tasks(session: Session, document_id: str) -> None:
    session.execute(
        update(KnowledgeTask)
        .where(
            KnowledgeTask.document_id == document_id,
            KnowledgeTask.status.in_(LIVE_STATUSES),
        )
        .values(
            status="CANCELLED",
            phase="FINISHED",
            finished_at=datetime.now(UTC),
            expires_at=None,
            error_reason="knowledge_archived",
        )
    )


def set_base_archived(
    session: Session, kb_id: int, archived: bool, if_match: int
) -> KnowledgeBase:
    base = lock_base(session, kb_id)
    _check_revision(base.revision, if_match)
    if base.archived != archived:
        base.archived = archived
        base.revision += 1
        base.index_revision += 1
        if archived:
            for document_id in session.scalars(
                select(KnowledgeDocument.id).where(KnowledgeDocument.kb_id == kb_id)
            ):
                _cancel_document_tasks(session, document_id)
    session.flush()
    return base


def get_document(session: Session, kb_id: int, docid: str) -> KnowledgeDocument:
    get_base(session, kb_id)
    document = session.scalar(
        select(KnowledgeDocument)
        .where(KnowledgeDocument.kb_id == kb_id, KnowledgeDocument.id == docid)
        .execution_options(populate_existing=True)
    )
    if document is None:
        raise KGError(ErrorCode.RESOURCE_NOT_FOUND, {"id": docid})
    return document


def list_documents(
    session: Session,
    kb_id: int,
    q: str = "",
    page: int = 1,
    page_size: int = 20,
    sort: str = "-created_at",
    status: ArchiveFilter = "active",
) -> tuple[list[KnowledgeDocument], int]:
    get_base(session, kb_id)
    statement = select(KnowledgeDocument).where(KnowledgeDocument.kb_id == kb_id)
    if q:
        statement = statement.where(KnowledgeDocument.name.contains(q, autoescape=True))
    if status != "all":
        statement = statement.where(
            KnowledgeDocument.archived.is_(status == "archived")
        )
    total = session.scalar(select(func.count()).select_from(statement.subquery())) or 0
    order = {
        "name": KnowledgeDocument.name,
        "created_at": KnowledgeDocument.created_at,
        "updated_at": KnowledgeDocument.updated_at,
    }.get(sort.lstrip("-"))
    if order is None:
        raise invalid("knowledge_invalid_sort")
    statement = statement.order_by(
        order.desc() if sort.startswith("-") else order, KnowledgeDocument.id
    )
    return list(
        session.scalars(statement.offset((page - 1) * page_size).limit(page_size))
    ), total


def _enqueue(session: Session, document: KnowledgeDocument) -> KnowledgeTask:
    # A newer explicit retry fences all work for the prior generation.
    session.execute(
        update(KnowledgeTask)
        .where(
            KnowledgeTask.document_id == document.id,
            KnowledgeTask.status.in_(LIVE_STATUSES),
        )
        .values(
            status="CANCELLED",
            phase="FINISHED",
            finished_at=datetime.now(UTC),
            expires_at=None,
            error_reason="knowledge_superseded",
        )
    )
    document.generation += 1
    task = KnowledgeTask(document_id=document.id, generation=document.generation)
    session.add(task)
    session.flush()
    return task


def upload_document(
    session: Session, kb_id: int, filename: str, media_type: str | None, content: bytes
) -> KnowledgeDocumentOut:
    name, media = validate_knowledge_upload(
        content, filename=filename, content_type=media_type
    )
    base = lock_base(session, kb_id)
    _writable(base)
    content_hash = hashlib.sha256(content).hexdigest()
    existing = session.scalar(
        select(KnowledgeDocument).where(
            KnowledgeDocument.kb_id == kb_id,
            KnowledgeDocument.content_hash == content_hash,
        )
    )
    if existing is not None:
        return document_out(session, existing).model_copy(update={"duplicate": True})
    count = (
        session.scalar(
            select(func.count())
            .select_from(KnowledgeDocument)
            .where(KnowledgeDocument.kb_id == kb_id)
        )
        or 0
    )
    if count >= MAX_DOCUMENTS:
        raise invalid("knowledge_too_many_documents", limit=MAX_DOCUMENTS)
    # The per-base lock serializes duplicate detection and insertion. The unique
    # constraint remains a final guard; unrelated integrity errors propagate.
    document = KnowledgeDocument(
        kb_id=kb_id,
        name=name,
        media_type=media,
        content=content,
        content_hash=content_hash,
    )
    session.add(document)
    session.flush()
    _enqueue(session, document)
    return document_out(session, document)


def queue_document(
    session: Session, kb_id: int, docid: str, if_match: int
) -> KnowledgeDocument:
    base = lock_base(session, kb_id)
    document = get_document(session, kb_id, docid)
    _check_revision(document.revision, if_match)
    _writable(base, document)
    document.revision += 1
    _enqueue(session, document)
    return document


def _active_chunk_count(
    session: Session, kb_id: int, *, exclude: str | None = None
) -> int:
    statement = (
        select(func.count())
        .select_from(KnowledgeChunk)
        .join(KnowledgeIndex, KnowledgeChunk.index_id == KnowledgeIndex.id)
        .join(KnowledgeDocument, KnowledgeIndex.document_id == KnowledgeDocument.id)
        .where(
            KnowledgeDocument.kb_id == kb_id,
            KnowledgeDocument.archived.is_(False),
            KnowledgeIndex.generation == KnowledgeDocument.active_generation,
        )
    )
    if exclude is not None:
        statement = statement.where(KnowledgeDocument.id != exclude)
    return session.scalar(statement) or 0


def set_document_archived(
    session: Session, kb_id: int, docid: str, archived: bool, if_match: int
) -> KnowledgeDocument:
    base = lock_base(session, kb_id)
    document = get_document(session, kb_id, docid)
    _check_revision(document.revision, if_match)
    _writable(base)
    if document.archived != archived:
        if not archived and document.active_generation is not None:
            count = (
                session.scalar(
                    select(func.count())
                    .select_from(KnowledgeChunk)
                    .join(KnowledgeIndex)
                    .where(
                        KnowledgeIndex.document_id == docid,
                        KnowledgeIndex.generation == document.active_generation,
                    )
                )
                or 0
            )
            if (
                _active_chunk_count(session, kb_id, exclude=docid) + count
                > MAX_ACTIVE_CHUNKS
            ):
                raise invalid(
                    "knowledge_too_many_active_chunks", limit=MAX_ACTIVE_CHUNKS
                )
        document.archived = archived
        document.revision += 1
        base.index_revision += 1
        if archived:
            _cancel_document_tasks(session, docid)
    session.flush()
    return document


def task_out(task: KnowledgeTask) -> KnowledgeTaskOut:
    return KnowledgeTaskOut.model_validate(task)


def list_tasks(
    session: Session, kb_id: int, docid: str, page: int = 1, page_size: int = 20
) -> tuple[list[KnowledgeTask], int]:
    get_document(session, kb_id, docid)
    statement = select(KnowledgeTask).where(KnowledgeTask.document_id == docid)
    total = session.scalar(select(func.count()).select_from(statement.subquery())) or 0
    return list(
        session.scalars(
            statement.order_by(KnowledgeTask.generation.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ), total


def document_out(session: Session, doc: KnowledgeDocument) -> KnowledgeDocumentOut:
    active = (
        session.scalar(
            select(KnowledgeIndex).where(
                KnowledgeIndex.document_id == doc.id,
                KnowledgeIndex.generation == doc.active_generation,
            )
        )
        if doc.active_generation is not None
        else None
    )
    task = session.scalar(
        select(KnowledgeTask)
        .where(KnowledgeTask.document_id == doc.id)
        .order_by(KnowledgeTask.generation.desc())
        .limit(1)
    )
    index_out = KnowledgeIndexOut.model_validate(active) if active else None
    semantic: SemanticStatus = "NOT_RUN"
    if index_out is not None:
        index_out.chunk_count = (
            session.scalar(
                select(func.count())
                .select_from(KnowledgeChunk)
                .where(KnowledgeChunk.index_id == index_out.id)
            )
            or 0
        )
        semantic = index_out.semantic_status
        if semantic == "READY" and (
            not knowledge_ai.embedding_configured()
            or index_out.embedding_version != knowledge_ai.embedding_version()
        ):
            semantic = "STALE"
        index_out.semantic_status = semantic
    elif task is not None and task.status == "RUNNING" and task.phase == "INDEXING":
        semantic = "INDEXING"
    return KnowledgeDocumentOut(
        id=doc.id,
        kb_id=doc.kb_id,
        name=doc.name,
        media_type=doc.media_type,
        content_hash=doc.content_hash,
        size_bytes=session.scalar(
            select(func.length(KnowledgeDocument.content)).where(
                KnowledgeDocument.id == doc.id
            )
        )
        or 0,
        revision=doc.revision,
        archived=doc.archived,
        generation=doc.generation,
        active_generation=doc.active_generation,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
        searchable=active is not None
        and not doc.archived
        and not get_base(session, doc.kb_id).archived,
        semantic_status=semantic,
        active_index=index_out,
        latest_task=task_out(task) if task else None,
    )


def base_out(session: Session, kb: KnowledgeBase) -> KnowledgeBaseOut:
    result = KnowledgeBaseOut.model_validate(kb)
    active = KnowledgeDocument.archived.is_(False)
    searchable = active & KnowledgeIndex.id.is_not(None) & (not kb.archived)
    semantic = (
        searchable
        & (KnowledgeIndex.semantic_status == "READY")
        & (KnowledgeIndex.embedding_version == knowledge_ai.embedding_version())
        & knowledge_ai.embedding_configured()
    )
    row = session.execute(
        select(
            func.count(KnowledgeDocument.id),
            func.sum(case((searchable, 1), else_=0)),
            func.sum(case((semantic, 1), else_=0)),
            func.sum(
                case((active & KnowledgeTask.status.in_(LIVE_STATUSES), 1), else_=0)
            ),
            func.sum(
                case(
                    (active & KnowledgeTask.status.in_(("FAILED", "INTERRUPTED")), 1),
                    else_=0,
                )
            ),
            func.sum(case((active & (KnowledgeTask.status == "PARTIAL"), 1), else_=0)),
        )
        .select_from(KnowledgeDocument)
        .outerjoin(
            KnowledgeIndex,
            (KnowledgeIndex.document_id == KnowledgeDocument.id)
            & (KnowledgeIndex.generation == KnowledgeDocument.active_generation),
        )
        .outerjoin(
            KnowledgeTask,
            (KnowledgeTask.document_id == KnowledgeDocument.id)
            & (KnowledgeTask.generation == KnowledgeDocument.generation),
        )
        .where(KnowledgeDocument.kb_id == kb.id)
    ).one()
    (
        result.document_count,
        result.searchable_count,
        result.semantic_count,
        result.processing_count,
        result.failed_count,
        result.partial_count,
    ) = (value or 0 for value in row)
    return result


@dataclass(frozen=True)
class ClaimedTask:
    id: str
    kb_id: int
    document_id: str
    generation: int
    worker_id: str
    filename: str
    media_type: str
    content: bytes


def interrupt_expired(session: Session, *, now: datetime | None = None) -> None:
    timestamp = now or datetime.now(UTC)
    session.execute(
        update(KnowledgeTask)
        .where(KnowledgeTask.status == "RUNNING", KnowledgeTask.expires_at <= timestamp)
        .values(
            status="INTERRUPTED",
            phase="FINISHED",
            finished_at=timestamp,
            error_code=ErrorCode.INTERNAL_ERROR.value,
            error_reason="knowledge_worker_expired",
            expires_at=None,
        )
    )


def interrupt_workers(session: Session, worker_ids: list[str]) -> None:
    session.execute(
        update(KnowledgeTask)
        .where(
            KnowledgeTask.worker_id.in_(worker_ids), KnowledgeTask.status == "RUNNING"
        )
        .values(
            status="INTERRUPTED",
            phase="FINISHED",
            expires_at=None,
            finished_at=datetime.now(UTC),
            error_code=ErrorCode.INTERNAL_ERROR.value,
            error_reason="knowledge_worker_stopped",
        )
    )


def claim_task(session: Session, worker_id: str) -> ClaimedTask | None:
    candidate = session.execute(
        select(KnowledgeTask.id, KnowledgeDocument.kb_id)
        .join(KnowledgeDocument, KnowledgeTask.document_id == KnowledgeDocument.id)
        .join(KnowledgeBase, KnowledgeDocument.kb_id == KnowledgeBase.id)
        .where(
            KnowledgeTask.status == "QUEUED",
            KnowledgeDocument.archived.is_(False),
            KnowledgeBase.archived.is_(False),
            KnowledgeTask.generation == KnowledgeDocument.generation,
        )
        .order_by(KnowledgeTask.created_at, KnowledgeTask.id)
        .limit(1)
    ).first()
    if candidate is None:
        return None
    base = lock_base(session, candidate.kb_id)
    task = session.get(KnowledgeTask, candidate.id, populate_existing=True)
    if task is None:
        return None
    doc = get_document(session, candidate.kb_id, task.document_id)
    if base.archived or doc.archived or doc.generation != task.generation:
        return None
    now = datetime.now(UTC)
    claimed = session.scalar(
        update(KnowledgeTask)
        .where(KnowledgeTask.id == task.id, KnowledgeTask.status == "QUEUED")
        .values(
            status="RUNNING",
            phase="EXTRACTING",
            worker_id=worker_id,
            started_at=now,
            expires_at=now + timedelta(seconds=LEASE_SECONDS),
        )
        .returning(KnowledgeTask.id)
    )
    if claimed is None:
        return None
    return ClaimedTask(
        task.id,
        doc.kb_id,
        doc.id,
        task.generation,
        worker_id,
        doc.name,
        doc.media_type,
        doc.content,
    )


def _owned(
    session: Session, claim: ClaimedTask
) -> tuple[KnowledgeBase, KnowledgeDocument, KnowledgeTask] | None:
    base = lock_base(session, claim.kb_id)
    doc = get_document(session, claim.kb_id, claim.document_id)
    task = session.scalar(
        select(KnowledgeTask)
        .where(
            KnowledgeTask.id == claim.id,
            KnowledgeTask.worker_id == claim.worker_id,
            KnowledgeTask.status == "RUNNING",
            KnowledgeTask.expires_at > datetime.now(UTC),
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if (
        task is None
        or base.archived
        or doc.archived
        or doc.generation != claim.generation
    ):
        return None
    return base, doc, task


def heartbeat(
    session: Session, claim: ClaimedTask, processed: int | None = None
) -> bool:
    owned = _owned(session, claim)
    if owned is None:
        return False
    task = owned[2]
    task.expires_at = datetime.now(UTC) + timedelta(seconds=LEASE_SECONDS)
    if processed is not None:
        task.processed_chunks = processed
    session.flush()
    return True


def stage_index(
    session: Session,
    claim: ClaimedTask,
    parsed: ParsedDocument,
    *,
    embedding_version: str | None,
    embedding_model: str | None,
) -> str | None:
    owned = _owned(session, claim)
    if owned is None:
        return None
    task = owned[2]
    index = KnowledgeIndex(
        document_id=claim.document_id,
        generation=claim.generation,
        normalized_text=parsed.normalized_text,
        parser_version=parsed.parser_version,
        chunker_version=parsed.chunker_version,
        embedding_version=embedding_version,
        embedding_model=embedding_model,
        parse_status="PARTIAL" if parsed.partial else "SUCCESS",
        semantic_status="INDEXING" if embedding_version else "NOT_CONFIGURED",
        warnings=[asdict(warning) for warning in parsed.warnings],
    )
    session.add(index)
    session.flush()
    session.add_all(
        KnowledgeChunk(
            id=f"{index.id}:{chunk.id}",
            index_id=index.id,
            text=chunk.text,
            location=asdict(chunk.location),
            section=chunk.section,
        )
        for chunk in parsed.chunks
    )
    task.phase = "INDEXING"
    task.total_chunks = len(parsed.chunks)
    session.flush()
    return index.id


def finish_failure(
    session: Session,
    claim: ClaimedTask,
    error_code: str,
    reason: str,
    *,
    interrupted: bool = False,
) -> bool:
    owned = _owned(session, claim)
    if owned is None:
        return False
    task = owned[2]
    task.status = "INTERRUPTED" if interrupted else "FAILED"
    task.phase, task.error_code, task.error_reason = "FINISHED", error_code, reason
    task.finished_at, task.expires_at = datetime.now(UTC), None
    session.flush()
    return True


def publish_index(
    session: Session,
    claim: ClaimedTask,
    index_id: str,
    vectors: list[list[float]] | None,
    *,
    error_code: str | None = None,
    error_reason: str | None = None,
) -> bool:
    owned = _owned(session, claim)
    if owned is None:
        return False
    base, doc, task = owned
    index = session.get(KnowledgeIndex, index_id)
    if (
        index is None
        or index.document_id != doc.id
        or index.generation != claim.generation
        or doc.active_generation == claim.generation
    ):
        raise invalid("knowledge_invalid_candidate")
    chunks = list(
        session.scalars(
            select(KnowledgeChunk)
            .where(KnowledgeChunk.index_id == index_id)
            .order_by(KnowledgeChunk.id)
        )
    )
    if (
        _active_chunk_count(session, base.id, exclude=doc.id) + len(chunks)
        > MAX_ACTIVE_CHUNKS
    ):
        finish_failure(
            session,
            claim,
            ErrorCode.INVALID_REQUEST.value,
            "knowledge_too_many_active_chunks",
        )
        return False
    if vectors is not None:
        if len(vectors) != len(chunks):
            raise invalid("embedding_count_mismatch")
        # Runtime passes vectors in the same stable chunk-id order.
        for chunk, vector in zip(chunks, vectors, strict=True):
            chunk.vector = vector
        index.embedding_dimensions = len(vectors[0]) if vectors else None
        index.semantic_status = "READY"
    elif error_reason is not None:
        index.semantic_status, index.error_reason = "FAILED", error_reason
    partial = index.parse_status == "PARTIAL" or error_reason is not None
    # A failed retry never replaces a usable active index. A first upload may
    # publish its extracted text explicitly as a partial, keyword-only result.
    publish = error_reason is None or doc.active_generation is None
    if publish:
        doc.active_generation = claim.generation
        base.index_revision += 1
    task.status = ("PARTIAL" if partial else "SUCCESS") if publish else "FAILED"
    task.phase, task.processed_chunks = "FINISHED", len(chunks)
    task.error_code, task.error_reason = error_code, error_reason
    task.finished_at, task.expires_at = datetime.now(UTC), None
    session.flush()
    return publish
