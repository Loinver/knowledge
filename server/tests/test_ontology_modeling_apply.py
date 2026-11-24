"""Isolated apply integration: fixed plans, frozen dependencies and atomic receipts."""

from __future__ import annotations

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from threading import Barrier
from typing import Any
from uuid import uuid4

import pytest
from app.core.db import Base
from app.core.errors import KGError
from app.domain import ontology_modeling_apply as executor
from app.domain import ontology_modeling_service as service
from app.domain.ontology_modeling_context import digest, prepare_context
from app.domain.status_service import publish_resource
from app.models.account import User
from app.models.asset_audit import AssetAuditLog
from app.models.domain import (
    Ontology,
    OntologyResourceRef,
    OntologyRevision,
    OntologyRuleRef,
)
from app.models.enums import ResourceKind, ResourceStatus, UserRole
from app.models.governance import Rule
from app.models.ontology_modeling import (
    ModelingApplication,
    ModelingProposal,
    ModelingValidation,
)
from app.models.resource import (
    DatatypePropDetail,
    ModelResource,
    Namespace,
    ResourceParent,
    ResourceRef,
)
from app.schemas.governance import RuleCreate
from app.schemas.ontology_modeling import ModelingApply, ModelingCreate
from app.schemas.ontology_modeling_candidate import OntologyCandidate
from app.semantics.ontology_modeling import axiom_rules, constraint_rules
from app.semantics.ontology_modeling_examples import validate_modeling_examples
from app.semantics.ontology_rules import compile_ontology_rules
from app.semantics.rule_examples import run_examples
from rdflib import OWL, RDFS, XSD, Graph, URIRef
from rdflib.compare import isomorphic
from sqlalchemy import create_engine, event, select, update
from sqlalchemy.orm import Session, sessionmaker


@dataclass
class Harness:
    sessions: sessionmaker[Session]
    actor_id: str
    ontology_id: int
    namespace_id: int


@pytest.fixture()
def h(tmp_path: Path) -> Iterator[Harness]:
    engine = create_engine(
        f"sqlite:///{tmp_path}/apply.db",
        connect_args={"check_same_thread": False, "timeout": 15},
    )

    @event.listens_for(engine, "connect")
    def fk(connection: Any, _: Any) -> None:
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)
    with sessions.begin() as session:
        user = User(
            username="editor",
            email="editor@example.org",
            password_hash="unused",
            role=UserRole.EDITOR,
        )
        namespace = Namespace(prefix="modeling", iri="https://example.org/modeling#")
        onto = Ontology(
            name="WorkingOntology",
            iri="https://example.org/onto",
            label_i18n={"zh-CN": "工作本体"},
        )
        session.add_all((user, namespace, onto))
        session.flush()
        harness = Harness(sessions, user.id, onto.id, namespace.id)
    yield harness
    engine.dispose()


def _metadata(label: str) -> dict:
    return {
        "labels": {"zh-CN": label, "en-US": None},
        "definitions": {"zh-CN": "虚构测试定义", "en-US": None},
        "synonyms": [{"language": "zh-CN", "text": label + "别名"}],
    }


def _evidence() -> dict:
    return {
        "basis": "PROPOSAL",
        "source_refs": [],
        "rationale_i18n": {"zh-CN": "待审建议", "en-US": None},
        "depends_on": [],
        "uncertainty_ids": [],
    }


def _ref(cid: str) -> dict:
    return {"kind": "CANDIDATE", "candidate_id": cid}


