"""资源与版本层（H-00）。

model_resource 有稳定身份 + 不可变版本；实例与关系数据不得塞回类型定义。
resource_revision 只增不改，发布即冻结。name 唯一、IRI 由 namespace+name 推导。
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
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.core.db import Base
from app.models.enums import ResourceKind, ResourceStatus


class Namespace(Base):
    """命名空间前缀注册（H-03）。

    prefix 是机读短名（如 kg），iri 是完整命名空间（以 # 或 / 结尾）。
    protected=True 的核心命名空间不可删（如标准核心包）。
    """

    __tablename__ = "namespace"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    prefix: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    iri: Mapped[str] = mapped_column(String(512), unique=True, nullable=False)
    protected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    label_i18n: Mapped[dict | None] = mapped_column(JSON, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ModelResource(Base):
    """语义资源主表：实体类型/数据属性/对象属性/关联实体/业务域/本体。

    name 是 PascalCase 机读名，全局唯一，不翻译；IRI = namespace.iri + name。
    label_i18n / definition_i18n 双语 JSONB（L3）。
    current_revision 指向最新已发布版本，草稿态为 0。
    """

    __tablename__ = "model_resource"
    __table_args__ = (
        UniqueConstraint("name", name="uq_resource_name"),
        UniqueConstraint("iri", name="uq_resource_iri"),
        Index("ix_resource_kind", "kind"),
        Index("ix_resource_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[ResourceKind] = mapped_column(nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    iri: Mapped[str] = mapped_column(String(640), nullable=False)
    namespace_id: Mapped[int] = mapped_column(
        ForeignKey("namespace.id"), nullable=False
    )
    label_i18n: Mapped[dict | None] = mapped_column(JSON, default=None)
    definition_i18n: Mapped[dict | None] = mapped_column(JSON, default=None)
    status: Mapped[ResourceStatus] = mapped_column(
        default=ResourceStatus.DRAFT, nullable=False
    )
    current_revision: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    namespace: Mapped[Namespace] = relationship()


class ResourceRevision(Base):
    """资源不可变版本。发布即冻结，只增不改。

    payload 是该版本的完整 JSONB 快照（属性定义、关系端点等）。
    checksum 用于校验完整性。
    """

    __tablename__ = "resource_revision"
    __table_args__ = (
        UniqueConstraint("resource_id", "revision", name="uq_revision_per_resource"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    resource_id: Mapped[int] = mapped_column(
        ForeignKey("model_resource.id"), nullable=False
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    resource: Mapped[ModelResource] = relationship(back_populates="revisions")


ModelResource.revisions = relationship(
    ResourceRevision, order_by="ResourceRevision.revision", back_populates="resource"
)


class ResourceParent(Base):
    """类型层级（继承关系）。子类型引用父类型，按 IRI 去重。"""

    __tablename__ = "resource_parent"
    __table_args__ = (UniqueConstraint("child_id", "parent_id", name="uq_parent_link"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    child_id: Mapped[int] = mapped_column(
        ForeignKey("model_resource.id"), nullable=False
    )
    parent_id: Mapped[int] = mapped_column(
        ForeignKey("model_resource.id"), nullable=False
    )


class ResourceRef(Base):
    """引用统计与更名影响面（H-03）。

    记录谁引用了谁、引用角色（关系端点/域成员/本体引用/映射），
    更名时扫描这张表即可得到完整影响面。
    """

    __tablename__ = "resource_ref"
    __table_args__ = (
        Index("ix_ref_target", "target_id"),
        Index("ix_ref_source", "source_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(
        ForeignKey("model_resource.id"), nullable=False
    )
    target_id: Mapped[int] = mapped_column(
        ForeignKey("model_resource.id"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
