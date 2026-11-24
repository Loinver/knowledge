"""Apply fixed modeling plans to working drafts in the caller's transaction.

No commits, publication, model calls or edits to reused assets. The caller must
roll back on any exception, including failures during receipt/audit persistence.
"""

from __future__ import annotations

import hashlib
from copy import deepcopy
from typing import Any
from uuid import uuid4

from sqlalchemy import false, func, select, update
from sqlalchemy.orm import Session

from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.domain.asset_audit_service import record_asset_audit
from app.domain.ontology_modeling_context import assert_context_current, digest
from app.domain.ontology_service import lock_ontology_edit
from app.domain.status_service import get_revision
from app.domain.template_service import lock_template
from app.models.asset_audit import AssetAuditAction, AssetType
from app.models.domain import Ontology, OntologyResourceRef, OntologyRuleRef
from app.models.enums import AuditResult, ResourceKind, ResourceStatus, ValidationState
from app.models.governance import Rule
from app.models.ontology_modeling import (
    ModelingApplication,
    ModelingProposal,
    ModelingProposalState,
    ModelingValidation,
)
from app.models.resource import (
    DatatypePropDetail,
    ModelResource,
    Namespace,
    ObjectPropDetail,
    ResourceParent,
    ResourceRef,
)
from app.schemas.governance import RuleCreate
from app.schemas.ontology_modeling import (
    ModelingApply,
    ModelingApplyOut,
    ModelingResourceMapping,
    ModelingValidationOut,
)
from app.schemas.ontology_modeling_candidate import OntologyCandidate
from app.semantics.ontology_modeling import axiom_rules, constraint_rules

_KINDS = {
    "CLASS": ResourceKind.ENTITY,
    "DATA_PROPERTY": ResourceKind.DATATYPE_PROP,
    "OBJECT_PROPERTY": ResourceKind.OBJECT_PROP,
}
_NEW_KINDS = {
    "NEW_CLASS": ResourceKind.ENTITY,
    "NEW_DATA_PROPERTY": ResourceKind.DATATYPE_PROP,
    "NEW_OBJECT_PROPERTY": ResourceKind.OBJECT_PROP,
}


def _reject(code: ErrorCode, reason: str, **params: Any) -> KGError:
    return KGError(code, {"reason": reason, **params})


def _write_fence(session: Session, actor_id: str, key: str) -> None:
    """Serialize key lookup before reads; reject old PostgreSQL snapshots."""
    with session.no_autoflush:
        connection = session.connection()
        if connection.dialect.name == "sqlite":
            connection.execute(update(Ontology).where(false()).values(id=Ontology.id))
        elif connection.dialect.name == "postgresql":
            if connection.get_isolation_level() != "READ COMMITTED":
                raise _reject(
                    ErrorCode.INVALID_REQUEST, "apply_requires_read_committed"
                )
            # Actor/key scope matches the receipt's unique constraint, across proposals.
            lock_id = int.from_bytes(
                hashlib.sha256(digest([actor_id, key]).encode()).digest()[:8],
                signed=True,
            )
            connection.execute(select(func.pg_advisory_xact_lock(lock_id)))
        else:
            raise _reject(ErrorCode.INVALID_REQUEST, "unsupported_apply_database")