def _candidate(
    h: Harness, *, datatype: str = "integer", relation: bool = False
) -> dict:
    resources = [
        {
            "candidate_id": "c:person",
            "spec": {
                "kind": "NEW_CLASS",
                "namespace_handle": f"ns:{h.namespace_id}",
                "local_name": "Person",
                "metadata": _metadata("人员"),
                "parents": [],
            },
            "evidence": _evidence(),
        },
        {
            "candidate_id": "c:value",
            "spec": {
                "kind": "NEW_DATA_PROPERTY",
                "namespace_handle": f"ns:{h.namespace_id}",
                "local_name": "value",
                "metadata": _metadata("测试值"),
                "owner": _ref("c:person"),
                "datatype": datatype,
            },
            "evidence": _evidence(),
        },
    ]
    if relation:
        resources.append(
            {
                "candidate_id": "c:device",
                "spec": {
                    "kind": "NEW_CLASS",
                    "namespace_handle": f"ns:{h.namespace_id}",
                    "local_name": "Device",
                    "metadata": _metadata("设备"),
                    "parents": [],
                },
                "evidence": _evidence(),
            }
        )
        for cid, reverse, inverse in (
            ("c:owns", False, "c:ownedBy"),
            ("c:ownedBy", True, "c:owns"),
        ):
            resources.append(
                {
                    "candidate_id": cid,
                    "spec": {
                        "kind": "NEW_OBJECT_PROPERTY",
                        "namespace_handle": f"ns:{h.namespace_id}",
                        "local_name": cid.split(":")[1],
                        "metadata": _metadata(cid),
                        "domain": {
                            "mode": "ONE",
                            "refs": [_ref("c:device" if reverse else "c:person")],
                        },
                        "range": {
                            "mode": "ONE",
                            "refs": [_ref("c:person" if reverse else "c:device")],
                        },
                        "inverse_of": _ref(inverse),
                        "features": dict.fromkeys(
                            (
                                "functional",
                                "inverse_functional",
                                "symmetric",
                                "transitive",
                                "asymmetric",
                                "reflexive",
                                "irreflexive",
                            ),
                            False,
                        ),
                    },
                    "evidence": _evidence(),
                }
            )
    return {
        "schema_version": "ontology-candidate/1.0",
        "context_token": "pending",
        "profile_echo": "BUSINESS",
        "scope": {
            "goal_i18n": {"zh-CN": "建模虚构人员", "en-US": None},
            "out_of_scope_i18n": [],
            "assumptions_i18n": [],
        },
        "ontology_metadata": {
            "metadata": _metadata("完善工作本体"),
            "evidence": _evidence(),
        },
        "resources": resources,
        "axioms": [],
        "constraints": [],
        "questions": [],
    }


def _prepare(
    h: Harness, candidate: dict | None = None, *, assets: list[int] | None = None
) -> tuple[str, ModelingApply]:
    with h.sessions.begin() as session:
        onto = session.get(Ontology, h.ontology_id)
        assert onto is not None
        context = prepare_context(
            session,
            ModelingCreate(
                target_ontology_id=h.ontology_id,
                target_draft_id=f"ontology:{h.ontology_id}:working",
                base_edit_revision=onto.edit_revision,
                text="构建虚构模型",
                namespace_ids=[h.namespace_id],
                asset_ids=assets or [],
                authorize_model_transfer=True,
            ),
        )
        data = deepcopy(candidate or _candidate(h))
        data["context_token"] = context["context_token"]
        proposal = service.save_generated(
            session,
            actor_id=h.actor_id,
            request_key=uuid4().hex,
            request_digest=digest(data),
            context=context,
            candidate=OntologyCandidate.model_validate(data),
            model_provenance={"model": "offline-fixture"},
        )
        revision = service.get_candidate_revision(session, proposal)
        report = service.validate_proposal(
            session, proposal, 1, revision.candidate_digest
        )
        assert report.can_apply, report.model_dump()
        payload = ModelingApply(
            target_draft_id=context["target_draft_id"],
            base_edit_revision=context["base_edit_revision"],
            validation_report_id=report.id,
            compiled_plan_digest=report.compiled_plan_digest,
            confirmation={"accepted_plan_digest": report.compiled_plan_digest},
        )
        return proposal.id, payload


def _apply(
    h: Harness, proposal_id: str, payload: ModelingApply, key: str = "apply-key"
) -> Any:
    with h.sessions.begin() as session:
        return executor.apply_proposal(
            session,
            proposal_id,
            payload,
            proposal_revision=1,
            actor_id=h.actor_id,
            idempotency_key=key,
        )


def _assert_unapplied(h: Harness, proposal_id: str, *, resource_count: int = 0) -> None:
    with h.sessions() as session:
        proposal = service.get_proposal(session, proposal_id, h.actor_id)
        onto = session.get(Ontology, h.ontology_id)
        assert proposal.state == "READY" and proposal.revision == 1
        assert onto is not None and onto.edit_revision == 0
        assert len(list(session.scalars(select(ModelResource)))) == resource_count
        for model in (
            ModelingApplication,
            AssetAuditLog,
            OntologyResourceRef,
            OntologyRuleRef,
            Rule,
        ):
            assert list(session.scalars(select(model))) == []


