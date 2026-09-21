"""数据接入层与映射层。

数据源凭据密文存储（M2 引入 cryptography），浏览器只拿可展示字段。
元数据快照与变更识别；映射发布冻结目标本体版本。
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
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.core.db import Base
from app.models.domain import Ontology
from app.models.enums import ResourceStatus


class Datasource(Base):
    """数据源连接：连接参数 + 凭据密文。

    浏览器只拿可展示字段（host/port/db_name/状态），凭据密文不出后端。
    """

    __tablename__ = "datasource"
    __table_args__ = (UniqueConstraint("name", name="uq_datasource_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    params: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    credential_cipher: Mapped[str | None] = mapped_column(Text, default=None)
    status: Mapped[str] = mapped_column(String(32), default="DISCONNECTED")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class MetadataSnapshot(Base):
    """元数据快照：库→schema→表/视图→字段。含变更识别 diff。"""

    __tablename__ = "metadata_snapshot"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    datasource_id: Mapped[int] = mapped_column(
        ForeignKey("datasource.id"), nullable=False
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    catalog: Mapped[dict] = mapped_column(JSON, nullable=False)
    diff: Mapped[dict | None] = mapped_column(JSON, default=None)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Mapping(Base):
    """映射方案：把本体语义落到物理表。"""

    __tablename__ = "mapping"
    __table_args__ = (UniqueConstraint("name", name="uq_mapping_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    ontology_id: Mapped[int] = mapped_column(ForeignKey("ontology.id"), nullable=False)
    status: Mapped[ResourceStatus] = mapped_column(
        default=ResourceStatus.DRAFT, nullable=False
    )
    current_revision: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    ontology: Mapped[Ontology] = relationship()


class MappingRevision(Base):
    """映射不可变版本。onto_version 钉住本体版本（版本冻结）。"""

    __tablename__ = "mapping_revision"
    __table_args__ = (UniqueConstraint("mapping_id", "revision"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    mapping_id: Mapped[int] = mapped_column(ForeignKey("mapping.id"), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    onto_version: Mapped[int] = mapped_column(Integer, nullable=False)
    entity_maps: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    rel_maps: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class MappingPreview(Base):
    """映射预览：字段四列实算结果 + 字段级错误定位。"""

    __tablename__ = "mapping_preview"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    mapping_revision_id: Mapped[int] = mapped_column(
        ForeignKey("mapping_revision.id"), nullable=False
    )
    results: Mapped[dict] = mapped_column(JSON, nullable=False)
    errors: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
