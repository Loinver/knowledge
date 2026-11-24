"""Persisted administrator-managed AI model endpoints."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class AiModelCapability(StrEnum):
    CHAT = "CHAT"
    EMBEDDING = "EMBEDDING"


class AiModelConfig(Base):
    __tablename__ = "ai_model_config"
    __table_args__ = (
        Index("ix_ai_model_config_capability_enabled", "capability", "enabled"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    capability: Mapped[AiModelCapability] = mapped_column(String(16), nullable=False)
    base_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    timeout_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=30, server_default="30"
    )
    model_version: Mapped[str] = mapped_column(
        String(100), nullable=False, default="1", server_default="1"
    )
    credential_cipher: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    revision: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class AiModelDefault(Base):
    __tablename__ = "ai_model_default"

    capability: Mapped[AiModelCapability] = mapped_column(String(16), primary_key=True)
    config_id: Mapped[int | None] = mapped_column(
        ForeignKey("ai_model_config.id", ondelete="SET NULL"), nullable=True
    )
    revision: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
