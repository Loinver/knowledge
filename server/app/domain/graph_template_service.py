"""视图模板（H-33 第二批）：形态配置持久化 + 本体版本失效检测。

模板钉住创建时的本体版本；本体发布更新版本后 stale=True，
前端显式提示"模板基于旧版本本体"，不静默沿用。
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.models.domain import Ontology
from app.models.enums import ResourceStatus
from app.models.governance import ViewTemplate
from app.schemas.graph_view import ViewTemplateCreate

MAX_PAGE_SIZE = 200


def create_template(session: Session, payload: ViewTemplateCreate) -> ViewTemplate:
    onto = session.get(Ontology, payload.ontology_id)
    if onto is None:
        raise KGError(
            ErrorCode.RESOURCE_NOT_FOUND, {"ontology_id": payload.ontology_id}
        )
    if onto.status != ResourceStatus.PUBLISHED:
        raise KGError(
            ErrorCode.VALIDATION_VIOLATION,
            {"ontology_id": onto.id, "reason": "ontology_not_published"},
        )
    template = ViewTemplate(
        name_i18n=payload.name_i18n,
        layout_id=payload.layout_id,
        config=payload.config,
        ontology_id=payload.ontology_id,
        ontology_revision=payload.ontology_revision,
    )
    session.add(template)
    session.flush()
    return template


def list_templates(
    session: Session, ontology_id: int | None = None, page: int = 1, page_size: int = 50
) -> tuple[list[ViewTemplate], int]:
    stmt = select(ViewTemplate)
    if ontology_id is not None:
        stmt = stmt.where(ViewTemplate.ontology_id == ontology_id)
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    page_size = min(max(page_size, 1), MAX_PAGE_SIZE)
    items = list(
        session.scalars(
            stmt.order_by(ViewTemplate.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return items, total


def get_template(session: Session, template_id: int) -> ViewTemplate:
    template = session.get(ViewTemplate, template_id)
    if template is None:
        raise KGError(ErrorCode.RESOURCE_NOT_FOUND, {"view_template_id": template_id})
    return template


def delete_template(session: Session, template_id: int) -> None:
    session.delete(get_template(session, template_id))
    session.flush()


def template_stale(session: Session, template: ViewTemplate) -> bool:
    """本体已发布比模板钉扎版本更新的版本 → 失效。"""
    onto = session.get(Ontology, template.ontology_id)
    if onto is None:
        return True
    return onto.current_revision > template.ontology_revision
