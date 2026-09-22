"""M-04 装配模板维护接口。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.api.v1.governance_common import (
    GovernanceRoute,
    governance_session,
    required_revision,
)
from app.domain import template_service as service
from app.domain.ontology_service import create_ontology
from app.schemas.ontology import OntologyCreate, OntologyOut
from app.schemas.template import (
    TemplateCreate,
    TemplateFromOntology,
    TemplateInstantiate,
    TemplateLink,
    TemplateMetadata,
    TemplateOut,
    TemplatePage,
    TemplateResourcePage,
)

router = APIRouter(
    prefix="/governance/templates", tags=["governance"], route_class=GovernanceRoute
)


@router.get("", response_model=TemplatePage)
def list_templates(
    q: str = Query("", max_length=256),
    builtin: bool | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    session: Session = Depends(governance_session),
) -> TemplatePage:
    items, total = service.list_templates(session, q, builtin, page, page_size)
    return TemplatePage(
        items=[service.template_out(session, item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/resources", response_model=TemplateResourcePage)
def list_resources(
    q: str = Query("", max_length=256),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    session: Session = Depends(governance_session),
) -> TemplateResourcePage:
    return service.resource_catalog(session, q, page, page_size)


@router.post("", response_model=TemplateOut, status_code=201)
def create_template(
    payload: TemplateCreate,
    response: Response,
    session: Session = Depends(governance_session),
) -> TemplateOut:
    with session.begin():
        result = service.template_out(
            session, service.create_template(session, payload)
        )
    response.headers["ETag"] = f'"{result.revision}"'
    return result


@router.post("/from-ontology", response_model=TemplateOut, status_code=201)
def from_ontology(
    payload: TemplateFromOntology, session: Session = Depends(governance_session)
) -> TemplateOut:
    with session.begin():
        return service.template_out(session, service.from_ontology(session, payload))


@router.get("/{template_id}", response_model=TemplateOut)
def get_template(
    template_id: int, response: Response, session: Session = Depends(governance_session)
) -> TemplateOut:
    result = service.template_out(session, service.get_template(session, template_id))
    response.headers["ETag"] = f'"{result.revision}"'
    return result


@router.put("/{template_id}", response_model=TemplateOut)
def update_template(
    template_id: int,
    payload: TemplateCreate,
    response: Response,
    revision: int = Depends(required_revision),
    session: Session = Depends(governance_session),
) -> TemplateOut:
    with session.begin():
        result = service.template_out(
            session, service.update_template(session, template_id, revision, payload)
        )
    response.headers["ETag"] = f'"{result.revision}"'
    return result


@router.delete("/{template_id}", status_code=204)
def delete_template(
    template_id: int,
    revision: int = Depends(required_revision),
    session: Session = Depends(governance_session),
) -> None:
    with session.begin():
        service.delete_template(session, template_id, revision)


@router.post("/{template_id}/copy", response_model=TemplateOut, status_code=201)
def copy_template(
    template_id: int,
    payload: TemplateMetadata,
    revision: int = Depends(required_revision),
    session: Session = Depends(governance_session),
) -> TemplateOut:
    with session.begin():
        return service.template_out(
            session, service.copy_template(session, template_id, revision, payload)
        )


@router.post("/{template_id}/instantiate", response_model=OntologyOut, status_code=201)
def instantiate(
    template_id: int,
    payload: TemplateInstantiate,
    revision: int = Depends(required_revision),
    session: Session = Depends(governance_session),
) -> OntologyOut:
    with session.begin():
        template = service.lock_template(session, template_id, revision)
        onto = create_ontology(
            session, OntologyCreate(**payload.model_dump(), template_id=template_id)
        )
        result = OntologyOut.model_validate(onto)
        result.template = TemplateLink.model_validate(template)
        return result