def _report_current(
    report: ModelingValidationOut,
    proposal: ModelingProposal,
    candidate_digest: str,
    plan: dict[str, Any],
) -> None:
    if (
        report.proposal_id != proposal.id
        or report.proposal_revision != proposal.revision
        or report.candidate_digest != candidate_digest
        or report.context_fingerprint != proposal.context["fingerprint"]
        or report.compiled_plan_digest != plan["digest"]
        or report.compiler_version != plan["compiler_version"]
        or report.plan != plan
    ):
        raise _reject(ErrorCode.ONTOLOGY_VALIDATION_STALE, "report_plan_changed")
    if plan.get("state") != "COMPILED" or any(
        issue.get("blocking", True) for issue in plan.get("issues", [])
    ):
        raise _reject(ErrorCode.ONTOLOGY_CONSTRUCT_UNSUPPORTED, "plan_blocked")
    if (
        not report.can_apply
        or not report.checks
        or report.blocking_questions
        or any(
            check.required
            and check.state not in {ValidationState.PASS, ValidationState.NA}
            for check in report.checks
        )
    ):
        raise _reject(
            ErrorCode.ONTOLOGY_CHECKS_INCOMPLETE, "required_checks_incomplete"
        )
    if plan["constraints"] and not any(
        check.check_code == "M06"
        and check.required
        and check.state == ValidationState.PASS
        for check in report.checks
    ):
        raise _reject(
            ErrorCode.ONTOLOGY_CHECKS_INCOMPLETE, "constraint_examples_required"
        )


def _pin_closure(
    session: Session, catalog: dict, requested: set[str]
) -> tuple[dict[str, ModelResource], dict[int, int]]:
    """Freeze dependencies solely from authorized catalog/owned-version snapshots."""
    records = {record["iri"]: record for record in catalog.values()}
    pins: dict[int, int] = {}
    resources: dict[str, ModelResource] = {}
    pending = [records[iri] for iri in sorted(requested)]
    while pending:
        record = pending.pop(0)
        rid, pin = record["id"], record["revision"]
        if rid in pins:
            if pins[rid] != pin:
                raise _reject(
                    ErrorCode.REVISION_CONFLICT, "reuse_pin_conflict", resource_id=rid
                )
            continue
        resource = session.get(ModelResource, rid, populate_existing=True)
        frozen = get_revision(session, rid, pin)
        payload = frozen.payload
        if (
            resource is None
            or payload.get("iri") != record["iri"]
            or payload.get("name") != record["name"]
            or payload.get("kind")
            not in {kind.value for kind in _KINDS.values()} | {"ASSOC"}
            or (
                record.get("checksum") is not None
                and frozen.checksum != record["checksum"]
            )
        ):
            raise _reject(ErrorCode.ONTOLOGY_PROPOSAL_STALE, "reuse_snapshot_changed")
        pins[rid], resources[payload["iri"]] = pin, resource
        dependencies = set(payload.get("parent_ids", []))
        dependencies.update(
            ref["target_id"] for ref in payload.get("resource_refs", [])
        )
        for dep in sorted(dependencies):
            owned_pin = payload.get("owned_versions", {}).get(str(dep))
            candidates = [r for r in catalog.values() if r["id"] == dep]
            if owned_pin is not None:
                candidates = [r for r in candidates if r["revision"] == owned_pin]
            if len(candidates) != 1:
                raise _reject(
                    ErrorCode.ONTOLOGY_CHECKS_INCOMPLETE,
                    "authorized_dependency_pin_missing",
                    resource_id=dep,
                )
            pending.append(candidates[0])
    return resources, pins


def _metadata(target: ModelResource | Ontology, metadata: dict) -> None:
    target.label_i18n = {k: v for k, v in metadata["labels"].items() if v is not None}
    target.definition_i18n = {
        k: v for k, v in metadata["definitions"].items() if v is not None
    }
    target.synonyms = deepcopy(metadata["synonyms"])


