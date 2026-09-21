"""执行与图谱层（H-32 / H-33）。

抽取运行记录版本化；graph_revision 当前结果集指针；
失败运行不覆盖 is_current；entity_identity 稳定 IRI；fact_evidence 证据追溯。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.core.db import Base
from app.models.enums import RunResult


class ExtractionRun(Base):
    """抽取运行记录：状态机 + cfg 快照 + 计数 + 指纹。

    fingerprint 用于幂等校验：同一配置重跑产出一致。
    失败运行不得改写 graph_revision.is_current。
    """

    __tablename__ = "extraction_run"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    mapping_revision_id: Mapped[int] = mapped_column(
        ForeignKey("mapping_revision.id"), nullable=False
    )
    status: Mapped[RunResult] = mapped_column(default=RunResult.PARTIAL)
    cfg_snapshot: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    fingerprint: Mapped[str | None] = mapped_column(String(64), default=None)
    counts: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )


class GraphRevision(Base):
    """图谱版本。is_current 是当前结果集指针。

    失败运行不覆盖 is_current；可从历史成功运行切回。
    唯一性由应用层在发布事务里保证（同一时刻只有一个 is_current=True）。
    """

    __tablename__ = "graph_revision"
    __table_args__ = (Index("ix_graph_current", "is_current"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("extraction_run.id"), nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    publishable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class EntityIdentity(Base):
    """实体实例稳定身份。IRI 集合幂等：重跑产出一致。"""

    __tablename__ = "entity_identity"
    __table_args__ = (
        UniqueConstraint("graph_revision_id", "iri", name="uq_entity_iri"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    graph_revision_id: Mapped[int] = mapped_column(
        ForeignKey("graph_revision.id"), nullable=False
    )
    iri: Mapped[str] = mapped_column(String(640), nullable=False)
    type_iri: Mapped[str] = mapped_column(String(640), nullable=False)
    row_key: Mapped[str] = mapped_column(String(256), nullable=False)
    attrs: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class GraphTriple(Base):
    """关系表三元组。规模上量后再评估图库。"""

    __tablename__ = "graph_triple"
    __table_args__ = (
        Index("ix_triple_subject", "subject"),
        Index("ix_triple_object", "object"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    graph_revision_id: Mapped[int] = mapped_column(
        ForeignKey("graph_revision.id"), nullable=False
    )
    subject: Mapped[str] = mapped_column(String(640), nullable=False)
    predicate: Mapped[str] = mapped_column(String(640), nullable=False)
    object_: Mapped[str] = mapped_column("object", String(640), nullable=False)


class DerivedEdge(Base):
    """派生边：只用于查询加速，不参与计数口径。"""

    __tablename__ = "derived_edge"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    graph_revision_id: Mapped[int] = mapped_column(
        ForeignKey("graph_revision.id"), nullable=False
    )
    subject: Mapped[str] = mapped_column(String(640), nullable=False)
    predicate: Mapped[str] = mapped_column(String(640), nullable=False)
    object_: Mapped[str] = mapped_column("object", String(640), nullable=False)


class FactEvidence(Base):
    """事实证据追溯：每条事实反查到表/行键/字段/运行批次。

    来源被隔离时，前端明确提示"来源记录未进入当前候选图"，
    不伪装为证据完整。
    """

    __tablename__ = "fact_evidence"
    __table_args__ = (Index("ix_evidence_triple", "subject", "predicate", "object"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    graph_revision_id: Mapped[int] = mapped_column(
        ForeignKey("graph_revision.id"), nullable=False
    )
    subject: Mapped[str] = mapped_column(String(640), nullable=False)
    predicate: Mapped[str] = mapped_column(String(640), nullable=False)
    object_: Mapped[str] = mapped_column("object", String(640), nullable=False)
    source_id: Mapped[int] = mapped_column(ForeignKey("datasource.id"), nullable=False)
    table_name: Mapped[str] = mapped_column(String(128), nullable=False)
    row_key: Mapped[str] = mapped_column(String(256), nullable=False)
    columns: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    run_id: Mapped[int] = mapped_column(ForeignKey("extraction_run.id"), nullable=False)
    evidence_type: Mapped[str] = mapped_column(String(32), nullable=False)


class Quarantine(Base):
    """隔离清单：表/源键/字段/原值/转换链/命中规则。"""

    __tablename__ = "quarantine"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("extraction_run.id"), nullable=False)
    table_name: Mapped[str] = mapped_column(String(128), nullable=False)
    row_key: Mapped[str] = mapped_column(String(256), nullable=False)
    field: Mapped[str] = mapped_column(String(128), nullable=False)
    raw_value: Mapped[str | None] = mapped_column(Text, default=None)
    transform_chain: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    rule_id: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