def test_basic_apply_allocates_formal_ids_metadata_and_inverse_links(
    h: Harness,
) -> None:
    proposal_id, payload = _prepare(h, _candidate(h, relation=True))
    commits: list[bool] = []
    with h.sessions() as session:
        event.listen(session, "after_commit", lambda _: commits.append(True))
        result = executor.apply_proposal(
            session,
            proposal_id,
            payload,
            proposal_revision=1,
            actor_id=h.actor_id,
            idempotency_key="basic",
        )
        assert commits == []
        assert result.state == "APPLIED_TO_DRAFT"
        assert result.after_edit_revision == 1 and result.before_edit_revision == 0
        assert set(result.candidate_to_resource) == {
            "c:person",
            "c:device",
            "c:value",
            "c:owns",
            "c:ownedBy",
        }
        session.commit()
    assert commits == [True]
    with h.sessions() as session:
        onto = session.get(Ontology, h.ontology_id)
        assert (
            onto is not None
            and onto.status == ResourceStatus.DRAFT
            and onto.current_revision == 0
        )
        assert onto.synonyms == _metadata("完善工作本体")["synonyms"]
        resources = list(session.scalars(select(ModelResource)))
        assert len(resources) == 5 and all(
            r.status == ResourceStatus.DRAFT and r.edit_revision == 1 for r in resources
        )
        for mapping in result.candidate_to_resource.values():
            resource = session.get(ModelResource, mapping.resource_id)
            assert resource is not None and resource.iri == mapping.iri
            assert resource.synonyms
            assert mapping.status == "DRAFT" and mapping.revision == 0
        assert len(list(session.scalars(select(OntologyResourceRef)))) == 5
        assert (
            len(
                list(
                    session.scalars(
                        select(ResourceRef).where(ResourceRef.role == "inverse_of")
                    )
                )
            )
            == 2
        )
        assert (
            session.get(
                DatatypePropDetail, result.candidate_to_resource["c:value"].resource_id
            ).datatype
            == "integer"
        )
        audit = session.scalar(select(AssetAuditLog))
        assert (
            audit is not None and audit.result == "OK" and audit.actor_id == h.actor_id
        )
        assert audit.action == "ASSEMBLE" and audit.object_type == "ONTOLOGY"
        assert audit.version_before == {"current_revision": 0, "edit_revision": 0}
        assert audit.version_after == {"current_revision": 0, "edit_revision": 1}
        assert audit.correlation_id == result.audit_correlation_id
        assert (
            service.get_candidate_revision(
                session, service.get_proposal(session, proposal_id, h.actor_id)
            ).revision
            == 1
        )


@pytest.mark.parametrize(
    "kind", ["CARDINALITY", "ENUM", "PATTERN", "NUMERIC_RANGE", "CLASS_MEMBERSHIP"]
)
def test_saved_constraints_match_validation_rules_and_real_examples(
    h: Harness, kind: str
) -> None:
    data = _candidate(
        h,
        datatype="string" if kind == "PATTERN" else "integer",
        relation=kind == "CLASS_MEMBERSHIP",
    )
    specs = {
        "CARDINALITY": {"min": 1, "max": 2},
        "ENUM": {
            "allowed": [
                {"datatype": "integer", "lexical": "1"},
                {"datatype": "integer", "lexical": "2"},
            ]
        },
        "PATTERN": {"regex": "^[A-Z]+$", "flags": ""},
        "NUMERIC_RANGE": {
            "minimum": "0",
            "maximum": "10",
            "minimum_inclusive": True,
            "maximum_inclusive": True,
        },
        "CLASS_MEMBERSHIP": {
            "allowed_class": {"mode": "ONE", "refs": [_ref("c:device")]}
        },
    }
    path = {
        "property": _ref("c:owns" if kind == "CLASS_MEMBERSHIP" else "c:value"),
        "inverse": False,
    }
    data["constraints"] = [
        {
            "candidate_id": "c:constraint",
            "target_class": _ref("c:person"),
            "spec": {"kind": kind, "path": path, **specs[kind]},
            "severity": "VIOLATION",
            "evidence": _evidence(),
        }
    ]
    proposal_id, payload = _prepare(h, data)
    _apply(h, proposal_id, payload)
    with h.sessions() as session:
        accepted = session.get(ModelingValidation, payload.validation_report_id)
        assert accepted is not None
        body = constraint_rules(accepted.report["plan"])[0]
        rule = session.scalar(select(Rule))
        assert rule is not None
        assert isomorphic(
            Graph().parse(data=body["expression"], format="turtle"),
            Graph().parse(data=rule.expression, format="turtle"),
        )
        assert rule.target_iri == body["target_iri"] and rule.language == "SHACL"
        yes, no = run_examples(RuleCreate.model_validate(rule, from_attributes=True))
        assert yes["conforms"] and not no["conforms"]
        ref = session.scalar(select(OntologyRuleRef))
        assert ref is not None and ref.rule_id == rule.id and ref.pinned_revision == 1


