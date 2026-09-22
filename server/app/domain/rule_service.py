"""规则库 CRUD、原子版本保护与正反例编排。"""

from __future__ import annotations

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.models.enums import ValidationState
from app.models.governance import Rule
from app.schemas.governance import (
    RuleCreate,
    RuleExampleOut,
    RuleSort,
    RuleSourceKind,
    RuleTestOut,
)
from app.semantics.rule_examples import inspect_examples, run_examples


def get_rule(session: Session, rule_id: int) -> Rule:
    rule = session.get(Rule, rule_id, populate_existing=True)
    if rule is None:
        raise KGError(ErrorCode.RESOURCE_NOT_FOUND, {"rule_id": rule_id})
    return rule


def check_revision(rule: Rule, revision: int) -> None:
    if rule.revision != revision:
        raise KGError(
            ErrorCode.REVISION_CONFLICT,
            {"rule_id": rule.id, "expected": revision, "actual": rule.revision},
        )


def list_rules(
    session: Session,
    *,
    page: int,
    page_size: int,
    q: str,
    source_kind: RuleSourceKind | None,
    sort: RuleSort,
) -> tuple[list[Rule], int]:
    statement = select(Rule)
    if q:
        escaped = q.replace("/", "//").replace("%", "/%").replace("_", "/_")
        pattern = f"%{escaped}%"
        statement = statement.where(
            or_(
                Rule.identifier.ilike(pattern, escape="/"),
                Rule.name_i18n["zh-CN"].as_string().ilike(pattern, escape="/"),
                Rule.name_i18n["en-US"].as_string().ilike(pattern, escape="/"),
                Rule.category.ilike(pattern, escape="/"),
                Rule.source_reference.ilike(pattern, escape="/"),
            )
        )
    if source_kind is not None:
        statement = statement.where(Rule.source_kind == source_kind)
    total = session.scalar(select(func.count()).select_from(statement.subquery())) or 0
    column = Rule.id if sort.lstrip("-") == "id" else Rule.identifier
    ordering = column.desc() if sort.startswith("-") else column.asc()
    items = session.scalars(
        statement.order_by(ordering, Rule.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return list(items), total


def _duplicate_identifier(identifier: str) -> KGError:
    return KGError(
        ErrorCode.ALREADY_PUBLISHED,
        {"identifier": identifier, "reason": "rule_identifier_taken"},
    )


def create_rule(session: Session, payload: RuleCreate) -> Rule:
    inspect_examples(payload)
    try:
        rule = Rule(**payload.model_dump(), revision=1)
        session.add(rule)
        session.flush()
    except IntegrityError as exc:
        raise _duplicate_identifier(payload.identifier) from exc
    return rule


def update_rule(
    session: Session, rule_id: int, payload: RuleCreate, revision: int
) -> Rule:
    check_revision(get_rule(session, rule_id), revision)
    inspect_examples(payload)
    try:
        rule = session.scalar(
            update(Rule)
            .where(Rule.id == rule_id, Rule.revision == revision)
            .values(**payload.model_dump(), revision=Rule.revision + 1)
            .returning(Rule)
            .execution_options(populate_existing=True)
        )
    except IntegrityError as exc:
        raise _duplicate_identifier(payload.identifier) from exc
    if rule is None:
        check_revision(get_rule(session, rule_id), revision)
        raise KGError(ErrorCode.REVISION_CONFLICT, {"rule_id": rule_id})
    return rule


def delete_rule(session: Session, rule_id: int, revision: int) -> None:
    check_revision(get_rule(session, rule_id), revision)
    deleted = session.scalar(
        delete(Rule)
        .where(Rule.id == rule_id, Rule.revision == revision)
        .returning(Rule.id)
    )
    if deleted is None:
        check_revision(get_rule(session, rule_id), revision)
        raise KGError(ErrorCode.REVISION_CONFLICT, {"rule_id": rule_id})


def test_rule(session: Session, rule_id: int, revision: int) -> RuleTestOut:
    rule = get_rule(session, rule_id)
    check_revision(rule, revision)
    if rule.language != "SHACL" or rule.execution != "AUTO":
        return RuleTestOut(
            rule_id=rule_id, revision=revision, state=ValidationState.NOT_RUN
        )
    payload = RuleCreate.model_validate(rule, from_attributes=True)
    positive_data, negative_data = run_examples(payload)
    # Re-read the saved revision after execution; stale results cannot endorse an edit.
    check_revision(get_rule(session, rule_id), revision)
    positive = RuleExampleOut.model_validate(positive_data)
    negative = RuleExampleOut.model_validate(negative_data)
    return RuleTestOut(
        rule_id=rule_id,
        revision=revision,
        state=ValidationState.PASS
        if positive.conforms and not negative.conforms
        else ValidationState.VIOLATION,
        positive=positive,
        negative=negative,
    )
