"""规则库持久化模型。标准来源仅存条款引用，不内置标准正文。"""

from __future__ import annotations

from sqlalchemy import CheckConstraint, Integer, String, Text, UniqueConstraint
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