def test_reuse_implicit_parent_pins_entire_closure_without_editing_frozen_assets(
    h: Harness,
) -> None:
    with h.sessions.begin() as session:
        parent = ModelResource(
            kind=ResourceKind.ENTITY,
            name="Ancestor",
            iri="https://example.org/modeling#Ancestor",
            namespace_id=h.namespace_id,
            label_i18n={"zh-CN": "祖先"},
        )
        child = ModelResource(
            kind=ResourceKind.ENTITY,
            name="Existing",
            iri="https://example.org/modeling#Existing",
            namespace_id=h.namespace_id,
            label_i18n={"zh-CN": "既有类型"},
        )
        session.add_all((parent, child))
        session.flush()
        session.add(ResourceParent(child_id=child.id, parent_id=parent.id))
        publish_resource(session, parent)
        publish_resource(session, child)
        existing_id, ancestor_id = child.id, parent.id
        before = {
            r.id: (r.label_i18n, r.edit_revision, r.current_revision)
            for r in (child, parent)
        }
    data = _candidate(h)
    data["resources"][0]["spec"]["parents"] = [
        {"kind": "CATALOG", "handle": f"asset:{existing_id}:1"}
    ]
    proposal_id, payload = _prepare(h, data, assets=[existing_id])
    _apply(h, proposal_id, payload)
    with h.sessions() as session:
        refs = {
            r.resource_id: r.pinned_revision
            for r in session.scalars(select(OntologyResourceRef))
        }
        assert refs[existing_id] == refs[ancestor_id] == 1
        for rid, snapshot in before.items():
            resource = session.get(ModelResource, rid)
            assert (
                resource is not None
                and (
                    resource.label_i18n,
                    resource.edit_revision,
                    resource.current_revision,
                )
                == snapshot
            )


def test_idempotent_replay_returns_original_receipt_after_context_changes(
    h: Harness,
) -> None:
    proposal_id, payload = _prepare(h)
    first = _apply(h, proposal_id, payload)
    with h.sessions.begin() as session:
        session.execute(
            update(Ontology).where(Ontology.id == h.ontology_id).values(edit_revision=2)
        )
    replay = _apply(h, proposal_id, payload)
    assert replay == first
    with h.sessions() as session:
        assert len(list(session.scalars(select(ModelingApplication)))) == 1
        assert len(list(session.scalars(select(AssetAuditLog)))) == 1


@pytest.mark.parametrize(
    "change",
    ["key", "confirmation", "report", "digest", "target", "base", "revision", "owner"],
)
def test_mismatches_cannot_write_draft(h: Harness, change: str) -> None:
    proposal_id, payload = _prepare(h)
    kwargs = {"proposal_revision": 1, "actor_id": h.actor_id, "idempotency_key": "key"}
    if change == "key":
        kwargs["idempotency_key"] = ""
    elif change == "confirmation":
        payload.confirmation.accepted_plan_digest = "bad"
    elif change == "report":
        payload.validation_report_id = "missing"
    elif change == "digest":
        payload.compiled_plan_digest = "bad"
    elif change == "target":
        payload.target_draft_id = "wrong"
    elif change == "base":
        payload.base_edit_revision = 100
    elif change == "revision":
        kwargs["proposal_revision"] = 2
    else:
        kwargs["actor_id"] = "other-actor"
    with h.sessions() as session:
        with pytest.raises(KGError):
            executor.apply_proposal(session, proposal_id, payload, **kwargs)
        session.rollback()
    _assert_unapplied(h, proposal_id)