def _persist_resources(
    session: Session, plan: dict, context: dict
) -> tuple[dict[str, ModelingResourceMapping], dict[int, int | None]]:
    operations = plan["resources"]
    new_iris = {op["iri"] for op in operations if op["kind"] != "REUSE"}
    required: set[str] = {
        op["iri"]
        for op in operations
        if op["kind"] == "REUSE" and op["attach_to_ontology"]
    }
    for op in operations:
        required.update(op.get("parents", []))
        required.update(
            op[key] for key in ("owner_iri", "domain_iri", "range_iri") if key in op
        )
    for constraint in plan["constraints"]:
        required.update((constraint["target_iri"], constraint["spec"]["path"]["iri"]))
        required.update(constraint["spec"].get("allowed_class", {}).get("iris", []))
    for axiom in plan.get("axioms", []):
        if axiom["kind"] not in {
            "EQUIVALENT_CLASSES",
            "DISJOINT_CLASSES",
            "SUBPROPERTY",
        }:
            raise _reject(ErrorCode.ONTOLOGY_CONSTRUCT_UNSUPPORTED, "unsupported_axiom")
        required.update(axiom.get("iris", []))
        required.update(axiom[key] for key in ("sub_iri", "super_iri") if key in axiom)
    authorized_iris = {r["iri"] for r in context["asset_catalog"].values()}
    if required - new_iris - authorized_iris:
        raise _reject(ErrorCode.ONTOLOGY_PROPOSAL_STALE, "unauthorized_plan_reference")
    resources, reused_pins = _pin_closure(
        session, context["asset_catalog"], required - new_iris
    )
    members: dict[int, int | None] = dict(reused_pins)
    mappings: dict[str, ModelingResourceMapping] = {}
    new_ids: set[int] = set()
    for op in operations:
        kind, iri = op["kind"], op["iri"]
        if kind == "REUSE":
            record = context["asset_catalog"].get(op["handle"])
            if (
                record is None
                or any(record[key] != op[key] for key in ("id", "revision", "iri"))
                or record["kind"] != op["expected_kind"]
            ):
                raise _reject(ErrorCode.ONTOLOGY_PROPOSAL_STALE, "reuse_handle_changed")
            frozen = get_revision(session, op["id"], op["revision"])
            if frozen.payload["iri"] != iri:
                raise _reject(
                    ErrorCode.ONTOLOGY_PROPOSAL_STALE, "reuse_snapshot_changed"
                )
            mappings[op["candidate_id"]] = ModelingResourceMapping(
                resource_id=op["id"],
                iri=iri,
                revision=op["revision"],
                status="PUBLISHED",
            )
            continue
        if kind not in _NEW_KINDS:
            raise _reject(
                ErrorCode.ONTOLOGY_CONSTRUCT_UNSUPPORTED, "unsupported_operation"
            )
        namespace = session.get(Namespace, op["namespace_id"], populate_existing=True)
        if namespace is None or namespace.protected:
            raise _reject(ErrorCode.INVALID_NAMESPACE, "namespace_changed")
        resource = ModelResource(
            kind=_NEW_KINDS[kind],
            name=op["name"],
            iri=iri,
            namespace_id=namespace.id,
            status=ResourceStatus.DRAFT,
            current_revision=0,
            edit_revision=1,
        )
        _metadata(resource, op["metadata"])
        session.add(resource)
        session.flush()
        resources[iri] = resource
        new_ids.add(resource.id)
        members[resource.id] = None
        if kind == "NEW_CLASS":
            for parent_iri in op["parents"]:
                parent = resources[parent_iri]
                if parent.kind not in {ResourceKind.ENTITY, ResourceKind.ASSOC}:
                    raise _reject(ErrorCode.INVALID_REQUEST, "parent_kind_mismatch")
                session.add(ResourceParent(child_id=resource.id, parent_id=parent.id))
        elif kind == "NEW_DATA_PROPERTY":
            owner = resources[op["owner_iri"]]
            if owner.id not in new_ids or owner.kind != ResourceKind.ENTITY:
                raise _reject(
                    ErrorCode.ONTOLOGY_CONSTRUCT_UNSUPPORTED, "data_owner_reuse"
                )
            session.add(
                DatatypePropDetail(
                    resource_id=resource.id,
                    prop_name=op["local_name"],
                    datatype=op["datatype"],
                )
            )
            session.add(
                ResourceRef(source_id=owner.id, target_id=resource.id, role="data_prop")
            )
        else:
            for role, key in (
                ("relation_domain", "domain_iri"),
                ("relation_range", "range_iri"),
            ):
                target = resources[op[key]]
                if target.kind not in {ResourceKind.ENTITY, ResourceKind.ASSOC}:
                    raise _reject(ErrorCode.INVALID_REQUEST, "endpoint_kind_mismatch")
                session.add(
                    ResourceRef(source_id=resource.id, target_id=target.id, role=role)
                )
            session.add(ObjectPropDetail(resource_id=resource.id, owl=op["features"]))
        mappings[op["candidate_id"]] = ModelingResourceMapping(
            resource_id=resource.id, iri=iri, revision=0, status="DRAFT"
        )
    for link in plan["inverse_links"]:
        left, right = resources[link["left_iri"]], resources[link["right_iri"]]
        if left.id not in new_ids or right.id not in new_ids:
            raise _reject(
                ErrorCode.ONTOLOGY_CONSTRUCT_UNSUPPORTED, "inverse_reuse_edit"
            )
        for source, target in ((left, right), (right, left)):
            session.add(
                ResourceRef(source_id=source.id, target_id=target.id, role="inverse_of")
            )
    return mappings, members


