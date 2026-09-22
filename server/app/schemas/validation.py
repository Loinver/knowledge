"""校验报告与逐项结果的响应模型（H-50 / H-51）。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ValidationReportOut(BaseModel):
    """一次校验的总体结论。summary 为四态计数。"""

    report_id: int
    scope: str
    target_id: int
    summary: dict[str, Any] = Field(default_factory=dict)


class ValidationResultOut(BaseModel):
    """逐项校验结果。state 为四态枚举码之一，绝不能把未执行渲染成通过。"""

    check_code: str
    state: str
    focus_node: str | None = None
    rule_id: str | None = None
    detail: dict[str, Any] | None = None
    message: str | None = None
