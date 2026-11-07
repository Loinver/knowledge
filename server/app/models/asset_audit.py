"""业务资产审计：只保存身份、操作和版本，不保存业务载荷。

操作者与对象 ID 故意没有外键：删除账号或资产不得改变历史。
没有清理任务、更新接口或删除接口，默认保留全部事件。
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import JSON, DateTime, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class AssetAuditAction(StrEnum):
    CREATE = "CREATE"
    EDIT = "EDIT"
    RENAME = "RENAME"
    ASSEMBLE = "ASSEMBLE"
    PUBLISH = "PUBLISH"
    UNPUBLISH = "UNPUBLISH"
    DELETE = "DELETE"
    SWITCH_CURRENT = "SWITCH_CURRENT"
    IMPORT = "IMPORT"


class AssetType(StrEnum):
    NAMESPACE = "NAMESPACE"
    ENTITY_TYPE = "ENTITY_TYPE"
    RELATION_TYPE = "RELATION_TYPE"
    BUSINESS_DOMAIN = "BUSINESS_DOMAIN"
    ONTOLOGY = "ONTOLOGY"
    MAPPING = "MAPPING"
    DATASOURCE = "DATASOURCE"
    RULE = "RULE"
    ASSEMBLY_TEMPLATE = "ASSEMBLY_TEMPLATE"
    ENUM_DICTIONARY = "ENUM_DICTIONARY"
    STANDARD_CLAUSE = "STANDARD_CLAUSE"
    GRAPH_REVISION = "GRAPH_REVISION"


class AssetAuditLog(Base):
    __tablename__ = "asset_audit_log"
    __table_args__ = (
        Index("ix_asset_audit_created", "created_at", "id"),
        Index("ix_asset_audit_actor", "actor_id", "created_at"),
        Index("ix_asset_audit_object", "object_type", "object_id", "created_at"),
        Index("ix_asset_audit_correlation", "correlation_id", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor_id: Mapped[str] = mapped_column(String(32), nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    object_type: Mapped[str] = mapped_column(String(32), nullable=False)
    # 创建失败时资产尚未获得身份，明确保留 NULL。
    object_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    version_before: Mapped[dict[str, int | None] | None] = mapped_column(JSON)
    version_after: Mapped[dict[str, int | None] | None] = mapped_column(JSON)
    result: Mapped[str] = mapped_column(String(8), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    correlation_id: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
