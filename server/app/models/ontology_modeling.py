"""AI modeling proposals are review records, never published ontology versions."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.core.db import Base


class ModelingProposalState(StrEnum):
    READY = "READY"
    DISCARDED = "DISCARDED"
    APPLIED = "APPLIED"


class ModelingProposal(Base):
    __tablename__ = "ontology_modeling_proposal"
    __table_args__ = (UniqueConstraint("actor_id", "request_key"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    ontology_id: Mapped[int] = mapped_column(ForeignKey("ontology.id"), index=True)
    actor_id: Mapped[str] = mapped_column(String(32))
    request_key: Mapped[str] = mapped_column(String(128))
    request_digest: Mapped[str] = mapped_column(String(64))
    revision: Mapped[int] = mapped_column(Integer, default=1)
    state: Mapped[ModelingProposalState] = mapped_column(
        String(16), default=ModelingProposalState.READY
    )
    context: Mapped[dict] = mapped_column(JSON)
    provenance: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ModelingCandidateRevision(Base):
    __tablename__ = "ontology_modeling_revision"
    __table_args__ = (UniqueConstraint("proposal_id", "revision"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    proposal_id: Mapped[str] = mapped_column(
        ForeignKey("ontology_modeling_proposal.id")
    )
    revision: Mapped[int] = mapped_column(Integer)
    candidate: Mapped[dict] = mapped_column(JSON)
    candidate_digest: Mapped[str] = mapped_column(String(64))
    actor_id: Mapped[str] = mapped_column(String(32))
    origin: Mapped[str] = mapped_column(String(16))
    note: Mapped[str] = mapped_column(String(1000), default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ModelingValidation(Base):
    __tablename__ = "ontology_modeling_validation"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    proposal_id: Mapped[str] = mapped_column(
        ForeignKey("ontology_modeling_proposal.id"), index=True
    )
    revision: Mapped[int] = mapped_column(Integer)
    report: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ModelingApplication(Base):
    __tablename__ = "ontology_modeling_application"
    __table_args__ = (
        UniqueConstraint("proposal_id"),
        UniqueConstraint("actor_id", "idempotency_key"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    proposal_id: Mapped[str] = mapped_column(
        ForeignKey("ontology_modeling_proposal.id")
    )
    actor_id: Mapped[str] = mapped_column(String(32))
    idempotency_key: Mapped[str] = mapped_column(String(128))
    request_digest: Mapped[str] = mapped_column(String(64))
    result: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
