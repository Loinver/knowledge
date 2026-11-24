"""Versioned program contract; model output uses its separate candidate schema."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import ValidationState
from app.models.ontology_modeling import ModelingProposalState
from app.schemas.ontology_modeling_candidate import OntologyCandidate

PROTOCOL: Literal["ontology-modeling/1.0"] = "ontology-modeling/1.0"
PROFILE_VERSION = "business/1"


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ModelingExcerpt(Contract):
    title: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=16000)
    authorized: Literal[True]


class ModelingCreate(Contract):
    protocol_version: Literal["ontology-modeling/1.0"] = PROTOCOL
    target_ontology_id: int = Field(gt=0)
    target_draft_id: str
    base_edit_revision: int = Field(ge=0)
    profile: Literal["BUSINESS", "STANDARD_DIGITALIZATION"] = "BUSINESS"
    profile_version: str = PROFILE_VERSION
    text: str = Field(min_length=1, max_length=16000)
    namespace_ids: list[int] = Field(min_length=1, max_length=20)
    asset_ids: list[int] = Field(default_factory=list, max_length=100)
    excerpts: list[ModelingExcerpt] = Field(default_factory=list, max_length=5)
    authorize_model_transfer: Literal[True]


class ModelingCheck(Contract):
    check_code: str
    state: ValidationState
    required: bool = True
    code: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    coverage: str


class ModelingValidationOut(Contract):
    id: str
    proposal_id: str
    proposal_revision: int
    candidate_digest: str
    context_fingerprint: str
    compiled_plan_digest: str
    compiler_version: str
    checks: list[ModelingCheck]
    blocking_questions: list[str]
    can_apply: bool
    plan: dict[str, Any]


class ModelingProposalOut(Contract):
    id: str
    ontology_id: int
    target_draft_id: str
    base_edit_revision: int
    revision: int
    state: ModelingProposalState
    candidate: OntologyCandidate
    candidate_digest: str
    provenance: dict[str, Any]
    sources: dict[str, Any]
    stale: bool
    validation: ModelingValidationOut | None = None
    created_at: datetime


class ModelingProposalPage(Contract):
    items: list[ModelingProposalOut]
    total: int


class ModelingCandidateUpdate(Contract):
    candidate: OntologyCandidate | None = None
    candidate_json: str | None = Field(default=None, max_length=262144)
    note: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def require_one_candidate(self) -> ModelingCandidateUpdate:
        if (self.candidate is None) == (self.candidate_json is None):
            raise ValueError("one_candidate_representation_required")
        return self


class ModelingValidate(Contract):
    candidate_digest: str


class ModelingConfirmation(Contract):
    accepted_plan_digest: str


class ModelingApply(Contract):
    protocol_version: Literal["ontology-modeling/1.0"] = PROTOCOL
    target_draft_id: str
    base_edit_revision: int = Field(ge=0)
    validation_report_id: str
    compiled_plan_digest: str
    confirmation: ModelingConfirmation


class ModelingResourceMapping(Contract):
    resource_id: int
    iri: str
    revision: int
    status: str


class ModelingApplyOut(Contract):
    application_id: str
    proposal_id: str
    proposal_revision: int
    state: Literal["APPLIED_TO_DRAFT"] = "APPLIED_TO_DRAFT"
    target_draft_id: str
    before_edit_revision: int
    after_edit_revision: int
    candidate_to_resource: dict[str, ModelingResourceMapping]
    validation_report_id: str
    audit_correlation_id: str


class ModelingCapabilities(Contract):
    protocol_version: str = PROTOCOL
    schema_version: str = "ontology-candidate/1.0"
    profile_version: str = PROFILE_VERSION
    supported_profiles: list[str] = ["BUSINESS"]
    unsupported_profiles: dict[str, str] = {
        "STANDARD_DIGITALIZATION": "core_profile_not_approved"
    }
    allowed_constructs: dict[str, Any]
    chat_configured: bool
    draft_only: bool = True
