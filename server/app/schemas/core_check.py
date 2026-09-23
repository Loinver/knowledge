"""M-02 标准核心资源逐项核对契约。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ResourceKind

CoreCheckState = Literal[
    "PRESENT",
    "MISSING",
    "KIND_MISMATCH",
    "ENTERPRISE_EXTENSION",
]


class CoreResourceRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=128)
    kind: ResourceKind
    standard_clause_id: int = Field(gt=0)


class CoreCheckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirements: list[CoreResourceRequirement] = Field(min_length=1, max_length=1000)


class CoreCheckItem(BaseModel):
    name: str
    kind: ResourceKind | None
    state: CoreCheckState
    resource_id: int | None = None
    pinned_revision: int | None = None
    standard_clause_id: int | None = None
    reason: str | None = None


class CoreCheckOut(BaseModel):
    template_id: int
    template_revision: int
    items: list[CoreCheckItem]
    all_core_present: bool
    enterprise_extension_count: int
