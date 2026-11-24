"""G02：真实临时候选图执行冻结 AUTO SHACL/OWL，保留失败与冻结语义。"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from app.core.db import Base
from app.domain.derivation_service import run_derivation_stage
from app.domain.extraction_rule_stage import run_rule_stage
from app.domain.ontology_service import publish_ontology
from app.models.data_access import Datasource, MappingRevision
from app.models.domain import OntologyRevision, OntologyRuleRef
from app.models.enums import ValidationState
from app.models.extraction import DerivedEdge, ExtractionRun, FactEvidence, Quarantine
from app.models.governance import Rule
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from test_instance_ontology_constraints import NS, Scenario, _edge, _entity, _seed


@pytest.fixture()
def session(tmp_path: Path) -> Iterator[Session]:
    engine = create_engine(f"sqlite:///{tmp_path}/semantic-stage.db")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            yield db
    finally:
        engine.dispose()


def _rule(
    session: Session, scenario: Scenario, language: str, *, execution: str = "AUTO"
) -> tuple[Rule, MappingRevision]:
    target = scenario.parent.iri
    expression = ""
    if language == "SHACL":
        expression = (
            "@prefix sh: <http://www.w3.org/ns/shacl#> . "
            f"[] a sh:NodeShape; sh:targetClass <{target}>; "
            f"sh:property [ sh:path <{target}/code>; sh:minLength 3 ] ."
        )
    elif language == "OWL":
        expression = (
            f"<{target}> <http://www.w3.org/2002/07/owl#disjointWith> "
            f"<{scenario.range_parent.iri}> ."
        )
    elif language == "DERIVATION":
        expression = '{"op":"symmetric","edge":"Rel","derive_edge":"ReverseRel"}'
    positive = f'<{NS}example> a <{target}>; <{target}/code> "VALID" .'
    negative = f'<{NS}example> a <{target}>; <{target}/code> "X" .'
    rule = Rule(
        identifier=f"AUTO-{language}",
        name_i18n={"zh-CN": "冻结规则", "en-US": "Frozen rule"},
        category="test",
        source_kind="ENTERPRISE",
        source_reference="self-authored",
        target_iri=target,
        severity="VIOLATION",
        language=language,
        expression=expression,
        execution=execution,
        positive_example=positive,
        negative_example=negative,
        revision=1,
    )
    session.add(rule)
    session.flush()
    session.add(
        OntologyRuleRef(
            ontology_id=scenario.ontology.id, rule_id=rule.id, pinned_revision=1
        )
    )
    revision = publish_ontology(session, scenario.ontology)
    run = session.get(ExtractionRun, scenario.graph.run_id)
    assert run is not None
    mapping = session.get(MappingRevision, run.mapping_revision_id)
    assert mapping is not None
    mapping.onto_version = revision
    session.flush()
    return rule, mapping


def _run(session: Session, scenario: Scenario, mapping: MappingRevision) -> dict:
    run = session.get(ExtractionRun, scenario.graph.run_id)
    assert run is not None
    return run_rule_stage(session, run, scenario.graph, mapping)


@pytest.mark.parametrize("language", ["SHACL", "OWL"])
@pytest.mark.parametrize("valid", [True, False])
def test_auto_semantic_rules_execute_nonempty_candidate_graph(
    session: Session, language: str, valid: bool
) -> None:
    scenario = _seed(session)
    _, mapping = _rule(session, scenario, language)
    subject = _entity(
        session, scenario, "s", scenario.grandchild, {"code": "VALID" if valid else "X"}
    )
    if language == "OWL":
        object_ = (
            _entity(session, scenario, "o", scenario.range_child, {})
            if valid
            else subject
        )
        _edge(session, scenario, subject, object_)
    result = _run(session, scenario, mapping)
    rule_result = result["rule_results"][0]
    assert rule_result["state"] == ("PASS" if valid else "VIOLATION")
    assert (
        result["rule_violation_count"] == 0
        if valid
        else result["rule_violation_count"] > 0
    )
    if language == "SHACL" and not valid:
        assert rule_result["hits"] > 0


@pytest.mark.parametrize("language", ["SHACL", "OWL"])
@pytest.mark.parametrize("change", ["revision", "manual", "delete"])
def test_frozen_semantic_rules_survive_live_edits_and_deletion(
    session: Session, language: str, change: str
) -> None:
    scenario = _seed(session)
    rule, mapping = _rule(session, scenario, language)
    subject = _entity(session, scenario, "s", scenario.grandchild, {"code": "X"})
    if language == "OWL":
        _edge(session, scenario, subject, subject)
    before = _run(session, scenario, mapping)
    if change == "delete":
        ref = session.scalar(
            select(OntologyRuleRef).where(OntologyRuleRef.rule_id == rule.id)
        )
        assert ref is not None
        session.delete(ref)
        session.delete(rule)
    else:
        rule.revision = 2
        rule.execution = "MANUAL" if change == "manual" else "AUTO"
        rule.expression = "invalid live body"
    session.flush()
    after = _run(session, scenario, mapping)
    assert before["rule_results"][0]["state"] == after["rule_results"][0]["state"]
    assert before["rule_results"][0]["hits"] == after["rule_results"][0]["hits"]
    assert after["rule_results"][0]["state"] == "VIOLATION"
    assert after["rule_violation_count"] > 0


@pytest.mark.parametrize("language", ["SHACL", "OWL"])
@pytest.mark.parametrize(
    "damage", ["missing", "revision", "source", "body", "bool_pin"]
)
def test_missing_or_tampered_frozen_rules_are_not_run(
    session: Session, language: str, damage: str
) -> None:
    scenario = _seed(session)
    _, mapping = _rule(session, scenario, language)
    _entity(session, scenario, "s", scenario.grandchild, {"code": "X"})
    frozen = session.scalar(
        select(OntologyRevision).where(
            OntologyRevision.ontology_id == scenario.ontology.id,
            OntologyRevision.revision == mapping.onto_version,
        )
    )
    assert frozen is not None
    record = {**frozen.rules[0], "snapshot": dict(frozen.rules[0]["snapshot"])}
    if damage == "missing":
        record.pop("snapshot")
    elif damage == "revision":
        record["snapshot"]["revision"] = 2
    elif damage == "source":
        record["source_reference"] = "altered source"
    elif damage == "bool_pin":
        record["revision"] = True
    else:
        record["snapshot"]["expression"] = "not a supported rule"
    frozen.rules = [record]
    session.flush()
    result = _run(session, scenario, mapping)
    assert result["rule_results"][0]["state"] == "NOT_RUN"
    assert result["rule_results"][0]["reason"]
    assert result["rule_violation_count"] == 0


@pytest.mark.parametrize("language", ["SHACL", "OWL"])
def test_valid_rule_without_target_is_na_not_pass(
    session: Session, language: str
) -> None:
    scenario = _seed(session)
    _, mapping = _rule(session, scenario, language)
    _entity(session, scenario, "non-target", scenario.range_child, {})
    result = _run(session, scenario, mapping)
    assert result["rule_results"][0]["state"] == "NA"
    assert result["rule_violation_count"] == 0


def test_derivation_reads_frozen_auto_body_after_live_revision_and_mode_change(
    session: Session,
) -> None:
    scenario = _seed(session)
    rule, mapping = _rule(session, scenario, "DERIVATION")
    subject = _entity(session, scenario, "s", scenario.child)
    object_ = _entity(session, scenario, "o", scenario.range_child, {})
    _edge(session, scenario, subject, object_)
    rule.revision, rule.execution, rule.expression = 2, "MANUAL", "invalid live body"
    session.flush()
    run = session.get(ExtractionRun, scenario.graph.run_id)
    assert run is not None
    assert _run(session, scenario, mapping)["rule_results"] == []
    assert run_derivation_stage(session, run, scenario.graph, mapping) == 1
    derived = session.scalar(select(DerivedEdge))
    assert derived is not None
    assert (derived.subject, derived.predicate, derived.object_) == (
        object_,
        "ReverseRel",
        subject,
    )
    assert derived.source_fact_ids


def test_shacl_violation_quarantines_the_real_source_row(session: Session) -> None:
    scenario = _seed(session)
    _, mapping = _rule(session, scenario, "SHACL")
    subject = _entity(session, scenario, "s", scenario.grandchild, {"code": "X"})
    source = Datasource(name="evidence", kind="sqlite", params={})
    session.add(source)
    session.flush()
    session.add(
        FactEvidence(
            graph_revision_id=scenario.graph.id,
            subject=subject,
            predicate="_entity_attrs",
            object_=subject,
            source_id=source.id,
            table_name="synthetic_rows",
            row_key="row-1",
            columns=["code"],
            run_id=scenario.graph.run_id,
            evidence_type="ENTITY",
        )
    )
    session.flush()
    result = _run(session, scenario, mapping)
    assert result["quarantined_by_rule"] == 1
    quarantine = session.scalar(select(Quarantine))
    assert quarantine is not None
    assert (quarantine.table_name, quarantine.row_key, quarantine.rule_id) == (
        "synthetic_rows",
        "row-1",
        "AUTO-SHACL",
    )


def test_unattributed_engine_violation_still_counts_as_violation(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.semantics.ontology_rule_validation import OntologyRuleValidationResult

    scenario = _seed(session)
    rule, mapping = _rule(session, scenario, "OWL")
    _entity(session, scenario, "s", scenario.grandchild)

    def unattributed(**kwargs: object) -> list[OntologyRuleValidationResult]:
        return [
            OntologyRuleValidationResult(
                rule_id=rule.id,
                identifier=rule.identifier,
                revision=1,
                language="OWL",
                state=ValidationState.VIOLATION,
                hits=[],
                reason="owl_conflict_without_isolated_focus",
            )
        ]

    monkeypatch.setattr(
        "app.semantics.ontology_rule_validation.validate_ontology_auto_rules",
        unattributed,
    )
    result = _run(session, scenario, mapping)
    assert result["rule_results"][0]["state"] == "VIOLATION"
    assert result["rule_results"][0]["hits"] == 0
    assert result["rule_violation_count"] == 1
    assert result["quarantined_by_rule"] == 0


def test_engine_truncation_annotation_is_retained(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.semantics.ontology_rule_validation import OntologyRuleValidationResult

    scenario = _seed(session)
    rule, mapping = _rule(session, scenario, "SHACL")
    focus = _entity(session, scenario, "s", scenario.child, {"code": "X"})

    def limited(**kwargs: object) -> list[OntologyRuleValidationResult]:
        return [
            OntologyRuleValidationResult(
                rule_id=rule.id,
                identifier=rule.identifier,
                revision=1,
                language="SHACL",
                state=ValidationState.VIOLATION,
                hits=[{"focus": focus, "detail": {}, "triple_ids": []}],
                detail={"hits_truncated": True},
            )
        ]

    monkeypatch.setattr(
        "app.semantics.ontology_rule_validation.validate_ontology_auto_rules", limited
    )
    result = _run(session, scenario, mapping)
    assert result["rule_results"][0]["truncated"] is True
