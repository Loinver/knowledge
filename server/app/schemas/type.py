"""实体类型库（H-11）的请求/响应模型。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ResourceKind, ResourceStatus


class DataTypePropCreate(BaseModel):
    """数据属性定义（实体类型的属性）。"""

    name: str
    label_i18n: dict[str, str] | None = None
    definition_i18n: dict[str, str] | None = None
    datatype: str  # string/integer/decimal/boolean/date/enum
    enum_dict_id: int | None = Field(default=None, gt=0)
    enum_dict_revision: int | None = Field(default=None, gt=0)
    nullable: bool = True
    default_value: str | None = None


class DataTypePropOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    name: str
    # 属性子资源的 IRI（= 所属类型 IRI + "/" + 属性名）。
    # GB/T 48000.3 附录 A 要求属性可定位到 IRI，此前只在库内派生、未对外返回。
    iri: str | None = None
    label_i18n: dict[str, str] | None = None
    definition_i18n: dict[str, str] | None = None
    datatype: str
    enum_dict_id: int | None = None
    enum_dict_revision: int | None = None
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
    edit_revision: int | None = Field(default=None, ge=0)


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
    edit_revision: int
    data_props: list[DataTypePropOut] = Field(default_factory=list)
    parent_ids: list[int] = Field(default_factory=list)


class EntityTypeBrief(BaseModel):
    """列表项：精简版。

    额外带装配规模（数据属性数 / 关系端点数）与最近变更时间 —— 列表页要展示，
    在服务端一次聚合完，避免前端逐行再请求。
    """

    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    iri: str
    label_i18n: dict[str, str] | None = None
    status: ResourceStatus
    current_revision: int
    data_prop_count: int = 0
    relation_count: int = 0
    updated_at: datetime | None = None
    has_violation: bool = False


class EntityTypeStatsOut(BaseModel):
    """实体类型库的库级统计。校验违反取自最近一次资产层校验报告。"""

    total: int = 0
    published: int = 0
    draft: int = 0
    archived: int = 0
    violation: int = 0


class TypeRelationUsageOut(BaseModel):
    """该类型参与的一条关系：自己在哪一端，另一端是什么类型。"""

    id: int
    name: str
    label_i18n: dict[str, str] | None = None
    status: ResourceStatus
    role: str  # domain | range
    other_type_id: int | None = None
    other_name: str | None = None
    other_label_i18n: dict[str, str] | None = None


class TypeRuleUsageOut(BaseModel):
    """挂在该类型 IRI 上的治理规则。"""

    id: int
    identifier: str
    name_i18n: dict[str, str] | None = None
    severity: str


class TypeDomainUsageOut(BaseModel):
    """该类型归属或被引用的业务域。"""

    id: int
    name: str
    label_i18n: dict[str, str] | None = None
    as_ref: bool = False


class TypeOntologyUsageOut(BaseModel):
    """引用了该类型的本体。"""

    id: int
    name: str
    label_i18n: dict[str, str] | None = None
    status: ResourceStatus
    current_revision: int


class TypeRevisionOut(BaseModel):
    revision: int
    published_at: datetime


class TypeValidationOut(BaseModel):
    """最近一次资产层校验里与该类型相关的检查项。"""

    check_code: str
    state: str
    message: str | None = None


class EntityTypeUsagesOut(BaseModel):
    """类型详情页「关联关系 / 规则 / 引用与版本」三个页签的数据源。

    一次请求取全，避免详情页为每个页签发一串请求。
    """

    relations: list[TypeRelationUsageOut] = Field(default_factory=list)
    rules: list[TypeRuleUsageOut] = Field(default_factory=list)
    domains: list[TypeDomainUsageOut] = Field(default_factory=list)
    ontologies: list[TypeOntologyUsageOut] = Field(default_factory=list)
    revisions: list[TypeRevisionOut] = Field(default_factory=list)
    validations: list[TypeValidationOut] = Field(default_factory=list)


class RevisionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    revision: int
    checksum: str
