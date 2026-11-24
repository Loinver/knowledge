"""本体冻结内容只读路由；授权由主应用 business_router 统一提供。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Path
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.domain.ontology_history_service import (
    get_revision_contents,
    get_revision_resource,
    get_revision_rule,
)
from app.schemas.ontology_history import (
    OntologyHistoryResourceOut,
    OntologyHistoryRuleOut,
    OntologyRevisionContents,
)
from app.schemas.response import ApiResponse

router = APIRouter(prefix="/ontologies", tags=["ontologies"])


@router.get(
    "/{ontology_id}/revisions/{revision}/contents",
    response_model=ApiResponse[OntologyRevisionContents],
)
def revision_contents_endpoint(
    ontology_id: int = Path(ge=1),
    revision: int = Path(ge=1),
    session: Session = Depends(get_session),
) -> OntologyRevisionContents:
    return get_revision_contents(session, ontology_id, revision)


@router.get(
    "/{ontology_id}/revisions/{revision}/resources/{resource_id}",
    response_model=ApiResponse[OntologyHistoryResourceOut],
)
def revision_resource_endpoint(
    ontology_id: int = Path(ge=1),
    revision: int = Path(ge=1),
    resource_id: int = Path(ge=1),
    session: Session = Depends(get_session),
) -> OntologyHistoryResourceOut:
    return get_revision_resource(session, ontology_id, revision, resource_id)


@router.get(
    "/{ontology_id}/revisions/{revision}/rules/{rule_id}",
    response_model=ApiResponse[OntologyHistoryRuleOut],
)
def revision_rule_endpoint(
    ontology_id: int = Path(ge=1),
    revision: int = Path(ge=1),
    rule_id: int = Path(ge=1),
    session: Session = Depends(get_session),
) -> OntologyHistoryRuleOut:
    return get_revision_rule(session, ontology_id, revision, rule_id)
