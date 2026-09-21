"""校验层（H-50 / H-51）。

validation_report 记录一次校验的总体结论；validation_result 记录逐项四态。
四态：PASS / VIOLATION / NA / NOT_RUN。未经执行的项必须返回 NOT_RUN，
绝不能显示成通过——这是合规底线。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
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
from app.models.enums import ValidationState


class ValidationReport(Base):
    """校验报告：针对本体版本或图谱版本的总体结论。"""

    __tablename__ = "validation_report"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scope: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[int] = mapped_column(Integer, nullable=False)
    target_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    summary: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ValidationResult(Base):
    """逐项校验结果：四态 + 焦点节点 + 规则来源。"""

    __tablename__ = "validation_result"
    __table_args__ = (
        UniqueConstraint("report_id", "check_code", name="uq_result_per_check"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    report_id: Mapped[int] = mapped_column(
        ForeignKey("validation_report.id"), nullable=False
    )
    check_code: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[ValidationState] = mapped_column(nullable=False)
    focus_node: Mapped[str | None] = mapped_column(String(640), default=None)
    rule_id: Mapped[str | None] = mapped_column(String(128), default=None)
    detail: Mapped[dict | None] = mapped_column(JSON, default=None)
    message: Mapped[str | None] = mapped_column(Text, default=None)
