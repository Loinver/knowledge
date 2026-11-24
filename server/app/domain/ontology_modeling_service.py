"""Proposal lifecycle, fixed context and deterministic review; API owns commits."""

from __future__ import annotations

import unicodedata
from copy import deepcopy
from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.domain.asset_audit_service import record_asset_audit
from app.domain.ontology_modeling_context import assert_context_current, digest
from app.domain.ontology_modeling_plan import compile_candidate
from app.domain.ontology_modeling_prompts import PROMPT_VERSION
from app.models.asset_audit import AssetAuditAction, AssetType
from app.models.enums import AuditResult, ValidationState
from app.models.ontology_modeling import (
    ModelingApplication,
    ModelingCandidateRevision,
    ModelingProposal,
    ModelingProposalState,
    ModelingValidation,
)
from app.schemas.ontology_modeling import (
    ModelingApplyOut,
    ModelingCandidateUpdate,
    ModelingCheck,
    ModelingProposalOut,
    ModelingProposalPage,
    ModelingValidationOut,
)
from app.schemas.ontology_modeling_candidate import (
    CandidateParseError,
    OntologyCandidate,
    parse_candidate_json,
)
from app.semantics.ontology_modeling_validation import validate_candidate_semantics


def record_failed_application(
    session: Session,
    proposal_id: str,
    actor_id: str,
    code: ErrorCode,
    correlation_id: str,
) -> None:
    """After confirmed rollback, retain only permitted identity and error fields."""
    proposal = session.get(ModelingProposal, proposal_id)
    if proposal is None or proposal.actor_id != actor_id:
        return
    record_asset_audit(
        session,
        actor_id=actor_id,
        action=AssetAuditAction.ASSEMBLE,
        object_type=AssetType.ONTOLOGY,
        object_id=proposal.ontology_id,
        version_before=None,
        version_after=None,
        result=AuditResult.FAILED,
        correlation_id=correlation_id,
        error_code=code,
    )


