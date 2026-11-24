"""实体类型库（H-11）的请求/响应模型。"""

from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.iri import is_valid_any_uri, is_valid_property_name
from app.models.enums import ResourceKind, ResourceStatus


class Synonym(BaseModel):
    """语义元数据别名；不表示等价类或全局唯一身份。"""

    model_config = ConfigDict(extra="forbid", strict=True)
    language: Literal["zh-CN", "en-US"]
    text: str = Field(min_length=1, max_length=200)

    @field_validator("text")
    @classmethod
    def _check_text(cls, value: str) -> str:
        if value != value.strip() or any(ord(char) < 32 for char in value):
            raise ValueError("invalid_synonym_text")
        return value


def _unique_synonyms(values: list[Synonym]) -> list[Synonym]:
    keys = [(value.language, value.text) for value in values]
    if len(set(keys)) != len(keys):
        raise ValueError("duplicate_synonym")
    return values


def _reject_null_synonyms(value: object) -> object:
    if value is None:
        raise ValueError("synonyms_null_unsupported")
    return value


Synonyms = Annotated[
    list[Synonym], Field(max_length=100), AfterValidator(_unique_synonyms)
]
SynonymsUpdate = Annotated[Synonyms | None, BeforeValidator(_reject_null_synonyms)]


class DataTypePropCreate(BaseModel):
    """数据属性定义（实体类型的属性）。"""

    name: str = Field(min_length=1, max_length=128)
    label_i18n: dict[str, str] | None = None
    definition_i18n: dict[str, str] | None = None
    synonyms: Synonyms = Field(default_factory=list)
    datatype: str  # string/integer/decimal/boolean/date/anyURI/enum
    enum_dict_id: int | None = Field(default=None, gt=0)
    enum_dict_revision: int | None = Field(default=None, gt=0)
    nullable: bool = True
    default_value: str | None = None
    # 项目约束能力；不把基数/数值范围归为 GB/T 48000.3 附录 A 的要求。
    min_cardinality: int | None = Field(default=None, ge=0, strict=True)
    max_cardinality: int | None = Field(default=None, ge=0, strict=True)
    min_value: str | None = Field(default=None, max_length=256)
    max_value: str | None = Field(default=None, max_length=256)
    source_clause_ref: str | None = None

    @field_validator("name")
    @classmethod
    def _check_name(cls, value: str) -> str:
        if not is_valid_property_name(value, allow_legacy_underscore=True):
            raise ValueError("invalid_property_name")
        return value

    @field_validator("datatype")
    @classmethod
    def _check_datatype(cls, value: str) -> str:
        if value not in {
            "string",
            "integer",
            "decimal",
            "boolean",
            "date",
            "anyURI",
            "enum",
        }:
            raise ValueError("unsupported_property_datatype")
        return value

    @model_validator(mode="after")
    def _check_constraints(self) -> DataTypePropCreate:
        if (
            self.datatype == "anyURI"
            and self.default_value is not None
            and not is_valid_any_uri(self.default_value)
        ):
            raise ValueError("invalid_any_uri_default")
        minimum = max(self.min_cardinality or 0, int(not self.nullable))
        if self.max_cardinality is not None and self.max_cardinality < minimum:
            raise ValueError("invalid_property_cardinality")
        bounds = [self.min_value, self.max_value]
        if any(bound is not None for bound in bounds):
            if self.datatype not in {"integer", "decimal"}:
                raise ValueError("unsupported_property_range_datatype")
            # SHACL 数值边界导出为 xsd:decimal，整数边界可合法往返为 1.0。
            pattern = r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)"
            for bound in bounds:
                if bound is None:
                    continue
                if not re.fullmatch(pattern, bound):
                    raise ValueError("invalid_property_numeric_bound")
                try:
                    number = Decimal(bound)
                except InvalidOperation:
                    raise ValueError("invalid_property_numeric_bound") from None
                if not number.is_finite():
                    raise ValueError("invalid_property_numeric_bound")
                if self.datatype == "integer" and number != number.to_integral_value():
                    raise ValueError("invalid_integer_property_bound")
            if (
                self.min_value is not None
                and self.max_value is not None
                and Decimal(self.min_value) > Decimal(self.max_value)
            ):
                raise ValueError("invalid_property_numeric_range")
        return self


class DataTypePropOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    name: str
    # 属性子资源的 IRI（= 所属类型 IRI + "/" + 属性名）。
    # GB/T 48000.3 附录 A 要求属性可定位到 IRI，此前只在库内派生、未对外返回。
    iri: str | None = None
    label_i18n: dict[str, str] | None = None
    definition_i18n: dict[str, str] | None = None
    synonyms: Synonyms = Field(default_factory=list)
    datatype: str
    enum_dict_id: int | None = None
    enum_dict_revision: int | None = None
    nullable: bool = True
    default_value: str | None = None
    min_cardinality: int | None = None
    max_cardinality: int | None = None
    min_value: str | None = None
    max_value: str | None = None
    source_clause_ref: str | None = None


class EntityTypeCreate(BaseModel):
    """创建实体类型。name 是 PascalCase 机读名，不翻译，IRI 由 namespace+name 推导。"""

    name: str
    namespace_id: int
    label_i18n: dict[str, str]
    definition_i18n: dict[str, str] | None = None
    synonyms: Synonyms = Field(default_factory=list)
    parent_ids: list[int] = Field(default_factory=list)  # 类型层级
    data_props: list[DataTypePropCreate] = Field(default_factory=list)


class EntityTypeUpdate(BaseModel):
    """更新实体类型（草稿态）。带 if_match 修订号做乐观锁。"""

    label_i18n: dict[str, str] | None = None
    definition_i18n: dict[str, str] | None = None
    synonyms: SynonymsUpdate = None
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
    synonyms: Synonyms = Field(default_factory=list)
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


class ResourceUsagesOut(BaseModel):
    """资源的引用面与版本历史（实体类型与关系类型详情页共用）。

    一次请求取全，避免详情页为每个页签发一串请求。
    """

    rules: list[TypeRuleUsageOut] = Field(default_factory=list)
    domains: list[TypeDomainUsageOut] = Field(default_factory=list)
    ontologies: list[TypeOntologyUsageOut] = Field(default_factory=list)
    revisions: list[TypeRevisionOut] = Field(default_factory=list)
    validations: list[TypeValidationOut] = Field(default_factory=list)


class EntityTypeUsagesOut(ResourceUsagesOut):
    """实体类型详情页「关联关系 / 规则 / 引用与版本」三个页签的数据源。

    比共用部分多一个「关联关系」页签：该类型作为定义域或值域参与的对象属性。
    """

    relations: list[TypeRelationUsageOut] = Field(default_factory=list)


class RevisionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    revision: int
    checksum: str
