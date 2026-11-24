"""Authenticated modeling review and atomic draft application endpoints."""

from __future__ import annotations

import logging
import re
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.v1.deps import access_token
from app.api.v1.governance_common import required_revision
from app.core.ai_client import CompatibleModel
from app.core.db import get_session
from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.domain import ontology_modeling_service as service
from app.domain.account_service import resolve_session
from app.domain.ai_model_service import get_default_model, is_current, resolve_default
from app.domain.ontology_modeling_context import digest, prepare_context
from app.domain.ontology_modeling_prompts import ALLOWED_CONSTRUCTS, modeling_messages
from app.schemas.ontology_modeling import (
    ModelingApply,
    ModelingApplyOut,
    ModelingCandidateUpdate,
    ModelingCapabilities,
    ModelingCreate,
    ModelingProposalOut,
    ModelingProposalPage,
    ModelingValidate,
    ModelingValidationOut,
)
from app.schemas.ontology_modeling_candidate import (
    CandidateParseError,
    OntologyCandidate,
    parse_bounded_json,
)
from app.schemas.response import ApiResponse

router = APIRouter(prefix="/ai/ontology-modeling", tags=["ontology-modeling"])
_log = logging.getLogger(__name__)


def _rollback_after_error(session: Session, correlation_id: str) -> bool:
    try:
        session.rollback()
    except SQLAlchemyError:
        _log.error("modeling_rollback_unconfirmed correlation=%s", correlation_id)
        return False
    return True


async def check_candidate_body(request: Request) -> None:
    # The regular request decoder loses duplicate keys before Pydantic sees them.
    # Keep the additive object form compatible while checking its original bytes.
    try:
        parse_bounded_json(await request.body(), max_bytes=1_600_000)
    except CandidateParseError as exc:
        raise KGError(
            ErrorCode.INVALID_REQUEST, {"reason": exc.code, **exc.params}
        ) from exc


@router.get("/candidate-schema", response_model=ApiResponse[dict[str, Any]])
def candidate_schema() -> dict[str, Any]:
    return OntologyCandidate.model_json_schema(by_alias=True)


def modeling_actor(
    token: str = Depends(access_token), session: Session = Depends(get_session)
) -> str:
    with Session(bind=session.get_bind()) as auth:
        return resolve_session(auth, token).id


def request_key(value: str = Header(alias="Idempotency-Key")) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_-]{16,128}", value):
        raise KGError(ErrorCode.INVALID_REQUEST, {"reason": "invalid_idempotency_key"})
    return value


@router.get("/capabilities", response_model=ApiResponse[ModelingCapabilities])
def capabilities(session: Session = Depends(get_session)) -> ModelingCapabilities:
    return ModelingCapabilities(
        allowed_constructs=ALLOWED_CONSTRUCTS,
        chat_configured=get_default_model(session, "CHAT") is not None,
    )


@router.post(
    "/proposals", response_model=ApiResponse[ModelingProposalOut], status_code=201
)
async def generate(
    payload: ModelingCreate,
    key: str = Depends(request_key),
    actor_id: str = Depends(modeling_actor),
    session: Session = Depends(get_session),
) -> ModelingProposalOut:
    request_digest = digest(payload.model_dump(mode="json"))
    existing = service.existing_request(session, actor_id, key, request_digest)
    if existing is not None:
        return service.proposal_out(session, existing)
    context = prepare_context(session, payload)
    model = resolve_default(session, "CHAT")
    if model is None:
        raise KGError(ErrorCode.LLM_NOT_CONFIGURED, {"capability": "CHAT"})
    system, user = modeling_messages(context)
    if len(user.encode()) > 400_000:
        raise KGError(
            ErrorCode.INVALID_REQUEST, {"reason": "modeling_context_too_large"}
        )
    # Release the read transaction before waiting for bounded inference.
    session.rollback()
    raw = await CompatibleModel(model.endpoint).chat(
        system, user, max_tokens=8192, require_complete=True
    )
    candidate = service.parse_model_candidate(raw)
    try:
        with session.begin():
            if not is_current(session, model):
                raise KGError(
                    ErrorCode.ONTOLOGY_PROPOSAL_STALE,
                    {"reason": "model_configuration_changed"},
                )
            proposal = service.save_generated(
                session,
                actor_id=actor_id,
                request_key=key,
                request_digest=request_digest,
                context=context,
                candidate=candidate,
                model_provenance={
                    "config_id": model.config_id,
                    "config_revision": model.config_revision,
                    "default_revision": model.default_revision,
                    "model_version": model.model_version,
                },
            )
            result = service.proposal_out(session, proposal)
        return result
    except IntegrityError:
        session.rollback()
        existing = service.existing_request(session, actor_id, key, request_digest)
        if existing is None:
            raise
        return service.proposal_out(session, existing)


