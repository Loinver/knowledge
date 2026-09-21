"""业务域管理路由（H-10）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.domain.domain_service import (
    add_member,
    check_publish,
    create_domain,
    get_domain,
    list_domains,
    list_members,
    publish_domain,
    remove_member,
    update_domain,
)
from app.schemas.domain import (
    DomainBrief,
    DomainCreate,
    DomainMemberAdd,
    DomainMemberOut,
    DomainOut,
    DomainUpdate,
    PublishCheckResult,
)

router = APIRouter(prefix="/domains", tags=["domains"])


@router.get("", response_model=list[DomainBrief])
def list_domain(
    q: str = Query(""),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    session: Session = Depends(get_session),
) -> list[DomainBrief]:
    items, _total = list_domains(session, q, page, page_size)
    return [DomainBrief.model_validate(i) for i in items]


@router.post("", response_model=DomainOut, status_code=201)
def create_domain_endpoint(
    payload: DomainCreate, session: Session = Depends(get_session)
) -> DomainOut:
    domain = create_domain(session, payload)
    session.commit()
    return DomainOut.model_validate(domain)


@router.get("/{domain_id}", response_model=DomainOut)
def get_domain_endpoint(
    domain_id: int, session: Session = Depends(get_session)
) -> DomainOut:
    domain = get_domain(session, domain_id)
    return DomainOut.model_validate(domain)


@router.put("/{domain_id}", response_model=DomainOut)
def update_domain_endpoint(
    domain_id: int,
    payload: DomainUpdate,
    session: Session = Depends(get_session),
) -> DomainOut:
    domain = get_domain(session, domain_id)
    update_domain(session, domain, payload)
    session.commit()
    return DomainOut.model_validate(domain)


@router.get("/{domain_id}/members", response_model=list[DomainMemberOut])
def list_members_endpoint(
    domain_id: int, session: Session = Depends(get_session)
) -> list[DomainMemberOut]:
    members = list_members(session, domain_id)
    return [DomainMemberOut.model_validate(m) for m in members]


@router.post("/{domain_id}/members", response_model=DomainMemberOut, status_code=201)
def add_member_endpoint(
    domain_id: int,
    payload: DomainMemberAdd,
    session: Session = Depends(get_session),
) -> DomainMemberOut:
    member = add_member(session, domain_id, payload)
    session.commit()
    return DomainMemberOut.model_validate(member)


@router.delete("/{domain_id}/members/{member_id}", status_code=204)
def remove_member_endpoint(
    domain_id: int, member_id: int, session: Session = Depends(get_session)
) -> None:
    remove_member(session, domain_id, member_id)
    session.commit()


@router.get("/{domain_id}/publish-check", response_model=PublishCheckResult)
def publish_check_endpoint(
    domain_id: int, session: Session = Depends(get_session)
) -> PublishCheckResult:
    domain = get_domain(session, domain_id)
    return check_publish(session, domain)


@router.post("/{domain_id}/publish")
def publish_domain_endpoint(
    domain_id: int, session: Session = Depends(get_session)
) -> dict:
    domain = get_domain(session, domain_id)
    revision = publish_domain(session, domain)
    session.commit()
    return {"revision": revision}
