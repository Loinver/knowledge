"""规则库接口。编辑、删除与测试均绑定明确的保存版本。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.api.v1.governance_common import (
    GovernanceRoute,
    governance_session,
    required_revision,
)
from app.domain import rule_service
from app.schemas.governance import (
    RuleCreate,
    RuleOut,
    RulePage,
    RuleSort,
    RuleSourceKind,
    RuleTestOut,
)

router = APIRouter(
    prefix="/governance/rules", tags=["governance"], route_class=GovernanceRoute
)


@router.get("", response_model=RulePage)
def list_rules_endpoint(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    q: str = Query("", max_length=256),
    source_kind: RuleSourceKind | None = None,
    sort: RuleSort = "identifier",
    session: Session = Depends(governance_session),
) -> RulePage:
    items, total = rule_service.list_rules(
        session, page=page, page_size=page_size, q=q, source_kind=source_kind, sort=sort
    )
    return RulePage(
        items=[RuleOut.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=RuleOut, status_code=201)
def create_rule_endpoint(
    payload: RuleCreate,
    response: Response,
    session: Session = Depends(governance_session),
) -> RuleOut:
    with session.begin():
        rule = rule_service.create_rule(session, payload)
        result = RuleOut.model_validate(rule)
    response.headers["ETag"] = f'"{result.revision}"'
    return result


@router.get("/{rule_id}", response_model=RuleOut)
def get_rule_endpoint(
    rule_id: int, response: Response, session: Session = Depends(governance_session)
) -> RuleOut:
    result = RuleOut.model_validate(rule_service.get_rule(session, rule_id))
    response.headers["ETag"] = f'"{result.revision}"'
    return result


@router.put("/{rule_id}", response_model=RuleOut)
def update_rule_endpoint(
    rule_id: int,
    payload: RuleCreate,
    response: Response,
    revision: int = Depends(required_revision),
    session: Session = Depends(governance_session),
) -> RuleOut:
    with session.begin():
        rule = rule_service.update_rule(session, rule_id, payload, revision)
        result = RuleOut.model_validate(rule)
    response.headers["ETag"] = f'"{result.revision}"'
    return result


@router.delete("/{rule_id}", status_code=204)
def delete_rule_endpoint(
    rule_id: int,
    revision: int = Depends(required_revision),
    session: Session = Depends(governance_session),
) -> None:
    with session.begin():
        rule_service.delete_rule(session, rule_id, revision)


@router.post("/{rule_id}/test", response_model=RuleTestOut)
def test_rule_endpoint(
    rule_id: int,
    revision: int = Depends(required_revision),
    session: Session = Depends(governance_session),
) -> RuleTestOut:
    return rule_service.test_rule(session, rule_id, revision)
