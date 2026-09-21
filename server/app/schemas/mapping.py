"""映射方案（H-30）的请求/响应模型。

实体映射含字段四列（目标属性→源字段→转换规则→空值策略）。
关系映射三模式：FK / JUNCTION / ASSOCIATIVE。
发布冻结目标本体版本（onto_version 钉住 OntologyRevision.revision）。
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class NullPolicy(StrEnum):
    """空值处理策略。"""

    REQUIRED = "REQUIRED"  # 遇空报错
    NULLABLE = "NULLABLE"  # 允许空
    DEFAULT = "DEFAULT"  # 用默认值
    SKIP = "SKIP"  # 跳过该行


class TransformKind(StrEnum):
    """字段转换规则。"""

    IDENTITY = "IDENTITY"  # 原值
    TEMPLATE = "TEMPLATE"  # 模板拼接 ent-{value}
    DATE = "DATE"  # 日期解析
    ENUM = "ENUM"  # 枚举映射
    DECIMAL = "DECIMAL"  # 小数精度


class RelMode(StrEnum):
    """关系映射三模式。"""

    FK = "FK"  # 外键
    JUNCTION = "JUNCTION"  # 中间表（仅两列外键）
    ASSOCIATIVE = "ASSOCIATIVE"  # 带属性关联表


class FieldMap(BaseModel):
    """字段映射四列：目标属性 → 源字段 → 转换规则 → 空值策略。"""

    target_attr: str
    source_field: str
    transform: TransformKind = TransformKind.IDENTITY
    transform_params: dict | None = None
    null_policy: NullPolicy = NullPolicy.NULLABLE
    default_value: str | None = None


class EntityMapCreate(BaseModel):
    """实体映射。一表可生成多类型，一类型可来自多表。"""

    entity_type: str
    table: str
    db_schema: str = Field(default="main", alias="schema")
    field_maps: list[FieldMap]
    key_fields: list[str] = []


class RelEndpointSpec(BaseModel):
    """关系端点：字段 → 引用表/字段。"""

    field: str
    ref_table: str
    ref_field: str


class RelMapCreate(BaseModel):
    """关系映射三模式。"""

    relation_type: str
    mode: RelMode
    table: str
    db_schema: str = Field(default="main", alias="schema")
    # FK 模式
    fk_field: str | None = None
    # JUNCTION / ASSOCIATIVE 两端
    source: RelEndpointSpec | None = None
    target: RelEndpointSpec | None = None
    # ASSOCIATIVE 关联属性
    attributes: list[dict] = []  # [{"attr": "role", "field": "role"}]


class MappingRevisionCreate(BaseModel):
    """映射版本草稿。发布时冻结 onto_version。"""

    entity_maps: list[EntityMapCreate] = []
    rel_maps: list[RelMapCreate] = []


class MappingCreate(BaseModel):
    name: str
    ontology_id: int
    draft: MappingRevisionCreate | None = None


class FieldMapOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    target_attr: str
    source_field: str
    transform: str
    transform_params: dict | None
    null_policy: str
    default_value: str | None


class EntityMapOut(BaseModel):
    entity_type: str
    table: str
    db_schema: str = Field(alias="schema")
    field_maps: list[dict]
    key_fields: list[str]


class RelMapOut(BaseModel):
    relation_type: str
    mode: str
    table: str
    db_schema: str = Field(alias="schema")
    fk_field: str | None
    source: dict | None
    target: dict | None
    attributes: list[dict]


class MappingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    ontology_id: int
    status: str
    current_revision: int


class MappingRevisionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    mapping_id: int
    revision: int
    onto_version: int
    entity_maps: list[dict]
    rel_maps: list[dict]
    published_at: datetime


class MappingBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    ontology_id: int
    status: str
    current_revision: int