@router.get("/proposals", response_model=ApiResponse[ModelingProposalPage])
def list_proposals(
    ontology_id: int = Query(gt=0),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    actor_id: str = Depends(modeling_actor),
    session: Session = Depends(get_session),
) -> ModelingProposalPage:
    return service.list_proposals(session, ontology_id, actor_id, page, page_size)


@router.get("/proposals/{proposal_id}", response_model=ApiResponse[ModelingProposalOut])
def get_proposal(
    proposal_id: str,
    actor_id: str = Depends(modeling_actor),
    session: Session = Depends(get_session),
) -> ModelingProposalOut:
    return service.proposal_out(
        session, service.get_proposal(session, proposal_id, actor_id)
    )


@router.put(
    "/proposals/{proposal_id}/candidate",
    response_model=ApiResponse[ModelingProposalOut],
)
def edit_candidate(
    proposal_id: str,
    payload: ModelingCandidateUpdate,
    revision: int = Depends(required_revision),
    actor_id: str = Depends(modeling_actor),
    session: Session = Depends(get_session),
    _checked_body: None = Depends(check_candidate_body),
) -> ModelingProposalOut:
    with session.begin():
        proposal = service.get_proposal(session, proposal_id, actor_id)
        service.update_candidate(session, proposal, payload, revision)
        return service.proposal_out(session, proposal)


@router.post(
    "/proposals/{proposal_id}/validate",
    response_model=ApiResponse[ModelingValidationOut],
)
def validate_candidate(
    proposal_id: str,
    payload: ModelingValidate,
    revision: int = Depends(required_revision),
    actor_id: str = Depends(modeling_actor),
    session: Session = Depends(get_session),
) -> ModelingValidationOut:
    with session.begin():
        return service.validate_proposal(
            session,
            service.get_proposal(session, proposal_id, actor_id),
            revision,
            payload.candidate_digest,
        )


@router.get(
    "/proposals/{proposal_id}/preview", response_model=ApiResponse[ModelingProposalOut]
)
def preview(
    proposal_id: str,
    revision: int = Query(ge=1),
    actor_id: str = Depends(modeling_actor),
    session: Session = Depends(get_session),
) -> ModelingProposalOut:
    proposal = service.get_proposal(session, proposal_id, actor_id)
    if proposal.revision != revision:
        raise KGError(ErrorCode.REVISION_CONFLICT)
    return service.proposal_out(session, proposal)


@router.post(
    "/proposals/{proposal_id}/discard", response_model=ApiResponse[ModelingProposalOut]
)
def discard(
    proposal_id: str,
    revision: int = Depends(required_revision),
    actor_id: str = Depends(modeling_actor),
    session: Session = Depends(get_session),
) -> ModelingProposalOut:
    with session.begin():
        proposal = service.get_proposal(session, proposal_id, actor_id)
        service.discard_proposal(session, proposal, revision)
        return service.proposal_out(session, proposal)


@router.post(
    "/proposals/{proposal_id}/apply", response_model=ApiResponse[ModelingApplyOut]
)
def apply(
    proposal_id: str,
    payload: ModelingApply,
    revision: int = Depends(required_revision),
    key: str = Depends(request_key),
    actor_id: str = Depends(modeling_actor),
    session: Session = Depends(get_session),
) -> ModelingApplyOut:
    from app.domain.ontology_modeling_apply import apply_proposal

    try:
        result = apply_proposal(
            session,
            proposal_id,
            payload,
            proposal_revision=revision,
            actor_id=actor_id,
            idempotency_key=key,
        )
    except Exception as exc:
        correlation_id = uuid4().hex
        if not _rollback_after_error(session, correlation_id):
            raise
        # An apply error before COMMIT is a confirmed rollback. A separate
        # transaction records only safe fields; it cannot flush failed assets.
        code = (
            exc.code
            if isinstance(exc, KGError)
            else ErrorCode.DATABASE_ERROR
            if isinstance(exc, SQLAlchemyError)
            else ErrorCode.INTERNAL_ERROR
        )
        try:
            with (
                Session(bind=session.get_bind()) as failure_session,
                failure_session.begin(),
            ):
                service.record_failed_application(
                    failure_session, proposal_id, actor_id, code, correlation_id
                )
        except SQLAlchemyError:
            _log.error(
                "modeling_failure_audit_unavailable correlation=%s", correlation_id
            )
        raise
    try:
        session.commit()
    except SQLAlchemyError as exc:
        # A lost COMMIT acknowledgement is not proof of rollback. The immutable
        # receipt and original key are the recovery path, not a new apply key.
        _rollback_after_error(session, uuid4().hex)
        raise KGError(
            ErrorCode.ONTOLOGY_APPLICATION_OUTCOME_UNKNOWN, {"idempotency_key": key}
        ) from exc
    return result


@router.get("/applications/by-key", response_model=ApiResponse[ModelingApplyOut | None])
def application_by_key(
    key: str = Query(min_length=16, max_length=128),
    actor_id: str = Depends(modeling_actor),
    session: Session = Depends(get_session),
) -> ModelingApplyOut | None:
    return service.application_by_key(session, key, actor_id)