@pytest.mark.parametrize("failure", ["audit", "receipt"])
def test_failure_and_outer_rollback_leave_no_partial_asset_or_receipt(
    h: Harness, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    proposal_id, payload = _prepare(h)

    def fail(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("Injected failure")

    if failure == "audit":
        monkeypatch.setattr(executor, "record_asset_audit", fail)
    else:

        def before_flush(session: Session, *args: Any) -> None:
            if any(isinstance(row, ModelingApplication) for row in session.new):
                fail()

        event.listen(h.sessions, "before_flush", before_flush)
    try:
        with h.sessions() as session:
            with pytest.raises(RuntimeError):
                executor.apply_proposal(
                    session,
                    proposal_id,
                    payload,
                    proposal_revision=1,
                    actor_id=h.actor_id,
                    idempotency_key="fail",
                )
            session.rollback()
    finally:
        if failure == "receipt":
            event.remove(h.sessions, "before_flush", before_flush)
    _assert_unapplied(h, proposal_id)


def test_duplicate_concurrent_key_produces_one_apply_and_same_receipt(
    h: Harness,
) -> None:
    proposal_id, payload = _prepare(h)
    barrier = Barrier(2)

    def apply() -> Any:
        with h.sessions() as session:
            cached = session.get(ModelingProposal, proposal_id)
            assert cached is not None and cached.state == "READY"
            barrier.wait(timeout=15)
            result = executor.apply_proposal(
                session,
                proposal_id,
                payload,
                proposal_revision=1,
                actor_id=h.actor_id,
                idempotency_key="concurrent",
            )
            session.commit()
            return result

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: apply(), range(2)))
    assert results[0] == results[1]
    with h.sessions() as session:
        assert len(list(session.scalars(select(ModelingApplication)))) == 1
        assert len(list(session.scalars(select(AssetAuditLog)))) == 1
        assert len(list(session.scalars(select(ModelResource)))) == 2


@pytest.mark.parametrize(
    "kind", ["EQUIVALENT_CLASSES", "DISJOINT_CLASSES", "SUBPROPERTY"]
)
def test_persists_supported_axioms_with_real_compiler(h: Harness, kind: str) -> None:
    data = _candidate(h, relation=True)
    if kind == "SUBPROPERTY":
        other = deepcopy(data["resources"][-2])
        other["candidate_id"] = "c:relatedTo"
        other["spec"].update(
            local_name="relatedTo", metadata=_metadata("关联"), inverse_of=None
        )
        data["resources"].append(other)
        spec = {"kind": kind, "sub": _ref("c:owns"), "super": _ref("c:relatedTo")}
    else:
        spec = {"kind": kind, "classes": [_ref("c:person"), _ref("c:device")]}
    data["axioms"] = [
        {"candidate_id": "c:axiom", "spec": spec, "evidence": _evidence()}
    ]
    proposal_id, payload = _prepare(h, data)
    _apply(h, proposal_id, payload)
    with h.sessions() as session:
        validation = session.get(ModelingValidation, payload.validation_report_id)
        assert validation is not None
        plan = validation.report["plan"]
        body = axiom_rules(plan)[0]
        rule = session.scalar(select(Rule))
        assert rule is not None and rule.language == "OWL"
        assert rule.positive_example == rule.negative_example == ""
        assert isomorphic(
            Graph().parse(data=body["expression"], format="turtle"),
            Graph().parse(data=rule.expression, format="turtle"),
        )
        kinds = {
            resource.iri: resource.kind
            for resource in session.scalars(select(ModelResource))
        }
        compiled = compile_ontology_rules(
            [RuleCreate.model_validate(rule, from_attributes=True).model_dump()], kinds
        )
        axiom = plan["axioms"][0]
        if kind == "SUBPROPERTY":
            triple = (
                URIRef(axiom["sub_iri"]),
                RDFS.subPropertyOf,
                URIRef(axiom["super_iri"]),
            )
        else:
            predicate = (
                OWL.equivalentClass
                if kind == "EQUIVALENT_CLASSES"
                else OWL.disjointWith
            )
            triple = URIRef(axiom["iris"][0]), predicate, URIRef(axiom["iris"][1])
        assert triple in compiled.tbox
        assert session.scalar(select(OntologyRuleRef)) is not None


def test_axiom_catalog_reference_is_frozen_without_explicit_reuse(h: Harness) -> None:
    with h.sessions.begin() as session:
        resource = ModelResource(
            kind=ResourceKind.ENTITY,
            name="ExistingAxiomClass",
            iri="https://example.org/modeling#ExistingAxiomClass",
            namespace_id=h.namespace_id,
            label_i18n={"zh-CN": "既有公理类型"},
        )
        session.add(resource)
        session.flush()
        publish_resource(session, resource)
        rid = resource.id
    data = _candidate(h)
    data["axioms"] = [
        {
            "candidate_id": "c:eq",
            "spec": {
                "kind": "EQUIVALENT_CLASSES",
                "classes": [
                    _ref("c:person"),
                    {"kind": "CATALOG", "handle": f"asset:{rid}:1"},
                ],
            },
            "evidence": _evidence(),
        }
    ]
    proposal_id, payload = _prepare(h, data, assets=[rid])
    _apply(h, proposal_id, payload)
    with h.sessions() as session:
        pin = session.scalar(
            select(OntologyResourceRef.pinned_revision).where(
                OntologyResourceRef.resource_id == rid
            )
        )
        assert pin == 1


