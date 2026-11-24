"""Explicit document references pinned to existing graph facts or entities."""

from __future__ import annotations

import secrets
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class KnowledgeGraphLink(Base):
    __tablename__ = "knowledge_graph_link"
    __table_args__ = (
        UniqueConstraint(
            "chunk_id",
            "graph_revision_id",
            "entity_iri",
            "fact_id",
            name="uq_knowledge_graph_link",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(32), primary_key=True, default=lambda: secrets.token_hex(16)
    )
    chunk_id: Mapped[str] = mapped_column(ForeignKey("knowledge_chunk.id"), index=True)
    graph_revision_id: Mapped[int] = mapped_column(
        ForeignKey("graph_revision.id"), index=True
    )
    entity_iri: Mapped[str] = mapped_column(String(2000))
    fact_id: Mapped[int | None] = mapped_column(
        ForeignKey("graph_triple.id"), default=None
    )
    predicate: Mapped[str | None] = mapped_column(String(2000), default=None)
    object_iri: Mapped[str | None] = mapped_column(String(2000), default=None)
    created_by: Mapped[str] = mapped_column(ForeignKey("app_user.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
