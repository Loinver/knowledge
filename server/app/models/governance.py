"""规则库持久化模型。标准来源仅存条款引用，不内置标准正文。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.core.db import Base


class Rule(Base):
    __tablename__ = "governance_rule"
    __table_args__ = (
        UniqueConstraint("identifier", name="uq_governance_rule_identifier"),
        CheckConstraint("revision >= 1", name="ck_governance_rule_revision"),
        CheckConstraint(
            "source_kind IN ('STANDARD', 'ENTERPRISE')",
            name="ck_governance_rule_source_kind",
        ),
        CheckConstraint(
            "severity IN ('INFO', 'WARNING', 'VIOLATION')",
            name="ck_governance_rule_severity",
        ),
        CheckConstraint(
            "language IN ('SHACL', 'OWL')", name="ck_governance_rule_language"
        ),
        CheckConstraint(
            "execution IN ('AUTO', 'MANUAL')", name="ck_governance_rule_execution"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    identifier: Mapped[str] = mapped_column(String(128), nullable=False)
    name_i18n: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False)
    category: Mapped[str] = mapped_column(String(128), nullable=False)
    source_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    source_reference: Mapped[str] = mapped_column(String(512), nullable=False)
    target_iri: Mapped[str] = mapped_column(String(2048), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    language: Mapped[str] = mapped_column(String(8), nullable=False)
    expression: Mapped[str] = mapped_column(Text, nullable=False)
    execution: Mapped[str] = mapped_column(String(8), nullable=False)
    positive_example: Mapped[str] = mapped_column(Text, nullable=False)
    negative_example: Mapped[str] = mapped_column(Text, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class StandardClause(Base):
    """标准条款资料：条款编号 + 自撰描述，不抄正文。

    四项解释差异标注用于跨标准对齐，避免直接引用正文。
    """

    __tablename__ = "standard_clause"
    __table_args__ = (
        UniqueConstraint("standard", "clause_number", name="uq_clause_per_standard"),
        CheckConstraint(
            "appendix_nature IN ('NORMATIVE', 'INFORMATIVE')",
            name="ck_clause_appendix_nature",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    standard: Mapped[str] = mapped_column(String(64), nullable=False)
    clause_number: Mapped[str] = mapped_column(String(32), nullable=False)
    title_i18n: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False)
    self_authored_description: Mapped[dict[str, str]] = mapped_column(
        JSON, nullable=False
    )
    product_fallback: Mapped[str | None] = mapped_column(String(256), default=None)
    appendix_nature: Mapped[str] = mapped_column(
        String(12), default="NORMATIVE", nullable=False
    )
    date_lexicon: Mapped[str | None] = mapped_column(String(128), default=None)
    clause_disambiguation: Mapped[str | None] = mapped_column(String(512), default=None)
    example_domain: Mapped[str | None] = mapped_column(String(128), default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