def _persist_constraints(
    session: Session,
    proposal: ModelingProposal,
    plan: dict,
    report: ModelingValidationOut,
) -> None:
    bodies = {rule["candidate_id"]: rule for rule in constraint_rules(plan)}
    examples: dict[str, Any] = next(
        (
            check.params.get("examples", {})
            for check in report.checks
            if check.check_code == "M06"
        ),
        {},
    )
    if set(examples) != {rule["candidate_id"] for rule in plan["constraints"]}:
        raise _reject(
            ErrorCode.ONTOLOGY_VALIDATION_STALE, "constraint_examples_changed"
        )
    for constraint in plan["constraints"]:
        body = bodies[constraint["candidate_id"]]
        fixed = examples[constraint["candidate_id"]]
        identifier = "modeling:" + proposal.id + ":" + constraint["candidate_id"]
        definition = RuleCreate(
            identifier=identifier,
            name_i18n={"zh-CN": constraint["candidate_id"]},
            category="ONTOLOGY_MODELING",
            source_kind="ENTERPRISE",
            source_reference=f"proposal:{proposal.id}:revision:{proposal.revision}",
            target_iri=body["target_iri"],
            severity=body["severity"],
            language=body["language"],
            expression=body["expression"],
            execution=body["execution"],
            positive_example=fixed["positive_example"],
            negative_example=fixed["negative_example"],
        )
        rule = Rule(**definition.model_dump(), revision=1)
        session.add(rule)
        session.flush()
        session.add(
            OntologyRuleRef(
                ontology_id=proposal.ontology_id,
                rule_id=rule.id,
                pinned_revision=rule.revision,
            )
        )


def _persist_axioms(session: Session, proposal: ModelingProposal, plan: dict) -> None:
    for body in axiom_rules(plan):
        definition = RuleCreate(
            identifier=f"modeling:{proposal.id}:{body['candidate_id']}",
            name_i18n={"zh-CN": body["candidate_id"]},
            category="ONTOLOGY_MODELING",
            source_kind="ENTERPRISE",
            source_reference=f"proposal:{proposal.id}:revision:{proposal.revision}",
            **{key: value for key, value in body.items() if key != "candidate_id"},
        )
        rule = Rule(**definition.model_dump(), revision=1)
        session.add(rule)
        session.flush()
        session.add(
            OntologyRuleRef(
                ontology_id=proposal.ontology_id,
                rule_id=rule.id,
                pinned_revision=rule.revision,
            )
        )


