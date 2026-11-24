"""校验报告与逐项结果的响应模型（H-50 / H-51）。"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from app.models.enums import ValidationState


class OntologyValidationTarget(StrEnum):
    WORKING = "WORKING"
    PUBLISHED = "PUBLISHED"


class ValidationBinding(BaseModel):
    target: OntologyValidationTarget
    working_draft_id: str | None = None
    edit_revision: int | None = None
    published_revision: int
    content_digest: str
    checker_version: str


class ValidationReportOut(BaseModel):
    """一次校验的总体结论。summary 为四态计数。"""

    report_id: int
    scope: str
    target_id: int
    target_revision: int
    summary: dict[str, Any] = Field(default_factory=dict)
    binding: ValidationBinding | None = None


class ValidationResultOut(BaseModel):
    """逐项校验结果。state 为四态枚举码之一，绝不能把未执行渲染成通过。"""

    check_code: str
    state: ValidationState
    focus_node: str | None = None
    rule_id: str | None = None
    detail: dict[str, Any] | None = None
    message: str | None = None
