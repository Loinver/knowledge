"""标准条款资料服务（M-03）：条款编号 + 自撰描述，不抄正文。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.models.governance import StandardClause
from app.schemas.governance import (
    ClauseSort,
    StandardClauseCreate,
    StandardClauseUpdate,
)


def get_clause(session: Session, clause_id: int) -> StandardClause:
    clause = session.get(StandardClause, clause_id, populate_existing=True)
    if clause is None:
        raise KGError(ErrorCode.RESOURCE_NOT_FOUND, {"clause_id": clause_id})
    return clause


def check_revision(clause: StandardClause, revision: int) -> None:
    if clause.revision != revision:
        raise KGError(
            ErrorCode.REVISION_CONFLICT,
            {"clause_id": clause.id, "expected": revision, "actual": clause.revision},
        )


def create_clause(session: Session, payload: StandardClauseCreate) -> StandardClause:
    try:
        clause = StandardClause(**payload.model_dump(), revision=1)
        session.add(clause)
        session.flush()
    except IntegrityError as exc:
        raise KGError(
            ErrorCode.ALREADY_EXISTS,
            {"standard": payload.standard, "clause_number": payload.clause_number},
        ) from exc
    return clause


def list_clauses(
    session: Session,
    q: str = "",
    page: int = 1,
    page_size: int = 50,
    sort: ClauseSort | None = None,
) -> tuple[list[StandardClause], int]:
    """条款索引。

    `sort` 为空时用索引默认序（标准号 → 条款号，均升序），与
    business_domain / ontology / mapping 等列表的「按业务键升序」约定一致；
    显式传入时按单一列的升降序排列，并以 `id` 兜底保证分页稳定。
    """
    stmt = select(StandardClause)
    if q:
        escaped = q.replace("/", "//").replace("%", "/%").replace("_", "/_")
        pattern = f"%{escaped}%"
        stmt = stmt.where(
            or_(
                StandardClause.standard.ilike(pattern, escape="/"),
                StandardClause.clause_number.ilike(pattern, escape="/"),
                StandardClause.product_fallback.ilike(pattern, escape="/"),
                StandardClause.title_i18n["zh-CN"]
                .as_string()
                .ilike(pattern, escape="/"),
                StandardClause.title_i18n["en-US"]
                .as_string()
                .ilike(pattern, escape="/"),
                StandardClause.self_authored_description["zh-CN"]
                .as_string()
                .ilike(pattern, escape="/"),
            )
        )
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    if sort is None:
        ordering: tuple[Any, ...] = (
            StandardClause.standard.asc(),
            StandardClause.clause_number.asc(),
        )
    else:
        column = {
            "standard": StandardClause.standard,
            "clause_number": StandardClause.clause_number,
            "id": StandardClause.id,
        }[sort.lstrip("-")]
        ordering = ((column.desc() if sort.startswith("-") else column.asc()),)
    items = list(
        session.scalars(
            stmt.order_by(*ordering, StandardClause.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
    )
    return items, total


def update_clause(
    session: Session,
    clause_id: int,
    payload: StandardClauseUpdate,
    revision: int,
) -> StandardClause:
    check_revision(get_clause(session, clause_id), revision)
    values = {k: v for k, v in payload.model_dump().items() if v is not None}
    clause = session.scalar(
        update(StandardClause)
        .where(StandardClause.id == clause_id, StandardClause.revision == revision)
        .values(**values, revision=StandardClause.revision + 1)
        .returning(StandardClause)
        .execution_options(populate_existing=True)
    )
    if clause is None:
        check_revision(get_clause(session, clause_id), revision)
        raise KGError(ErrorCode.REVISION_CONFLICT, {"clause_id": clause_id})
    return clause


def delete_clause(session: Session, clause_id: int, revision: int) -> None:
    check_revision(get_clause(session, clause_id), revision)
    deleted = session.scalar(
        delete(StandardClause)
        .where(StandardClause.id == clause_id, StandardClause.revision == revision)
        .returning(StandardClause.id)
    )
    if deleted is None:
        check_revision(get_clause(session, clause_id), revision)
        raise KGError(ErrorCode.REVISION_CONFLICT, {"clause_id": clause_id})
