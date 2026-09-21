"""关系类型库（H-12）请求/响应模型。

关系是对象属性（OBJECT_PROP）。关系端点引用实体类型，按 IRI 去重。
基数注明约束方向（如每个 Employee 最多 1 个 Department）。
启用关系属性时切换到关联实体（ASSOC）模式：关系端点不直接产生三元组，
而是生成一个 ASSOC 类型的 ModelResource 承载属性清单，端点通过 role 标注。
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import ResourceKind, ResourceStatus


class CardinalitySpec(BaseModel):
    """基数约束。min/max 必须成对，方向由 spec 自身描述。

    约束方向由调用方在 domain/range 上分别提供，例如：
      domain_cardinality = {min: 0, max: 1, role: "Employee 最多 1 个 Department"}
      range_cardinality  = {min: 0, max: -1, role: "Department 可有 N 个 Employee"}
    max = -1 表示无上限。
    """

    min: int = Field(default=0, ge=0)
    max: int = Field(default=-1, ge=-1)
    role_label_i18n: dict[str, str] | None = None

    @model_validator(mode="after")
    def _check_bounds(self) -> CardinalitySpec:
        if self.max != -1 and self.max < self.min:
            raise ValueError("max must be -1 (unbounded) or >= min")
        return self


class OwlFeatures(BaseModel):
    """OWL 关系特征。兼容性在领域服务校验。"""

    functional: bool = False
    inverse_functional: bool = False
    symmetric: bool = False
    transitive: bool = False


class EndpointSpec(BaseModel):
    """关系端点：引用实体类型 + 在该端点的基数。"""

    type_id: int
    cardinality: CardinalitySpec = Field(default_factory=CardinalitySpec)
    role_i18n: dict[str, str] | None = None


class RelationTypeCreate(BaseModel):
    """创建关系类型。

    domain_spec / range_spec 引用实体类型 id，跨业务域可引用。
    inverse_of 指向另一个关系类型 id，可选。
    enable_attributes=True 时生成关联实体（ASSOC），承载 attribute_defs。
    """

    name: str
    namespace_id: int
    label_i18n: dict[str, str]
    definition_i18n: dict[str, str] | None = None
    domain_spec: EndpointSpec
    range_spec: EndpointSpec
    inverse_of: int | None = None
    owl: OwlFeatures = Field(default_factory=OwlFeatures)
    union_of: list[int] = Field(default_factory=list)
    intersection_of: list[int] = Field(default_factory=list)
    enable_attributes: bool = False
    attribute_defs: list[dict[str, object]] = Field(default_factory=list)


class AttributeDefOut(BaseModel):
    """关联实体上的属性定义（M1 存结构，M4 补完整 OWL 语义）。"""

    name: str
    datatype: str
    nullable: bool = True


class RelationTypeUpdate(BaseModel):
    """更新关系类型（草稿态）。带 if_match 修订号。"""

    label_i18n: dict[str, str] | None = None
    definition_i18n: dict[str, str] | None = None
    domain_spec: EndpointSpec | None = None
    range_spec: EndpointSpec | None = None
    inverse_of: int | None = None
    owl: OwlFeatures | None = None
    union_of: list[int] | None = None
    intersection_of: list[int] | None = None
    enable_attributes: bool | None = None
    attribute_defs: list[dict[str, object]] | None = None
    if_match: int


class RelationTypeOut(BaseModel):
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
    domain_spec: EndpointSpec
    range_spec: EndpointSpec
    inverse_of: int | None = None
    owl: OwlFeatures
    union_of: list[int] = Field(default_factory=list)
    intersection_of: list[int] = Field(default_factory=list)
    enable_attributes: bool
    assoc_resource_id: int | None = None
    attribute_defs: list[AttributeDefOut] = Field(default_factory=list)


class RelationTypeBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    iri: str
    label_i18n: dict[str, str] | None = None
    status: ResourceStatus
    current_revision: int
    enable_attributes: bool
    inverse_of: int | None = None
