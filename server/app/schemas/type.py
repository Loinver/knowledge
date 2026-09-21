"""实体类型库（H-11）的请求/响应模型。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ResourceKind, ResourceStatus


class DataTypePropCreate(BaseModel):
    """数据属性定义（实体类型的属性）。"""

    name: str
    label_i18n: dict[str, str] | None = None
    definition_i18n: dict[str, str] | None = None
    datatype: str  # string/integer/decimal/boolean/date/enum
    enum_dict_id: int | None = None  # 引用枚举字典（M4 补）
    nullable: bool = True
    default_value: str | None = None


class DataTypePropOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    name: str
    label_i18n: dict[str, str] | None = None
    definition_i18n: dict[str, str] | None = None
    datatype: str
    enum_dict_id: int | None = None
    nullable: bool = True
    default_value: str | None = None


class EntityTypeCreate(BaseModel):
    """创建实体类型。name 是 PascalCase 机读名，不翻译，IRI 由 namespace+name 推导。"""

    name: str
    namespace_id: int
    label_i18n: dict[str, str]
    definition_i18n: dict[str, str] | None = None
    parent_ids: list[int] = Field(default_factory=list)  # 类型层级
    data_props: list[DataTypePropCreate] = Field(default_factory=list)


class EntityTypeUpdate(BaseModel):
    """更新实体类型（草稿态）。带 if_match 修订号做乐观锁。"""

    label_i18n: dict[str, str] | None = None
    definition_i18n: dict[str, str] | None = None
    parent_ids: list[int] | None = None
    data_props: list[DataTypePropCreate] | None = None
    if_match: int


class EntityTypeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    kind: ResourceKind
    name: str
    iri: str
    namespace_id: int
    label_i18n: dict[str, str] | None = None
    definition_i18n: dict[str, str] | None = None
    status: ResourceStatus
    current_revision: int
    data_props: list[DataTypePropOut] = Field(default_factory=list)
    parent_ids: list[int] = Field(default_factory=list)


class EntityTypeBrief(BaseModel):
    """列表项：精简版。"""

    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    iri: str
    label_i18n: dict[str, str] | None = None
    status: ResourceStatus
    current_revision: int


class RevisionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    revision: int
    checksum: str