def test_unused_reuse_false_preserves_attachment_intent(h: Harness) -> None:
    with h.sessions.begin() as session:
        resource = ModelResource(
            kind=ResourceKind.ENTITY,
            name="Unused",
            iri="https://example.org/modeling#Unused",
            namespace_id=h.namespace_id,
            label_i18n={"zh-CN": "未使用资源"},
        )
        session.add(resource)
        session.flush()
        publish_resource(session, resource)
        rid = resource.id
    data = _candidate(h)
    data["resources"].append(
        {
            "candidate_id": "c:unused",
            "spec": {
                "kind": "REUSE",
                "handle": f"asset:{rid}:1",
                "expected_kind": "CLASS",
                "attach_to_ontology": False,
            },
            "evidence": _evidence(),
        }
    )
    proposal_id, payload = _prepare(h, data, assets=[rid])
    result = _apply(h, proposal_id, payload)
    assert result.candidate_to_resource["c:unused"].resource_id == rid
    with h.sessions() as session:
        assert (
            session.scalar(
                select(OntologyResourceRef).where(
                    OntologyResourceRef.resource_id == rid
                )
            )
            is None
        )


def test_working_ontology_history_is_unchanged(h: Harness) -> None:
    with h.sessions.begin() as session:
        onto = session.get(Ontology, h.ontology_id)
        assert onto is not None
        onto.status = ResourceStatus.PUBLISHED
        onto.current_revision = 1
        session.add(
            OntologyRevision(
                ontology_id=onto.id,
                revision=1,
                metadata_snapshot={"label_i18n": {"zh-CN": "历史标签"}},
                resource_versions={},
            )
        )
    proposal_id, payload = _prepare(h)
    result = _apply(h, proposal_id, payload)
    assert result.after_edit_revision == 1
    with h.sessions() as session:
        onto = session.get(Ontology, h.ontology_id)
        assert (
            onto is not None
            and onto.status == ResourceStatus.PUBLISHED
            and onto.current_revision == 1
        )
        historical = session.scalar(select(OntologyRevision))
        assert (
            historical is not None
            and historical.metadata_snapshot == {"label_i18n": {"zh-CN": "历史标签"}}
            and historical.resource_versions == {}
        )


@pytest.mark.parametrize(
    "failure",
    ["vacuous_cardinality", "regex_without_counterexample", "boolean_cardinality"],
)
def test_unsuitable_examples_never_report_pass(h: Harness, failure: str) -> None:
    from app.domain.ontology_modeling_plan import compile_candidate

    data = _candidate(
        h, datatype="boolean" if failure == "boolean_cardinality" else "string"
    )
    if failure == "regex_without_counterexample":
        spec = {"kind": "PATTERN", "regex": "^[\\s\\S]*$", "flags": "m"}
    else:
        spec = {
            "kind": "CARDINALITY",
            "min": 3 if failure == "boolean_cardinality" else 0,
            "max": None,
        }
    data["context_token"] = "fixed"
    data["constraints"] = [
        {
            "candidate_id": "c:required",
            "target_class": _ref("c:person"),
            "spec": {**spec, "path": {"property": _ref("c:value"), "inverse": False}},
            "severity": "VIOLATION",
            "evidence": _evidence(),
        }
    ]
    context = {
        "namespace_catalog": {
            f"ns:{h.namespace_id}": {
                "id": h.namespace_id,
                "iri": "https://example.org/modeling#",
                "protected": False,
            }
        },
        "asset_catalog": {},
        "source_catalog": {},
    }
    plan = compile_candidate(
        OntologyCandidate.model_validate(data), context_token="fixed", **context
    )
    assert plan["state"] == "COMPILED"
    checked = validate_modeling_examples(plan, context)
    assert checked["required"] is True and checked["state"] in {"NOT_RUN", "VIOLATION"}


