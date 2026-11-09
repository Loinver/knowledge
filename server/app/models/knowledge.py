"""Knowledge uploads and immutable published index generations."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def new_id() -> str:
    return uuid.uuid4().hex


class KnowledgeBase(Base):
    __tablename__ = "knowledge_base"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(String(4000), default="")
    created_by: Mapped[str] = mapped_column(ForeignKey("app_user.id"))
    revision: Mapped[int] = mapped_column(default=1, server_default="1")
    archived: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    index_revision: Mapped[int] = mapped_column(default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_document"
    __table_args__ = (
        UniqueConstraint("kb_id", "content_hash", name="uq_knowledge_document_hash"),
        CheckConstraint("length(content) <= 2097152", name="ck_knowledge_content_size"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    kb_id: Mapped[int] = mapped_column(ForeignKey("knowledge_base.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    media_type: Mapped[str] = mapped_column(String(100))
    content: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)
    content_hash: Mapped[str] = mapped_column(String(64))
    revision: Mapped[int] = mapped_column(default=1, server_default="1")
    archived: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    generation: Mapped[int] = mapped_column(default=0, server_default="0")
    active_generation: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class KnowledgeIndex(Base):
    __tablename__ = "knowledge_index"
    __table_args__ = (
        UniqueConstraint(
            "document_id", "generation", name="uq_knowledge_index_generation"
        ),
        CheckConstraint(
            "parse_status IN ('SUCCESS', 'PARTIAL')", name="ck_knowledge_parse_status"
        ),
        CheckConstraint(
            "semantic_status IN ('NOT_CONFIGURED', 'INDEXING', 'READY', 'FAILED')",
            name="ck_knowledge_semantic_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(ForeignKey("knowledge_document.id"))
    generation: Mapped[int] = mapped_column(Integer)
    normalized_text: Mapped[str] = mapped_column(Text, deferred=True)
    parser_version: Mapped[str] = mapped_column(String(100))
    chunker_version: Mapped[str] = mapped_column(String(100))
    embedding_version: Mapped[str | None] = mapped_column(String(100))
    embedding_model: Mapped[str | None] = mapped_column(String(255))
    embedding_dimensions: Mapped[int | None] = mapped_column(Integer)
    parse_status: Mapped[str] = mapped_column(String(16))
    semantic_status: Mapped[str] = mapped_column(String(32))
    warnings: Mapped[list[dict]] = mapped_column(JSON, default=list)
    error_reason: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunk"
    __table_args__ = (
        CheckConstraint("length(text) <= 800", name="ck_knowledge_chunk_size"),
    )

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    index_id: Mapped[str] = mapped_column(ForeignKey("knowledge_index.id"), index=True)
    text: Mapped[str] = mapped_column(String(800))
    location: Mapped[dict] = mapped_column(JSON)
    section: Mapped[str | None] = mapped_column(Text)
    vector: Mapped[list[float] | None] = mapped_column(JSON)


class KnowledgeTask(Base):
    __tablename__ = "knowledge_task"
    __table_args__ = (
        UniqueConstraint(
            "document_id", "generation", name="uq_knowledge_task_generation"
        ),
        Index("ix_knowledge_task_claim", "status", "expires_at", "created_at"),
        CheckConstraint(
            "status IN ('QUEUED', 'RUNNING', 'SUCCESS', 'PARTIAL', "
            "'FAILED', 'CANCELLED', 'INTERRUPTED')",
            name="ck_knowledge_task_status",
        ),
        CheckConstraint(
            "phase IN ('QUEUED', 'EXTRACTING', 'INDEXING', 'FINISHED')",
            name="ck_knowledge_task_phase",
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(ForeignKey("knowledge_document.id"))
    generation: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="QUEUED")
    phase: Mapped[str] = mapped_column(String(16), default="QUEUED")
    processed_chunks: Mapped[int] = mapped_column(default=0, server_default="0")
    total_chunks: Mapped[int] = mapped_column(default=0, server_default="0")
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_reason: Mapped[str | None] = mapped_column(String(200))
    worker_id: Mapped[str | None] = mapped_column(String(64))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