def apply_proposal(
    session: Session,
    proposal_id: str,
    payload: ModelingApply,
    *,
    proposal_revision: int,
    actor_id: str,
    idempotency_key: str,
) -> ModelingApplyOut:
    """Apply a confirmed revision; caller commits once or rolls back."""
    from app.domain.ontology_modeling_service import (
        compile_proposal,
        get_candidate_revision,
        get_proposal,
        validate_proposal,
    )

    if not actor_id or not idempotency_key or len(idempotency_key) > 128:
        raise _reject(ErrorCode.INVALID_REQUEST, "invalid_idempotency_key")
    payload = ModelingApply.model_validate(payload.model_dump())
    _write_fence(session, actor_id, idempotency_key)
    request_digest = digest(
        {
            "proposal_id": proposal_id,
            "proposal_revision": proposal_revision,
            "payload": payload.model_dump(mode="json"),
        }
    )
    existing = session.scalar(
        select(ModelingApplication)
        .where(
            ModelingApplication.actor_id == actor_id,
            ModelingApplication.idempotency_key == idempotency_key,
        )
        .execution_options(populate_existing=True)
    )
    proposal = get_proposal(session, proposal_id, actor_id)
    if existing is not None:
        if (
            existing.proposal_id != proposal_id
            or existing.request_digest != request_digest
        ):
            raise _reject(ErrorCode.IDEMPOTENCY_CONFLICT, "idempotency_request_changed")
        return ModelingApplyOut.model_validate(existing.result)
    claimed = session.scalar(
        update(ModelingProposal)
        .where(
            ModelingProposal.id == proposal_id,
            ModelingProposal.actor_id == actor_id,
            ModelingProposal.state == ModelingProposalState.READY,
            ModelingProposal.revision == proposal_revision,
        )
        .values(state=ModelingProposalState.READY)
        .returning(ModelingProposal)
        .execution_options(populate_existing=True)
    )
    if claimed is None:
        raise _reject(
            ErrorCode.ONTOLOGY_PROPOSAL_STALE, "proposal_revision_or_state_changed"
        )
    proposal = claimed
    context = proposal.context
    if (
        context["ontology_id"] != proposal.ontology_id
        or context["target_draft_id"] != payload.target_draft_id
        or payload.target_draft_id != f"ontology:{proposal.ontology_id}:working"
        or context["base_edit_revision"] != payload.base_edit_revision
    ):
        raise _reject(ErrorCode.ONTOLOGY_PROPOSAL_STALE, "target_draft_changed")
    onto = session.scalar(
        select(Ontology)
        .where(Ontology.id == proposal.ontology_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if onto is None or onto.status == ResourceStatus.ARCHIVED:
        raise _reject(ErrorCode.ONTOLOGY_PROPOSAL_STALE, "target_unavailable")
    # Parent lock precedes all catalog resource locks in existing assembly APIs.
    for model, ids in (
        (Namespace, sorted({r["id"] for r in context["namespace_catalog"].values()})),
        (
            ModelResource,
            sorted(
                {r["id"] for r in context["asset_catalog"].values()}
                | {int(rid) for rid in context["working_payloads"]}
            ),
        ),
    ):
        list(
            session.scalars(
                select(model)
                .where(model.id.in_(ids))
                .order_by(model.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        )
    rule_ids = sorted({record["rule_id"] for record in context["working_rules"]})
    if rule_ids:
        list(
            session.scalars(
                select(Rule)
                .where(Rule.id.in_(rule_ids))
                .order_by(Rule.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        )
    if onto.template_id is not None:
        lock_template(session, onto.template_id)
    assert_context_current(session, context)
    candidate_revision = get_candidate_revision(session, proposal)
    session.refresh(candidate_revision)
    if digest(candidate_revision.candidate) != candidate_revision.candidate_digest:
        raise _reject(ErrorCode.ONTOLOGY_VALIDATION_STALE, "candidate_content_changed")
    plan = compile_proposal(
        proposal, OntologyCandidate.model_validate(candidate_revision.candidate)
    )
    if payload.compiled_plan_digest != plan["digest"]:
        raise _reject(ErrorCode.ONTOLOGY_VALIDATION_STALE, "compiled_plan_changed")
    if payload.confirmation.accepted_plan_digest != plan["digest"]:
        raise _reject(
            ErrorCode.ONTOLOGY_CONFIRMATION_REQUIRED, "confirmation_plan_changed"
        )
    stored = session.get(
        ModelingValidation, payload.validation_report_id, populate_existing=True
    )
    if (
        stored is None
        or stored.proposal_id != proposal_id
        or stored.revision != proposal_revision
    ):
        raise _reject(ErrorCode.ONTOLOGY_VALIDATION_STALE, "validation_report_changed")
    accepted = ModelingValidationOut.model_validate(stored.report)
    _report_current(accepted, proposal, candidate_revision.candidate_digest, plan)
    rechecked = validate_proposal(
        session, proposal, proposal_revision, candidate_revision.candidate_digest
    )
    _report_current(rechecked, proposal, candidate_revision.candidate_digest, plan)
    if rechecked.model_dump(exclude={"id"}) != accepted.model_dump(exclude={"id"}):
        raise _reject(ErrorCode.ONTOLOGY_VALIDATION_STALE, "validation_result_changed")
    assert_context_current(session, context)
    before: dict[str, int | None] = {
        "current_revision": onto.current_revision,
        "edit_revision": onto.edit_revision,
    }
    onto = lock_ontology_edit(
        session,
        onto,
        payload.base_edit_revision,
        if_match=context["published_revision"],
    )
    mappings, members = _persist_resources(session, plan, context)
    for rid, pin in sorted(members.items()):
        ref = session.scalar(
            select(OntologyResourceRef).where(
                OntologyResourceRef.ontology_id == onto.id,
                OntologyResourceRef.resource_id == rid,
            )
        )
        if ref is None:
            session.add(
                OntologyResourceRef(
                    ontology_id=onto.id, resource_id=rid, pinned_revision=pin
                )
            )
        elif pin is not None and ref.pinned_revision not in {None, pin}:
            raise _reject(
                ErrorCode.REVISION_CONFLICT,
                "existing_member_pin_conflict",
                resource_id=rid,
            )
        elif pin is not None and ref.pinned_revision is None:
            if str(rid) in context["working_payloads"] and (
                context["working_payloads"][str(rid)]
                != get_revision(session, rid, pin).payload
            ):
                raise _reject(
                    ErrorCode.REVISION_CONFLICT, "working_member_cannot_be_replaced"
                )
            ref.pinned_revision = pin
    _persist_constraints(session, proposal, plan, accepted)
    _persist_axioms(session, proposal, plan)
    if plan["metadata"] is not None:
        _metadata(onto, plan["metadata"])
    correlation_id = uuid4().hex
    record_asset_audit(
        session,
        actor_id=actor_id,
        action=AssetAuditAction.ASSEMBLE,
        object_type=AssetType.ONTOLOGY,
        object_id=onto.id,
        version_before=before,
        version_after={
            "current_revision": onto.current_revision,
            "edit_revision": onto.edit_revision,
        },
        result=AuditResult.OK,
        correlation_id=correlation_id,
    )
    result = ModelingApplyOut(
        application_id=uuid4().hex,
        proposal_id=proposal_id,
        proposal_revision=proposal_revision,
        target_draft_id=payload.target_draft_id,
        before_edit_revision=payload.base_edit_revision,
        after_edit_revision=onto.edit_revision,
        candidate_to_resource=mappings,
        validation_report_id=accepted.id,
        audit_correlation_id=correlation_id,
    )
    proposal.state = ModelingProposalState.APPLIED
    session.add(
        ModelingApplication(
            id=result.application_id,
            proposal_id=proposal_id,
            actor_id=actor_id,
            idempotency_key=idempotency_key,
            request_digest=request_digest,
            result=result.model_dump(mode="json"),
        )
    )
    session.flush()
    return result