@pytest.mark.parametrize("kind", ["DATA_PROPERTY", "OBJECT_PROPERTY"])
def test_reused_property_examples_use_frozen_catalog_kind(
    h: Harness, kind: str
) -> None:
    from app.domain.ontology_modeling_plan import compile_candidate

    data = _candidate(h)
    base_iri = "https://example.org/modeling#ExistingBase"
    prop_iri = "https://example.org/modeling#existingProperty"
    data["context_token"] = "fixed"
    data["resources"][0]["spec"]["parents"] = [
        {"kind": "CATALOG", "handle": "asset:base"}
    ]
    data["resources"].append(
        {
            "candidate_id": "c:reuseProperty",
            "spec": {
                "kind": "REUSE",
                "handle": "asset:property",
                "expected_kind": kind,
                "attach_to_ontology": False,
            },
            "evidence": _evidence(),
        }
    )
    data["constraints"] = [
        {
            "candidate_id": "c:count",
            "target_class": _ref("c:person"),
            "spec": {
                "kind": "CARDINALITY",
                "path": {
                    "property": _ref("c:reuseProperty"),
                    "inverse": kind == "OBJECT_PROPERTY",
                },
                "min": 1,
                "max": 1,
            },
            "severity": "VIOLATION",
            "evidence": _evidence(),
        }
    ]
    context = {
        "namespace_catalog": {
            f"ns:{h.namespace_id}": {
                "id": h.namespace_id,
                "iri": "https://example.org/modeling#",
                "protected": False,
            }
        },
        "asset_catalog": {
            "asset:base": {
                "id": 100,
                "revision": 1,
                "kind": "CLASS",
                "iri": base_iri,
                "name": "ExistingBase",
            },
            "asset:property": {
                "id": 101,
                "revision": 1,
                "kind": kind,
                "iri": prop_iri,
                "name": "existingProperty",
                "owner_iri": base_iri,
                "datatype": "integer",
                "domain_iri": base_iri,
                "range_iri": base_iri,
            },
        },
        "source_catalog": {},
    }
    plan = compile_candidate(
        OntologyCandidate.model_validate(data), context_token="fixed", **context
    )
    assert plan["state"] == "COMPILED", plan["issues"]
    checked = validate_modeling_examples(plan, context)
    assert checked["state"] == "PASS", checked
    positive = checked["params"]["examples"]["c:count"]["positive_example"]
    if kind == "DATA_PROPERTY":
        assert "XMLSchema#integer" in positive
    else:
        assert "<urn:modeling:example:value:0>" in positive and "^^" not in positive


@pytest.mark.parametrize(
    "kind", ["date_cardinality_min", "date_cardinality_max", "date_enum"]
)
def test_date_constraints_persist_valid_distinct_examples(
    h: Harness, kind: str
) -> None:
    data = _candidate(h, datatype="date")
    if kind == "date_enum":
        spec = {
            "kind": "ENUM",
            "allowed": [
                {"datatype": "date", "lexical": "2000-01-01"},
                {"datatype": "date", "lexical": "2000-01-02"},
            ],
        }
        counts = (1, 1)
    else:
        maximum_only = kind == "date_cardinality_max"
        spec = {
            "kind": "CARDINALITY",
            "min": 0 if maximum_only else 3,
            "max": 2 if maximum_only else 3,
        }
        counts = (0, 3) if maximum_only else (3, 0)
    data["constraints"] = [
        {
            "candidate_id": "c:dateConstraint",
            "target_class": _ref("c:person"),
            "spec": {**spec, "path": {"property": _ref("c:value"), "inverse": False}},
            "severity": "VIOLATION",
            "evidence": _evidence(),
        }
    ]
    proposal_id, payload = _prepare(h, data)
    _apply(h, proposal_id, payload)
    with h.sessions() as session:
        rule = session.scalar(select(Rule))
        assert rule is not None
        predicate = URIRef("https://example.org/modeling#Person/value")
        dates: list[set[date]] = []
        for text, count in zip(
            (rule.positive_example, rule.negative_example), counts, strict=True
        ):
            graph = Graph().parse(data=text, format="turtle")
            values = list(graph.objects(None, predicate))
            assert len(values) == count
            assert all(
                value.datatype == XSD.date and isinstance(value.toPython(), date)
                for value in values
            )
            dates.append({value.toPython() for value in values})
            assert len(dates[-1]) == count
        if kind == "date_enum":
            assert dates == [{date(2000, 1, 1)}, {date(2000, 1, 3)}]
        yes, no = run_examples(RuleCreate.model_validate(rule, from_attributes=True))
        assert yes["conforms"] and not no["conforms"]


def _compile_example_candidate(h: Harness, data: dict) -> tuple[dict, dict]:
    from app.domain.ontology_modeling_plan import compile_candidate

    data["context_token"] = "fixed"
    context = {
        "namespace_catalog": {
            f"ns:{h.namespace_id}": {
                "id": h.namespace_id,
                "iri": "https://example.org/modeling#",
                "protected": False,
            }
        },
        "asset_catalog": {},
        "source_catalog": {},
    }
    return compile_candidate(
        OntologyCandidate.model_validate(data), context_token="fixed", **context
    ), context


