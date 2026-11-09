"""Read-only retrieval/answers and explicit graph-reference write boundaries."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from contextlib import suppress
from urllib.parse import quote

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from sqlalchemy.orm import Session

from app.api.v1.deps import current_user
from app.core.db import get_session
from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.core.knowledge_ai import (
    chat_client,
    embedding_client,
    embedding_configured,
    embedding_version,
)
from app.domain.knowledge_answering import EvidencePassage, answer_from_evidence
from app.domain.knowledge_retrieval import (
    assert_answer_sources_current,
    evidence_detail,
    graph_document_evidence,
    link_graph_evidence,
    original_document,
    readable_base,
    search_knowledge,
)
from app.models.account import User
from app.schemas.knowledge import (
    KnowledgeAnswerCitation,
    KnowledgeAnswerOut,
    KnowledgeCapabilities,
    KnowledgeEvidenceOut,
    KnowledgeGraphEvidenceOut,
    KnowledgeGraphLinkCreate,
    KnowledgeGraphLinkOut,
    KnowledgeSearchOut,
    KnowledgeSearchRequest,
)
from app.schemas.response import ApiResponse

router = APIRouter(prefix="/knowledge-bases", tags=["knowledge-bases"])


async def _while_connected[T](request: Request, operation: Awaitable[T]) -> T:
    task = asyncio.ensure_future(operation)
    try:
        while not task.done():
            if await request.is_disconnected():
                raise KGError(
                    ErrorCode.INVALID_REQUEST, {"reason": "request_cancelled"}
                )
            await asyncio.wait({task}, timeout=0.2)
        return await task
    finally:
        if not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task


@router.get("/capabilities", response_model=ApiResponse[KnowledgeCapabilities])
def capabilities() -> KnowledgeCapabilities:
    embedding = embedding_client()
    return KnowledgeCapabilities(
        chat_configured=chat_client().endpoint.configured,
        embedding_configured=embedding.endpoint.configured,
        embedding_model=embedding.endpoint.model
        if embedding.endpoint.configured
        else None,
        embedding_version=embedding_version()
        if embedding.endpoint.configured
        else None,
    )


@router.get(
    "/graph-evidence", response_model=ApiResponse[list[KnowledgeGraphEvidenceOut]]
)
def graph_references(
    graph_revision_id: int = Query(ge=1),
    entity_iri: str = Query(min_length=1, max_length=2000),
    fact_id: int | None = Query(None, ge=1),
    session: Session = Depends(get_session),
) -> list[KnowledgeGraphEvidenceOut]:
    return graph_document_evidence(session, graph_revision_id, entity_iri, fact_id)


async def _search(
    request: Request,
    session: Session,
    kb_id: int,
    payload: KnowledgeSearchRequest,
) -> KnowledgeSearchOut:
    readable_base(session, kb_id)
    vector: list[float] | None = None
    if payload.mode != "KEYWORD":
        if not embedding_configured():
            raise KGError(ErrorCode.LLM_NOT_CONFIGURED, {"capability": "embeddings"})
        session.rollback()
        vectors = await _while_connected(request, embedding_client().embed([payload.q]))
        vector = vectors[0]
    return await _while_connected(
        request, _rank_in_worker(session, kb_id, payload, vector)
    )


async def _rank_in_worker(
    session: Session,
    kb_id: int,
    payload: KnowledgeSearchRequest,
    vector: list[float] | None,
) -> KnowledgeSearchOut:
    # SQL decoding and exact vector scoring can take seconds at the corpus cap.
    # Keep the event loop available for other requests and ingestion heartbeats.
    work = asyncio.create_task(
        asyncio.to_thread(search_knowledge, session, kb_id, payload, vector)
    )
    try:
        return await asyncio.shield(work)
    except asyncio.CancelledError:
        # A Python worker cannot be force-stopped. Join its bounded read before
        # FastAPI disposes the request session; never use that session concurrently.
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


@router.post("/{kb_id}/search", response_model=ApiResponse[KnowledgeSearchOut])
async def search(
    kb_id: int,
    payload: KnowledgeSearchRequest,
    request: Request,
    session: Session = Depends(get_session),
) -> KnowledgeSearchOut:
    return await _search(request, session, kb_id, payload)


@router.post("/{kb_id}/answer", response_model=ApiResponse[KnowledgeAnswerOut])
async def answer(
    kb_id: int,
    payload: KnowledgeSearchRequest,
    request: Request,
    session: Session = Depends(get_session),
) -> KnowledgeAnswerOut:
    retrieval = await _search(request, session, kb_id, payload)
    sources = retrieval.items[:6]
    session.rollback()
    result = await _while_connected(
        request,
        answer_from_evidence(
            chat_client(),
            payload.q,
            [EvidencePassage(item.chunk_id, item.text) for item in sources],
        ),
    )
    assert_answer_sources_current(session, kb_id, retrieval)
    by_id = {item.chunk_id: item for item in sources}
    return KnowledgeAnswerOut(
        status=result.status,
        question=payload.q,
        retrieval=retrieval,
        citations=[
            KnowledgeAnswerCitation(quote=item.quote, source=by_id[item.chunk_id])
            for item in result.citations
        ],
    )


@router.get(
    "/{kb_id}/evidence/{chunk_id}", response_model=ApiResponse[KnowledgeEvidenceOut]
)
def evidence(
    kb_id: int, chunk_id: str, session: Session = Depends(get_session)
) -> KnowledgeEvidenceOut:
    return evidence_detail(session, kb_id, chunk_id)


@router.post(
    "/{kb_id}/evidence/{chunk_id}/links",
    response_model=ApiResponse[KnowledgeGraphLinkOut],
    status_code=201,
)
def add_link(
    kb_id: int,
    chunk_id: str,
    payload: KnowledgeGraphLinkCreate,
    if_match: int = Header(ge=1),
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> KnowledgeGraphLinkOut:
    result = link_graph_evidence(session, kb_id, chunk_id, payload, user.id, if_match)
    session.commit()
    return result


@router.get("/{kb_id}/documents/{document_id}/original")
def original(
    kb_id: int, document_id: str, session: Session = Depends(get_session)
) -> Response:
    content, filename = original_document(session, kb_id, document_id)
    return Response(
        content=content,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": "attachment; filename*=UTF-8''" + quote(filename),
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )
