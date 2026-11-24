"""The single OWL rule endpoint needs an explicit, complete frozen target context."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from app.core.db import Base
from app.domain.iri_service import register_namespace
from app.domain.ontology_service import create_ontology, publish_ontology
from app.domain.rule_service import create_rule
from app.domain.rule_service import test_rule as run_rule_test
from app.domain.status_service import publish_resource
from app.domain.type_service import create_entity_type
from app.models.domain import OntologyRuleRef
from app.models.enums import ValidationState
from app.models.governance import Rule
from app.schemas.governance import RuleCreate
from app.schemas.ontology import OntologyCreate
from app.schemas.type import EntityTypeCreate
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

NS = "https://example.org/single#"


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def seed(session: Session, *, linked: bool = True, count: int = 1) -> Rule:
    namespace = register_namespace(session, "single", NS)
    resources = [
        create_entity_type(
            session,
            EntityTypeCreate(
                name=name, namespace_id=namespace.id, label_i18n={"zh-CN": name}
            ),
        )
        for name in ("Person", "Organization")
    ]
    for resource in resources:
        publish_resource(session, resource)
    rule = create_rule(
        session,
        RuleCreate(
            identifier="OWL-EXAMPLE",
            name_i18n={"zh-CN": "类型互斥"},
            category="integrity",
            source_kind="ENTERPRISE",
            source_reference="example-1",
            target_iri=NS + "Person",
            severity="VIOLATION",
            language="OWL",
            expression=f"<{NS}Person> "
            f"<http://www.w3.org/2002/07/owl#disjointWith> <{NS}Organization> .",
            execution="AUTO",
            positive_example=f"<{NS}alice> a <{NS}Person> .",
            negative_example=f"<{NS}alice> a <{NS}Person>, <{NS}Organization> .",
        ),
    )
    if linked:
        for index in range(count):
            ontology = create_ontology(
                session,
                OntologyCreate(
                    name=f"SingleRule{index}",
                    iri=f"https://example.org/single-ontology/{index}",
                    label_i18n={"zh-CN": "单规则本体"},
                    ref_resource_ids=[resource.id for resource in resources],
                ),
            )
            session.add(
                OntologyRuleRef(
                    ontology_id=ontology.id, rule_id=rule.id, pinned_revision=1
                )
            )
            session.flush()
            publish_ontology(session, ontology)
    return rule


def test_single_owl_examples_use_actual_engine_and_frozen_context(
    session: Session,
) -> None:
    rule = seed(session)
    result = run_rule_test(session, rule.id, 1)
    assert result.state is ValidationState.PASS
    assert result.positive is not None and result.positive.state is ValidationState.PASS
    assert (
        result.negative is not None
        and result.negative.state is ValidationState.VIOLATION
    )
    assert "owl_disjoint_class_conflict" in result.negative.report_text


@pytest.mark.parametrize(("linked", "count"), [(False, 1), (True, 2)])
def test_missing_or_ambiguous_context_cannot_pass(
    session: Session, linked: bool, count: int
) -> None:
    rule = seed(session, linked=linked, count=count)
    result = run_rule_test(session, rule.id, 1)
    assert result.state is ValidationState.NOT_RUN
    assert result.positive is None and result.negative is None


def test_mutated_example_body_does_not_match_frozen_rule(session: Session) -> None:
    rule = seed(session)
    rule.negative_example = rule.positive_example
    session.flush()
    assert run_rule_test(session, rule.id, 1).state is ValidationState.NOT_RUN
