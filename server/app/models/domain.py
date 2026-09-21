"""业务域层与本体装配层。

业务域组织类型，支持复用；本体装配引用域/类型/关系，发布冻结全部资源版本。
canvas_layout 单独存储，不产生语义版本（拖节点不触发版本号变化）。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
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
from app.models.enums import ResourceStatus


class BusinessDomain(Base):
    """业务域：按业务边界组织类型，支持复用与模块化。"""

    __tablename__ = "business_domain"
    __table_args__ = (UniqueConstraint("name", name="uq_domain_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    iri: Mapped[str] = mapped_column(String(640), nullable=False)
    label_i18n: Mapped[dict | None] = mapped_column(JSON, default=None)
    definition_i18n: Mapped[dict | None] = mapped_column(JSON, default=None)
    status: Mapped[ResourceStatus] = mapped_column(
        default=ResourceStatus.DRAFT, nullable=False
    )
    current_revision: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class DomainRevision(Base):
    """业务域不可变版本。发布即冻结。"""

    __tablename__ = "domain_revision"
    __table_args__ = (UniqueConstraint("domain_id", "revision"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    domain_id: Mapped[int] = mapped_column(
        ForeignKey("business_domain.id"), nullable=False
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class DomainMember(Base):
    """业务域成员清单。as_ref=True 表示跨域引用（按 IRI 去重）。
    owner_domain 标注维护责任域唯一性。
    """

    __tablename__ = "domain_member"
    __table_args__ = (
        UniqueConstraint("domain_id", "resource_id", "as_ref", name="uq_domain_member"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    domain_id: Mapped[int] = mapped_column(
        ForeignKey("business_domain.id"), nullable=False
    )
    resource_id: Mapped[int] = mapped_column(
        ForeignKey("model_resource.id"), nullable=False
    )
    as_ref: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    owner_domain_id: Mapped[int | None] = mapped_column(
        ForeignKey("business_domain.id"), default=None
    )


class Ontology(Base):
    """本体：装配模板选型 + 引用域/单类型 + 挂入关系 + 规则集。"""

    __tablename__ = "ontology"
    __table_args__ = (UniqueConstraint("name", name="uq_ontology_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    iri: Mapped[str] = mapped_column(String(640), nullable=False)
    label_i18n: Mapped[dict | None] = mapped_column(JSON, default=None)
    definition_i18n: Mapped[dict | None] = mapped_column(JSON, default=None)
    status: Mapped[ResourceStatus] = mapped_column(
        default=ResourceStatus.DRAFT, nullable=False
    )
    current_revision: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    template_id: Mapped[int | None] = mapped_column(
        ForeignKey("assembly_template.id"), default=None
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class OntologyRevision(Base):
    """本体不可变版本。

    ref_domains / ref_types 钉住引用的资源 ID；
    resource_versions 记录发布时全部成员资源的版本号快照（版本冻结）。
    """

    __tablename__ = "ontology_revision"
    __table_args__ = (UniqueConstraint("ontology_id", "revision"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ontology_id: Mapped[int] = mapped_column(ForeignKey("ontology.id"), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    ref_domains: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    ref_types: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    rules: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    resource_versions: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class OntologyResourceRef(Base):
    """本体引用的资源（按 IRI 去重）。相同资源不兼容版本显式冲突。"""

    __tablename__ = "ontology_resource_ref"
    __table_args__ = (
        UniqueConstraint("ontology_id", "resource_id", name="uq_onto_resource_ref"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ontology_id: Mapped[int] = mapped_column(ForeignKey("ontology.id"), nullable=False)
    resource_id: Mapped[int] = mapped_column(
        ForeignKey("model_resource.id"), nullable=False
    )
    pinned_revision: Mapped[int | None] = mapped_column(Integer, default=None)


class CanvasLayout(Base):
    """画布布局（本体设计器/图谱浏览/映射图谱视图）。

    scope 区分不同画布用途；positions 存节点坐标。
    单独存储，不产生语义版本——拖节点不触发版本号变化。
    """

    __tablename__ = "canvas_layout"
    __table_args__ = (
        UniqueConstraint("scope", "owner_id", name="uq_canvas_per_scope"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scope: Mapped[str] = mapped_column(String(32), nullable=False)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False)
    positions: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class AssemblyTemplate(Base):
    """装配模板（M4 治理层前置占位，供 ontology.template_id 外键）。

    来源与依据必填；内置只读、可复制为自定义。
    M0 只建表与外键，M4 填业务逻辑。
    """

    __tablename__ = "assembly_template"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    source: Mapped[str] = mapped_column(String(128), nullable=False)
    basis: Mapped[str] = mapped_column(Text, nullable=False)
    builtin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
