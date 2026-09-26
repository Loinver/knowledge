"""视图模板路由：图谱形态配置的持久化与失效提示。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.domain.graph_template_service import (
    create_template,
    delete_template,
    get_template,
    list_templates,
    template_stale,
)
from app.models.governance import ViewTemplate
from app.schemas.graph_view import ViewTemplateCreate, ViewTemplateOut, ViewTemplatePage
from app.schemas.response import ApiResponse

router = APIRouter(prefix="/view-templates", tags=["view-templates"])


def _out(session: Session, template: ViewTemplate) -> ViewTemplateOut:
    data = ViewTemplateOut.model_validate(template)
    return data.model_copy(update={"stale": template_stale(session, template)})


@router.get("", response_model=ApiResponse[ViewTemplatePage])
def list_view_templates(
    ontology_id: int | None = Query(None, ge=1),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    session: Session = Depends(get_session),
) -> ViewTemplatePage:
    items, total = list_templates(session, ontology_id, page, page_size)
    return ViewTemplatePage(
        items=[_out(session, item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=ApiResponse[ViewTemplateOut], status_code=201)
def create_view_template(
    payload: ViewTemplateCreate, session: Session = Depends(get_session)
) -> ViewTemplateOut:
    template = create_template(session, payload)
    session.commit()
    return _out(session, template)


@router.get("/{template_id}", response_model=ApiResponse[ViewTemplateOut])
def get_view_template(
    template_id: int, session: Session = Depends(get_session)
) -> ViewTemplateOut:
    return _out(session, get_template(session, template_id))


@router.delete("/{template_id}", response_model=ApiResponse[None])
def delete_view_template(
    template_id: int, session: Session = Depends(get_session)
) -> None:
    delete_template(session, template_id)
    session.commit()
