"""管理员只读资产审计契约。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.error_codes import ErrorCode
from app.models.asset_audit import AssetAuditAction, AssetType
from app.models.enums import AuditResult

AssetAuditSort = Literal["-created_at", "created_at"]


class AssetAuditVersion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revision: int | None = Field(None, ge=0)
    current_revision: int | None = Field(None, ge=0)
    edit_revision: int | None = Field(None, ge=0)
    run_id: int | None = Field(None, ge=1)
    current_graph_revision_id: int | None = Field(None, ge=1)


class AssetAuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    actor_id: str
    action: AssetAuditAction
    object_type: AssetType
    object_id: int | None
    version_before: AssetAuditVersion | None
    version_after: AssetAuditVersion | None
    result: AuditResult
    error_code: ErrorCode | None
    correlation_id: str
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def utc_timestamp(cls, value: datetime) -> datetime:
        # SQLite 的 server timestamp 无 tzinfo，但语义为 UTC。
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value


class AssetAuditPage(BaseModel):
    items: list[AssetAuditOut]
    total: int
    page: int
    page_size: int
