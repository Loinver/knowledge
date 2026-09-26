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
    """实体映射。一表可生成多类型，一类型可来自多表。

    match_keys 是跨表业务键（如统一社会信用代码）：多张表映射到同一
    entity_type 时，按业务键值生成同一稳定 IRI，实现跨表实体融合；
    每张来源表各自保留 FactEvidence，证据不合并。
    """

    entity_type: str
    table: str
    db_schema: str = Field(default="main", alias="schema")
    field_maps: list[FieldMap]
    key_fields: list[str] = []
    match_keys: list[str] = []
    # 增量水位字段（如 updated_at / 自增 id）：配合异步任务的增量运行过滤
    incremental_field: str | None = None


class RelEndpointCandidate(BaseModel):
    """多态端点候选：一列值 → 一张引用表。

    when 与端点 spec 的 type_field 配合：type_field 的行值等于 when
    时启用该候选；不配 type_field 时按列非空顺序取第一个候选。
    """

    field: str
    ref_table: str
    ref_field: str | None = None
    when: str | None = None
    # 引用实体在本体中的类型名；提供时优先按业务键匹配已建实体
    ref_entity_type: str | None = None


class RelEndpointVia(BaseModel):
    """二跳端点：先按本行连接列找到经由表的行，再在该行上判别端点。

    典型结构：持股表的 shareholder_id → 股东表（多态）→ 按
    shareholder_type 判别引用自然人表或企业表。
    """

    table: str
    field: str  # 本行提供连接值的列（如 shareholder_id）
    ref_field: str = "id"  # 经由表的查找列


class RelEndpointSpec(BaseModel):
    """关系端点：字段 → 引用表/字段，支持多态候选与二跳经由。

    单候选端点等价于 candidates=[{field, ref_table, ref_field}]；
    多候选 + type_field 表达"判别字段决定端点表"的多态结构；
    via 声明时，判别字段与候选列都在经由表的行上求值。
    """

    field: str = ""
    ref_table: str = ""
    ref_field: str = ""
    candidates: list[RelEndpointCandidate] = []
    type_field: str | None = None
    via: RelEndpointVia | None = None


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


class SaveDraftRequest(BaseModel):
    draft: MappingRevisionCreate
    if_match: int
    if_edit_match: int | None = Field(default=None, ge=0)


class PublishRequest(BaseModel):
    if_match: int
    if_edit_match: int | None = Field(default=None, ge=0)


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
    edit_revision: int


class MappingRevisionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    mapping_id: int
    revision: int
    edit_revision: int
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
    edit_revision: int
