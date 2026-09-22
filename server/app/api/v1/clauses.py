"""标准条款资料接口（M-03）。只存条款编号 + 自撰描述，不附标准正文。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.api.v1.governance_common import (
    GovernanceRoute,
    governance_session,
    required_revision,
)
from app.domain import clause_service
from app.schemas.governance import (
    ClauseSort,
    StandardClauseBrief,
    StandardClauseCreate,
    StandardClauseOut,
    StandardClausePage,
    StandardClauseUpdate,
)
from app.schemas.response import ApiResponse

router = APIRouter(
    prefix="/governance/clauses", tags=["governance"], route_class=GovernanceRoute
)


@router.get("", response_model=ApiResponse[StandardClausePage])
def list_clauses_endpoint(
    q: str = Query("", max_length=640),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    sort: ClauseSort | None = Query(
        None, description="为空时按标准号 → 条款号升序（索引默认序）"
    ),
    session: Session = Depends(governance_session),
) -> StandardClausePage:
    items, total = clause_service.list_clauses(session, q, page, page_size, sort)
    return StandardClausePage(
        items=[StandardClauseBrief.model_validate(i) for i in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=ApiResponse[StandardClauseOut], status_code=201)
def create_clause_endpoint(
    payload: StandardClauseCreate,
    response: Response,
    session: Session = Depends(governance_session),
) -> StandardClauseOut:
    with session.begin():
        clause = clause_service.create_clause(session, payload)
        result = StandardClauseOut.model_validate(clause)
    response.headers["ETag"] = f'"{result.revision}"'
    return result


@router.get("/{clause_id}", response_model=ApiResponse[StandardClauseOut])
def get_clause_endpoint(
    clause_id: int,
    response: Response,
    session: Session = Depends(governance_session),
) -> StandardClauseOut:
    clause = clause_service.get_clause(session, clause_id)
    result = StandardClauseOut.model_validate(clause)
    response.headers["ETag"] = f'"{result.revision}"'
    return result


@router.put("/{clause_id}", response_model=ApiResponse[StandardClauseOut])
def update_clause_endpoint(
    clause_id: int,
    payload: StandardClauseUpdate,
    response: Response,
    revision: int = Depends(required_revision),
    session: Session = Depends(governance_session),
) -> StandardClauseOut:
    with session.begin():
        clause = clause_service.update_clause(session, clause_id, payload, revision)
        result = StandardClauseOut.model_validate(clause)
    response.headers["ETag"] = f'"{result.revision}"'
    return result


@router.delete("/{clause_id}", response_model=ApiResponse[None])
def delete_clause_endpoint(
    clause_id: int,
    revision: int = Depends(required_revision),
    session: Session = Depends(governance_session),
) -> None:
    with session.begin():
        clause_service.delete_clause(session, clause_id, revision)