def list_proposals(
    session: Session, ontology_id: int, actor_id: str, page: int, page_size: int
) -> ModelingProposalPage:
    statement = select(ModelingProposal).where(
        ModelingProposal.ontology_id == ontology_id,
        ModelingProposal.actor_id == actor_id,
    )
    total = session.scalar(select(func.count()).select_from(statement.subquery())) or 0
    items = session.scalars(
        statement.order_by(
            ModelingProposal.created_at.desc(), ModelingProposal.id.desc()
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return ModelingProposalPage(
        items=[proposal_out(session, item) for item in items], total=total
    )


def application_by_key(
    session: Session, key: str, actor_id: str
) -> ModelingApplyOut | None:
    application = session.scalar(
        select(ModelingApplication).where(
            ModelingApplication.actor_id == actor_id,
            ModelingApplication.idempotency_key == key,
        )
    )
    return ModelingApplyOut.model_validate(application.result) if application else None


def get_proposal(session: Session, proposal_id: str, actor_id: str) -> ModelingProposal:
    proposal = session.get(ModelingProposal, proposal_id, populate_existing=True)
    # Private source material remains visible only to its authenticated author.
    if proposal is None or proposal.actor_id != actor_id:
        raise KGError(ErrorCode.RESOURCE_NOT_FOUND, {"proposal_id": proposal_id})
    return proposal


def get_candidate_revision(
    session: Session, proposal: ModelingProposal
) -> ModelingCandidateRevision:
    revision = session.scalar(
        select(ModelingCandidateRevision).where(
            ModelingCandidateRevision.proposal_id == proposal.id,
            ModelingCandidateRevision.revision == proposal.revision,
        )
    )
    if revision is None:
        raise KGError(ErrorCode.REVISION_NOT_FOUND, {"proposal_id": proposal.id})
    return revision


def parse_model_candidate(raw: str) -> OntologyCandidate:
    try:
        return parse_candidate_json(raw)
    except CandidateParseError as exc:
        raise KGError(
            ErrorCode.LLM_RESPONSE_INVALID, {"reason": exc.code, **exc.params}
        ) from exc


def existing_request(
    session: Session, actor_id: str, request_key: str, request_digest: str
) -> ModelingProposal | None:
    proposal = session.scalar(
        select(ModelingProposal).where(
            ModelingProposal.actor_id == actor_id,
            ModelingProposal.request_key == request_key,
        )
    )
    if proposal is not None and proposal.request_digest != request_digest:
        raise KGError(ErrorCode.IDEMPOTENCY_CONFLICT)
    return proposal


def save_generated(
    session: Session,
    *,
    actor_id: str,
    request_key: str,
    request_digest: str,
    context: dict,
    candidate: OntologyCandidate,
    model_provenance: dict,
) -> ModelingProposal:
    existing = existing_request(session, actor_id, request_key, request_digest)
    if existing is not None:
        return existing
    assert_context_current(session, context)
    proposal = ModelingProposal(
        id=uuid4().hex,
        ontology_id=context["ontology_id"],
        actor_id=actor_id,
        request_key=request_key,
        request_digest=request_digest,
        revision=1,
        state=ModelingProposalState.READY,
        context=deepcopy(context),
        provenance={
            **model_provenance,
            "prompt_version": PROMPT_VERSION,
            "schema_version": "ontology-candidate/1.0",
        },
    )
    session.add(proposal)
    session.flush()
    data = candidate.model_dump(by_alias=True, mode="json")
    session.add(
        ModelingCandidateRevision(
            proposal_id=proposal.id,
            revision=1,
            candidate=data,
            candidate_digest=digest(data),
            actor_id=actor_id,
            origin="MODEL",
            note="",
        )
    )
    session.flush()
    return proposal


def compile_proposal(proposal: ModelingProposal, candidate: OntologyCandidate) -> dict:
    context = proposal.context
    plan = compile_candidate(
        candidate,
        namespace_catalog=context["namespace_catalog"],
        asset_catalog=context["asset_catalog"],
        source_catalog=context["source_catalog"],
        context_token=context["context_token"],
        profile=context["profile"],
    )
    # Check names against all assets without expanding the LLM material scope.
    inventory = {(name, iri) for _rid, name, iri in context["inventory"]}

    def normalized(value: str) -> str:
        return " ".join(unicodedata.normalize("NFKC", value).casefold().split())

    for item in plan["resources"]:
        if item["kind"] != "REUSE" and any(
            item["name"] == name or item["iri"] == iri for name, iri in inventory
        ):
            plan["issues"].append(
                {
                    "code": "KG.CANDIDATE_NEW_REQUIRES_REUSE",
                    "state": "VIOLATION",
                    "blocking": True,
                    "params": {"candidate_id": item["candidate_id"]},
                }
            )
        if item["kind"] != "REUSE":
            metadata = item["metadata"]
            words = {
                (language, normalized(text))
                for language, text in metadata["labels"].items()
                if text
            }
            words.update(
                (alias["language"], normalized(alias["text"]))
                for alias in metadata["synonyms"]
            )
            kind = {
                "NEW_CLASS": "CLASS",
                "NEW_DATA_PROPERTY": "DATA_PROPERTY",
                "NEW_OBJECT_PROPERTY": "OBJECT_PROPERTY",
            }[item["kind"]]
            for concept in context.get("concept_inventory", []):
                if concept["kind"] == kind and any(
                    (language, normalized(text)) in words
                    for language, text in concept["words"]
                ):
                    plan["issues"].append(
                        {
                            "code": "KG.CANDIDATE_POSSIBLE_SYNONYM",
                            "state": "NOT_RUN",
                            "blocking": True,
                            "params": {
                                "candidate_id": item["candidate_id"],
                                "resource_id": concept["id"],
                            },
                        }
                    )
    if any(issue["blocking"] for issue in plan["issues"]):
        plan["state"] = "BLOCKED"
        plan["resources"] = []
        plan["constraints"] = []
        plan["axioms"] = []
        plan["inverse_links"] = []
        plan["metadata"] = None
    plan["digest"] = digest(
        {key: value for key, value in plan.items() if key != "digest"}
    )
    return plan


def validate_proposal(
    session: Session,
    proposal: ModelingProposal,
    expected_rev: int,
    candidate_digest: str,
) -> ModelingValidationOut:
    if (
        proposal.state != ModelingProposalState.READY
        or proposal.revision != expected_rev
    ):
        raise KGError(ErrorCode.REVISION_CONFLICT, {"actual": proposal.revision})
    assert_context_current(session, proposal.context)
    revision = get_candidate_revision(session, proposal)
    if revision.candidate_digest != candidate_digest:
        raise KGError(ErrorCode.ONTOLOGY_VALIDATION_STALE)
    candidate = OntologyCandidate.model_validate(revision.candidate)
    plan = compile_proposal(proposal, candidate)
    issues = plan["issues"]
    checks = [
        ModelingCheck(
            check_code="M01",
            state=ValidationState.PASS
            if plan["state"] == "COMPILED"
            else ValidationState.VIOLATION
            if any(issue["state"] == "VIOLATION" for issue in issues)
            else ValidationState.NOT_RUN,
            code="candidate_compilation",
            params={"issues": issues},
            coverage="structure_references_dependencies_semantics",
        )
    ]
    checks.extend(
        ModelingCheck.model_validate(check)
        for check in validate_candidate_semantics(plan, proposal.context)
    )
    checks.extend(
        [
            ModelingCheck(
                check_code="M04",
                state=ValidationState.NOT_RUN,
                required=False,
                code="business_instances_not_run",
                coverage="business_instance_data",
            ),
            ModelingCheck(
                check_code="M05",
                state=ValidationState.NA,
                required=False,
                code="business_profile",
                coverage="standard_digitalization_core_profile",
            ),
        ]
    )
    report = ModelingValidationOut(
        id=uuid4().hex,
        proposal_id=proposal.id,
        proposal_revision=proposal.revision,
        candidate_digest=revision.candidate_digest,
        context_fingerprint=proposal.context["fingerprint"],
        compiled_plan_digest=plan["digest"],
        compiler_version=plan["compiler_version"],
        checks=checks,
        blocking_questions=[q.id for q in candidate.questions if q.blocking],
        can_apply=all(
            check.state in {"PASS", "NA"} for check in checks if check.required
        ),
        plan=plan,
    )
    session.add(
        ModelingValidation(
            id=report.id,
            proposal_id=proposal.id,
            revision=proposal.revision,
            report=report.model_dump(mode="json"),
        )
    )
    session.flush()
    return report


def update_candidate(
    session: Session,
    proposal: ModelingProposal,
    payload: ModelingCandidateUpdate,
    expected_rev: int,
) -> ModelingProposal:
    candidate = payload.candidate
    if payload.candidate_json is not None:
        try:
            candidate = parse_candidate_json(payload.candidate_json)
        except CandidateParseError as exc:
            raise KGError(
                ErrorCode.INVALID_REQUEST, {"reason": str(exc.code), **exc.params}
            ) from exc
    if candidate is None:
        raise KGError(ErrorCode.INVALID_REQUEST, {"reason": "missing_candidate"})
    assert_context_current(session, proposal.context)
    claimed = session.scalar(
        update(ModelingProposal)
        .where(
            ModelingProposal.id == proposal.id,
            ModelingProposal.state == ModelingProposalState.READY,
            ModelingProposal.revision == expected_rev,
        )
        .values(revision=ModelingProposal.revision + 1)
        .returning(ModelingProposal)
        .execution_options(populate_existing=True)
    )
    if claimed is None:
        raise KGError(ErrorCode.REVISION_CONFLICT)
    data = candidate.model_dump(by_alias=True, mode="json")
    session.add(
        ModelingCandidateRevision(
            proposal_id=proposal.id,
            revision=claimed.revision,
            candidate=data,
            candidate_digest=digest(data),
            actor_id=proposal.actor_id,
            origin="HUMAN",
            note=payload.note,
        )
    )
    session.flush()
    return claimed


def discard_proposal(
    session: Session, proposal: ModelingProposal, expected_rev: int
) -> ModelingProposal:
    claimed = session.scalar(
        update(ModelingProposal)
        .where(
            ModelingProposal.id == proposal.id,
            ModelingProposal.state == ModelingProposalState.READY,
            ModelingProposal.revision == expected_rev,
        )
        .values(state=ModelingProposalState.DISCARDED)
        .returning(ModelingProposal)
        .execution_options(populate_existing=True)
    )
    if claimed is None:
        raise KGError(ErrorCode.REVISION_CONFLICT)
    # Discard is a state transition, not a new candidate revision.
    session.flush()
    return claimed


def proposal_out(session: Session, proposal: ModelingProposal) -> ModelingProposalOut:
    revision = get_candidate_revision(session, proposal)
    stale = False
    try:
        assert_context_current(session, proposal.context)
    except KGError:
        stale = True
    latest = session.scalar(
        select(ModelingValidation)
        .where(
            ModelingValidation.proposal_id == proposal.id,
            ModelingValidation.revision == proposal.revision,
        )
        .order_by(ModelingValidation.created_at.desc(), ModelingValidation.id.desc())
    )
    validation = ModelingValidationOut.model_validate(latest.report) if latest else None
    if stale and validation is not None:
        validation.can_apply = False
    return ModelingProposalOut(
        id=proposal.id,
        ontology_id=proposal.ontology_id,
        target_draft_id=proposal.context["target_draft_id"],
        base_edit_revision=proposal.context["base_edit_revision"],
        revision=proposal.revision,
        state=proposal.state,
        candidate=OntologyCandidate.model_validate(revision.candidate),
        candidate_digest=revision.candidate_digest,
        provenance=proposal.provenance,
        sources=proposal.context["source_details"],
        stale=stale,
        validation=validation,
        created_at=proposal.created_at,
    )