@pytest.mark.parametrize(
    "low,high,low_inclusive,high_inclusive,expected",
    [
        (None, "1", True, False, 0),
        (None, "-1.5", True, False, -2),
        ("1", None, False, True, 2),
        ("-1.5", None, False, True, -1),
        ("1", "2", True, False, 1),
        ("0", "1", False, True, 1),
        ("-2", "-1", True, False, -2),
        ("1.1", "2.1", False, False, 2),
        ("1.1", "1.9", True, True, None),
        ("-1.9", "-1.1", True, True, None),
        ("5", "5", True, True, 5),
        (
            "1000000000000000000000000000000",
            None,
            False,
            True,
            1000000000000000000000000000001,
        ),
        (
            None,
            "1000000000000000000000000000000",
            True,
            True,
            1000000000000000000000000000000,
        ),
    ],
)
def test_integer_range_examples_respect_exact_open_bounds(
    h: Harness,
    low: str | None,
    high: str | None,
    low_inclusive: bool,
    high_inclusive: bool,
    expected: int | None,
) -> None:
    data = _candidate(h)
    data["constraints"] = [
        {
            "candidate_id": "c:range",
            "target_class": _ref("c:person"),
            "spec": {
                "kind": "NUMERIC_RANGE",
                "path": {"property": _ref("c:value"), "inverse": False},
                "minimum": low,
                "maximum": high,
                "minimum_inclusive": low_inclusive,
                "maximum_inclusive": high_inclusive,
            },
            "severity": "VIOLATION",
            "evidence": _evidence(),
        }
    ]
    plan, context = _compile_example_candidate(h, data)
    if expected is None:
        assert plan["state"] == "BLOCKED" and plan["constraints"] == []
        assert any(
            issue["code"] == "KG.CANDIDATE_NUMERIC_RANGE_CONFLICT"
            for issue in plan["issues"]
        )
        assert validate_modeling_examples(plan, context)["state"] == "NOT_RUN"
        return
    assert plan["state"] == "COMPILED", plan["issues"]
    checked = validate_modeling_examples(plan, context)
    assert checked["required"] and checked["state"] == "PASS", checked
    examples = checked["params"]["examples"]["c:range"]
    predicate = URIRef("https://example.org/modeling#Person/value")
    positive = list(
        Graph()
        .parse(data=examples["positive_example"], format="turtle")
        .objects(None, predicate)
    )
    negative = list(
        Graph()
        .parse(data=examples["negative_example"], format="turtle")
        .objects(None, predicate)
    )
    assert [value.toPython() for value in positive] == (
        [] if expected is None else [expected]
    )
    assert len(negative) == 1
    assert all(
        value.datatype == XSD.integer and type(value.toPython()) is int
        for value in [*positive, *negative]
    )


def test_date_order_remains_unsupported_and_empty_numeric_range_remains_blocked(
    h: Harness,
) -> None:
    data = _candidate(h, datatype="date")
    second = deepcopy(data["resources"][1])
    second["candidate_id"] = "c:later"
    second["spec"].update(local_name="later", metadata=_metadata("结束日期"))
    data["resources"].append(second)
    data["constraints"] = [
        {
            "candidate_id": "c:order",
            "target_class": _ref("c:person"),
            "spec": {
                "kind": "DATE_ORDER",
                "earlier": {"property": _ref("c:value"), "inverse": False},
                "later": {"property": _ref("c:later"), "inverse": False},
                "allow_equal": False,
            },
            "severity": "VIOLATION",
            "evidence": _evidence(),
        }
    ]
    plan, context = _compile_example_candidate(h, data)
    assert plan["state"] == "BLOCKED" and plan["constraints"] == []
    assert validate_modeling_examples(plan, context)["state"] == "NOT_RUN"
    data = _candidate(h)
    data["constraints"] = [
        {
            "candidate_id": "c:empty",
            "target_class": _ref("c:person"),
            "spec": {
                "kind": "NUMERIC_RANGE",
                "path": {"property": _ref("c:value"), "inverse": False},
                "minimum": None,
                "maximum": None,
                "minimum_inclusive": True,
                "maximum_inclusive": True,
            },
            "severity": "VIOLATION",
            "evidence": _evidence(),
        }
    ]
    plan, context = _compile_example_candidate(h, data)
    assert plan["state"] == "BLOCKED" and plan["constraints"] == []
    assert validate_modeling_examples(plan, context)["state"] == "NOT_RUN"
