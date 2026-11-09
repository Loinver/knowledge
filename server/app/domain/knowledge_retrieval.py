"""Bounded retrieval and pinned document citations in the existing global scope."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.core.knowledge_ai import embedding_version
from app.domain.knowledge_ranking import (
    RANKING_VERSION,
    cosine,
    keyword_scores,
    ordered,
    reciprocal_rank_fusion,
)
from app.models.extraction import EntityIdentity, GraphTriple
from app.models.knowledge import (
    KnowledgeBase,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeIndex,
)
from app.models.knowledge_links import KnowledgeGraphLink
from app.schemas.knowledge import (
    KnowledgeCoverage,
    KnowledgeEvidenceOut,
    KnowledgeGraphEvidenceOut,
    KnowledgeGraphLinkCreate,
    KnowledgeGraphLinkOut,
    KnowledgeLocation,
    KnowledgeSearchHit,
    KnowledgeSearchOut,
    KnowledgeSearchRequest,
)


def readable_base(
    session: Session, kb_id: int, *, active: bool = True
) -> KnowledgeBase:
    base = session.get(KnowledgeBase, kb_id, populate_existing=True)
    if base is None:
        raise KGError(ErrorCode.RESOURCE_NOT_FOUND, {"kb_id": kb_id})
    if active and base.archived:
        raise KGError(ErrorCode.INVALID_REQUEST, {"reason": "knowledge_archived"})
    return base


@dataclass
class _Candidate:
    hit: KnowledgeSearchHit
    semantic_ready: bool
    dimensions: int | None


def _candidates(session: Session, base: KnowledgeBase) -> list[_Candidate]:
    rows = session.execute(
        select(
            KnowledgeChunk.id,
            KnowledgeChunk.text,
            KnowledgeChunk.location,
            KnowledgeChunk.section,
            KnowledgeIndex.id,
            KnowledgeIndex.generation,
            KnowledgeIndex.semantic_status,
            KnowledgeIndex.embedding_version,
            KnowledgeIndex.embedding_dimensions,
            KnowledgeDocument.id,
            KnowledgeDocument.name,
        )
        .join(KnowledgeIndex, KnowledgeIndex.id == KnowledgeChunk.index_id)
        .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeIndex.document_id)
        .where(
            KnowledgeDocument.kb_id == base.id,
            KnowledgeDocument.archived.is_(False),
            KnowledgeDocument.active_generation == KnowledgeIndex.generation,
        )
        .order_by(KnowledgeChunk.id)
        .limit(10001)
    )
    version = embedding_version()
    result: list[_Candidate] = []
    for (
        chunk_id,
        text,
        location,
        section,
        index_id,
        generation,
        status,
        version_id,
        dimensions,
        doc_id,
        name,
    ) in rows:
        result.append(
            _Candidate(
                KnowledgeSearchHit(
                    chunk_id=chunk_id,
                    index_id=index_id,
                    kb_id=base.id,
                    kb_name=base.name,
                    document_id=doc_id,
                    document_name=name,
                    generation=generation,
                    text=text,
                    location=KnowledgeLocation.model_validate(location),
                    section=section,
                    score=0,
                ),
                status == "READY" and version_id == version,
                dimensions,
            )
        )
    if len(result) > 10000:
        raise KGError(ErrorCode.INVALID_REQUEST, {"reason": "knowledge_index_limit"})
    return result


def _links(
    session: Session, chunk_ids: list[str]
) -> dict[str, list[KnowledgeGraphLinkOut]]:
    result: dict[str, list[KnowledgeGraphLinkOut]] = {}
    if not chunk_ids:
        return result
    for link in session.scalars(
        select(KnowledgeGraphLink)
        .where(KnowledgeGraphLink.chunk_id.in_(chunk_ids))
        .order_by(KnowledgeGraphLink.id)
    ):
        result.setdefault(link.chunk_id, []).append(
            KnowledgeGraphLinkOut.model_validate(link)
        )
    return result


def search_knowledge(
    session: Session,
    kb_id: int,
    payload: KnowledgeSearchRequest,
    query_vector: list[float] | None = None,
) -> KnowledgeSearchOut:
    from app.domain.knowledge_service import base_out

    base = readable_base(session, kb_id)
    summary = base_out(session, base)
    active_documents = (
        session.scalar(
            select(func.count())
            .select_from(KnowledgeDocument)
            .where(
                KnowledgeDocument.kb_id == kb_id, KnowledgeDocument.archived.is_(False)
            )
        )
        or 0
    )
    candidates = _candidates(session, base)
    by_id = {item.hit.chunk_id: item for item in candidates}
    semantic_ids = {key for key, item in by_id.items() if item.semantic_ready}
    semantic: dict[str, float] = {}
    lexical: dict[str, float] = {}
    if payload.mode != "SEMANTIC":
        lexical = keyword_scores(
            payload.q, {key: item.hit.text for key, item in by_id.items()}
        )
    if payload.mode != "KEYWORD":
        if not semantic_ids and active_documents:
            raise KGError(
                ErrorCode.INVALID_REQUEST,
                {"reason": "knowledge_semantic_index_not_ready"},
            )
        if semantic_ids and query_vector is None:
            raise KGError(ErrorCode.LLM_NOT_CONFIGURED, {"capability": "embeddings"})
        # Stream vectors in bounded batches; avoid materializing a full vector corpus.
        indexes = {item.hit.index_id for item in candidates if item.semantic_ready}
        if indexes:
            vectors = session.execute(
                select(KnowledgeChunk.id, KnowledgeChunk.vector)
                .where(KnowledgeChunk.index_id.in_(indexes))
                .execution_options(yield_per=32)
            )
            for chunk_id, vector in vectors:
                if (
                    chunk_id not in semantic_ids
                    or not isinstance(vector, list)
                    or not query_vector
                ):
                    raise KGError(
                        ErrorCode.INVALID_REQUEST, {"reason": "knowledge_index_corrupt"}
                    )
                if len(vector) != by_id[chunk_id].dimensions or len(vector) != len(
                    query_vector
                ):
                    raise KGError(
                        ErrorCode.INVALID_REQUEST,
                        {"reason": "knowledge_index_dimension_mismatch"},
                    )
                try:
                    score = cosine(query_vector, vector)
                except (KGError, TypeError, ValueError) as exc:
                    raise KGError(
                        ErrorCode.INVALID_REQUEST, {"reason": "knowledge_index_corrupt"}
                    ) from exc
                if score >= payload.min_similarity:
                    semantic[chunk_id] = score
    scores = (
        lexical
        if payload.mode == "KEYWORD"
        else semantic
        if payload.mode == "SEMANTIC"
        else reciprocal_rank_fusion(lexical, semantic)
    )
    keys = ordered(scores)[: payload.top_k]
    links = _links(session, keys)
    items = [
        by_id[key].hit.model_copy(
            update={
                "score": scores[key],
                "keyword_score": lexical.get(key),
                "similarity": semantic.get(key),
                "graph_links": links.get(key, []),
            }
        )
        for key in keys
    ]
    return KnowledgeSearchOut(
        query=payload.q,
        mode=payload.mode,
        items=items,
        total_matches=len(scores),
        top_k=payload.top_k,
        min_similarity=payload.min_similarity,
        ranking_version=RANKING_VERSION,
        embedding_version=embedding_version() if payload.mode != "KEYWORD" else None,
        coverage=KnowledgeCoverage(
            total_documents=active_documents,
            searchable_documents=summary.searchable_count,
            semantic_documents=summary.semantic_count,
            failed_documents=summary.failed_count,
            processing_documents=summary.processing_count,
            partial_documents=summary.partial_count,
            searched_chunks=len(semantic_ids)
            if payload.mode == "SEMANTIC"
            else len(candidates),
            excluded_semantic_chunks=(len(candidates) - len(semantic_ids))
            if payload.mode != "KEYWORD"
            else 0,
        ),
    )


def evidence_detail(
    session: Session, kb_id: int, chunk_id: str
) -> KnowledgeEvidenceOut:
    base = readable_base(session, kb_id, active=False)
    chunk = session.get(KnowledgeChunk, chunk_id)
    index = session.get(KnowledgeIndex, chunk.index_id) if chunk else None
    document = (
        session.get(KnowledgeDocument, index.document_id, populate_existing=True)
        if index
        else None
    )
    if not chunk or not index or not document or document.kb_id != kb_id:
        raise KGError(ErrorCode.RESOURCE_NOT_FOUND)
    links = _links(session, [chunk.id])
    return KnowledgeEvidenceOut(
        hit=KnowledgeSearchHit(
            chunk_id=chunk.id,
            index_id=index.id,
            kb_id=kb_id,
            kb_name=base.name,
            document_id=document.id,
            document_name=document.name,
            generation=index.generation,
            text=chunk.text,
            location=KnowledgeLocation.model_validate(chunk.location),
            section=chunk.section,
            score=0,
            graph_links=links.get(chunk.id, []),
        ),
        normalized_text=index.normalized_text,
        parser_version=index.parser_version,
        chunker_version=index.chunker_version,
        historical=document.active_generation != index.generation,
        archived=base.archived or document.archived,
    )


def assert_answer_sources_current(
    session: Session, kb_id: int, result: KnowledgeSearchOut
) -> None:
    readable_base(session, kb_id)
    # Re-check after model inference: archiving or rebuilding must not leak stale
    # passages into a fresh answer. The caller ended its read transaction first.
    for item in result.items:
        document = session.get(
            KnowledgeDocument, item.document_id, populate_existing=True
        )
        if (
            not document
            or document.archived
            or document.active_generation != item.generation
        ):
            raise KGError(
                ErrorCode.REVISION_CONFLICT, {"reason": "knowledge_search_changed"}
            )


def link_graph_evidence(
    session: Session,
    kb_id: int,
    chunk_id: str,
    payload: KnowledgeGraphLinkCreate,
    actor_id: str,
    if_match: int,
) -> KnowledgeGraphLinkOut:
    # Serialize with publication/archive on the same aggregate on SQLite and PG.
    from app.domain.knowledge_service import lock_base

    lock_base(session, kb_id)
    detail = evidence_detail(session, kb_id, chunk_id)
    if detail.archived or detail.historical:
        raise KGError(
            ErrorCode.INVALID_REQUEST, {"reason": "knowledge_evidence_readonly"}
        )
    document = session.get(
        KnowledgeDocument, detail.hit.document_id, populate_existing=True
    )
    assert document is not None
    existing = session.scalar(
        select(KnowledgeGraphLink).where(
            KnowledgeGraphLink.chunk_id == chunk_id,
            KnowledgeGraphLink.graph_revision_id == payload.graph_revision_id,
            KnowledgeGraphLink.entity_iri == payload.entity_iri,
            KnowledgeGraphLink.fact_id == payload.fact_id,
        )
    )
    if existing:
        return KnowledgeGraphLinkOut.model_validate(existing)
    if document.revision != if_match:
        raise KGError(
            ErrorCode.REVISION_CONFLICT,
            {"expected": if_match, "actual": document.revision},
        )
    entity = session.scalar(
        select(EntityIdentity).where(
            EntityIdentity.graph_revision_id == payload.graph_revision_id,
            EntityIdentity.iri == payload.entity_iri,
        )
    )
    if entity is None:
        raise KGError(
            ErrorCode.RESOURCE_NOT_FOUND, {"reason": "graph_entity_not_found"}
        )
    fact = (
        session.get(GraphTriple, payload.fact_id)
        if payload.fact_id is not None
        else None
    )
    if payload.fact_id is not None and (
        not fact
        or fact.graph_revision_id != payload.graph_revision_id
        or payload.entity_iri != fact.subject
    ):
        raise KGError(ErrorCode.INVALID_REQUEST, {"reason": "graph_fact_mismatch"})
    link = KnowledgeGraphLink(
        chunk_id=chunk_id,
        graph_revision_id=payload.graph_revision_id,
        entity_iri=payload.entity_iri,
        fact_id=payload.fact_id,
        created_by=actor_id,
        predicate=fact.predicate if fact else None,
        object_iri=fact.object_ if fact else None,
    )
    session.add(link)
    document.revision += 1
    session.flush()
    return KnowledgeGraphLinkOut.model_validate(link)


def graph_document_evidence(
    session: Session,
    graph_revision_id: int,
    entity_iri: str,
    fact_id: int | None = None,
) -> list[KnowledgeGraphEvidenceOut]:
    stmt = (
        select(KnowledgeGraphLink.chunk_id, KnowledgeDocument.kb_id)
        .join(KnowledgeChunk, KnowledgeChunk.id == KnowledgeGraphLink.chunk_id)
        .join(KnowledgeIndex, KnowledgeIndex.id == KnowledgeChunk.index_id)
        .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeIndex.document_id)
        .join(KnowledgeBase, KnowledgeBase.id == KnowledgeDocument.kb_id)
        .where(
            KnowledgeGraphLink.graph_revision_id == graph_revision_id,
            KnowledgeGraphLink.entity_iri == entity_iri,
            KnowledgeBase.archived.is_(False),
            KnowledgeDocument.archived.is_(False),
        )
    )
    if fact_id is not None:
        stmt = stmt.where(KnowledgeGraphLink.fact_id == fact_id)
    references = session.execute(
        stmt.distinct().order_by(KnowledgeGraphLink.chunk_id).limit(50)
    ).all()
    result: list[KnowledgeGraphEvidenceOut] = []
    for chunk_id, kb_id in references:
        detail = evidence_detail(session, kb_id, chunk_id)
        # A document or base may have been archived since the reference snapshot.
        if detail.archived:
            continue
        result.append(
            KnowledgeGraphEvidenceOut(
                **detail.hit.model_dump(), historical=detail.historical
            )
        )
    return result


def original_document(
    session: Session, kb_id: int, document_id: str
) -> tuple[bytes, str]:
    readable_base(session, kb_id, active=False)
    document = session.get(KnowledgeDocument, document_id)
    if not document or document.kb_id != kb_id:
        raise KGError(ErrorCode.RESOURCE_NOT_FOUND)
    return document.content, document.name
