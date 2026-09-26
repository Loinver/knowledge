"""规则库持久化模型。标准来源仅存条款引用，不内置标准正文。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
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
            "language IN ('SHACL', 'OWL', 'DATA', 'DERIVATION')",
            name="ck_governance_rule_language",
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


class ViewTemplate(Base):
    """图谱视图模板：形态 + 配置 + 钉住的本体版本。

    模板与本体版本绑定：本体发布新版本后 stale=True，前端必须显式
    提示失效，不得静默沿用旧语义渲染。
    """

    __tablename__ = "view_template"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name_i18n: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False)
    layout_id: Mapped[str] = mapped_column(String(64), nullable=False)
    config: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    ontology_id: Mapped[int] = mapped_column(ForeignKey("ontology.id"), nullable=False)
    ontology_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class AiSuggestion(Base):
    """AI 建议（V-DS-05 / V-EX-07）：PENDING → APPLIED/DISCARDED。

    建议永远只是建议：每条独立保存标题、内容与解释，人工逐条
    确认后才会作用到草稿资产，绝不自动落库。
    """

    __tablename__ = "ai_suggestion"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="PENDING", nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )


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
