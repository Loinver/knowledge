"""规则库 CRUD、原子版本保护与正反例编排。"""

from __future__ import annotations

import json

from pydantic import ValidationError
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.domain.status_service import get_revision
from app.models.domain import Ontology, OntologyRevision, OntologyRuleRef
from app.models.enums import ValidationState
from app.models.governance import Rule
from app.schemas.governance import (
    RuleCreate,
    RuleExampleOut,
    RuleSort,
    RuleSourceKind,
    RuleTestOut,
)
from app.semantics.ontology_rdf import OntologyRdfMetadata, OntologyRdfResource
from app.semantics.ontology_rule_validation import validate_ontology_auto_rules
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
        ErrorCode.ALREADY_EXISTS,
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
    # 被本体引用的规则不允许删：否则本体-规则链接悬挂，
    # 本体发布/导出会带着指向已删规则的死引用。
    referenced = session.scalar(
        select(func.count())
        .select_from(OntologyRuleRef)
        .where(OntologyRuleRef.rule_id == rule_id)
    )
    if referenced:
        raise KGError(
            ErrorCode.RESOURCE_IN_USE,
            {"rule_id": rule_id, "count": referenced, "reason": "rule_in_use"},
        )
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
    if rule.execution != "AUTO":
        return RuleTestOut(
            rule_id=rule_id, revision=revision, state=ValidationState.NOT_RUN
        )
    if rule.language == "OWL":
        return _test_owl_rule(session, rule, revision)
    if rule.language != "SHACL":
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


def _test_owl_rule(session: Session, rule: Rule, revision: int) -> RuleTestOut:
    """Test only with one explicit current published ontology's frozen closure.

    No context parameter exists on this endpoint. Missing/ambiguous contexts,
    unsupported rules and absent example targets therefore remain NOT_RUN.
    """
    not_run = RuleTestOut(
        rule_id=rule.id, revision=revision, state=ValidationState.NOT_RUN
    )
    payload = RuleCreate.model_validate(rule, from_attributes=True)
    current = {**payload.model_dump(mode="json"), "id": rule.id, "revision": revision}
    contexts = []
    for frozen in session.scalars(
        select(OntologyRevision)
        .join(
            Ontology,
            (Ontology.id == OntologyRevision.ontology_id)
            & (Ontology.current_revision == OntologyRevision.revision),
        )
        .join(OntologyRuleRef, OntologyRuleRef.ontology_id == Ontology.id)
        .where(OntologyRuleRef.rule_id == rule.id)
    ):
        if not isinstance(frozen.rules, list):
            continue
        if any(
            isinstance(record, dict)
            and type(record.get("rule_id")) is int
            and type(record.get("revision")) is int
            and record["rule_id"] == rule.id
            and record["revision"] == revision
            and record.get("snapshot") == current
            for record in frozen.rules
        ):
            contexts.append(frozen)
    if len(contexts) != 1:
        return not_run
    frozen = contexts[0]
    try:
        snapshots = {}
        for key, pin in frozen.resource_versions.items():
            if (
                not isinstance(key, str)
                or not key.isdecimal()
                or int(key) < 1
                or type(pin) is not int
                or pin < 1
            ):
                return not_run
            snapshots[int(key)] = OntologyRdfResource.model_validate(
                get_revision(session, int(key), pin).payload
            )
        metadata = OntologyRdfMetadata.model_validate(frozen.metadata_snapshot)
    except (KGError, ValidationError, TypeError, ValueError, AttributeError):
        return not_run
    examples = [
        validate_ontology_auto_rules(
            metadata=metadata,
            snapshots=snapshots,
            rules=[current],
            instance_graph=text,
            revision=frozen.revision,
        )[0]
        for text in (payload.positive_example, payload.negative_example)
    ]
    check_revision(get_rule(session, rule.id), revision)
    if any(
        result.state not in {ValidationState.PASS, ValidationState.VIOLATION}
        for result in examples
    ):
        return not_run
    positive, negative = [
        RuleExampleOut(
            state=result.state,
            conforms=result.state == ValidationState.PASS,
            report_text=json.dumps(result.model_dump(mode="json"), sort_keys=True)[
                :16000
            ],
        )
        for result in examples
    ]
    return RuleTestOut(
        rule_id=rule.id,
        revision=revision,
        state=ValidationState.PASS
        if positive.conforms and not negative.conforms
        else ValidationState.VIOLATION,
        positive=positive,
        negative=negative,
    )
