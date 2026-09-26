"""AI 建议路由（第三批）：生成可解释建议，人工逐条确认后落库。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.domain.ai_suggestion_service import (
    apply_suggestion,
    discard_suggestion,
    extract_document_facts,
    get_suggestion,
    list_suggestions,
    suggest_mapping,
    suggest_ontology_completion,
)
from app.models.governance import AiSuggestion
from app.schemas.ai import AiSuggestionOut, DocumentExtractRequest
from app.schemas.response import ApiResponse

router = APIRouter(prefix="/ai", tags=["ai"])


def _out(item: AiSuggestion) -> AiSuggestionOut:
    return AiSuggestionOut.model_validate(item)


@router.post(
    "/ontologies/{ontology_id}/suggest-completion",
    response_model=ApiResponse[list[AiSuggestionOut]],
)
def suggest_completion(
    ontology_id: int, session: Session = Depends(get_session)
) -> list[AiSuggestionOut]:
    """为草稿类型建议缺失的双语标签/定义（仅草稿资源）。"""
    items = suggest_ontology_completion(session, ontology_id)
    session.commit()
    return [_out(item) for item in items]


@router.post(
    "/mappings/{mapping_id}/suggest-mapping",
    response_model=ApiResponse[list[AiSuggestionOut]],
)
def suggest_mapping_route(
    mapping_id: int,
    datasource_id: int = Query(..., ge=1),
    session: Session = Depends(get_session),
) -> list[AiSuggestionOut]:
    """按源表结构与本体类型建议字段映射（应用到映射草稿）。"""
    items = suggest_mapping(session, mapping_id, datasource_id)
    session.commit()
    return [_out(item) for item in items]


@router.post(
    "/documents/extract", response_model=ApiResponse[list[AiSuggestionOut]]
)
def extract_facts(
    payload: DocumentExtractRequest, session: Session = Depends(get_session)
) -> list[AiSuggestionOut]:
    """从文本抽取候选事实（仅审阅；应用不落库）。"""
    items = extract_document_facts(session, payload.ontology_id, payload.text)
    session.commit()
    return [_out(item) for item in items]


@router.get("/suggestions", response_model=ApiResponse[list[AiSuggestionOut]])
def list_all_suggestions(
    kind: str | None = Query(None),
    status: str | None = Query(None),
    session: Session = Depends(get_session),
) -> list[AiSuggestionOut]:
    return [_out(item) for item in list_suggestions(session, kind, status)]


@router.post(
    "/suggestions/{suggestion_id}/apply", response_model=ApiResponse[AiSuggestionOut]
)
def apply_one(
    suggestion_id: int, session: Session = Depends(get_session)
) -> AiSuggestionOut:
    item = apply_suggestion(session, suggestion_id)
    session.commit()
    return _out(item)


@router.post(
    "/suggestions/{suggestion_id}/discard", response_model=ApiResponse[AiSuggestionOut]
)
def discard_one(
    suggestion_id: int, session: Session = Depends(get_session)
) -> AiSuggestionOut:
    item = discard_suggestion(session, suggestion_id)
    session.commit()
    return _out(item)


@router.get("/suggestions/{suggestion_id}", response_model=ApiResponse[AiSuggestionOut])
def get_one(
    suggestion_id: int, session: Session = Depends(get_session)
) -> AiSuggestionOut:
    return _out(get_suggestion(session, suggestion_id))
