"""本体指定发布版本的只读资源与规则契约。"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from app.models.enums import ResourceKind
from app.schemas.enum_dictionary import EnumDictionaryOut
from app.schemas.governance import RuleOut, RuleSourceKind
from app.schemas.relation import CardinalitySpec, OwlFeatures
from app.schemas.type import DataTypePropOut


class HistorySnapshotState(StrEnum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"


class HistoryNamespace(BaseModel):
    prefix: str
    iri: str


class HistoryResourceRef(BaseModel):
    target_id: int
    role: str


class HistoryPropertySnapshot(DataTypePropOut):
    """保留属性默认值、标签、枚举与约束，不裁剪成校验用投影。"""

    role: str
    iri: str
    enum_dictionary: EnumDictionaryOut | None = None


class HistoryObjectPropertySnapshot(BaseModel):
    domain_cardinality: CardinalitySpec
    range_cardinality: CardinalitySpec
    domain_role_i18n: dict[str, str] | None = None
    range_role_i18n: dict[str, str] | None = None
    owl: OwlFeatures


class HistoryResourceSnapshot(BaseModel):
    """沿用 ResourceSnapshot 结构，HTTP 契约不依赖领域模块。"""

    id: int
    name: str
    iri: str
    kind: ResourceKind
    label_i18n: dict[str, str] | None = None
    definition_i18n: dict[str, str] | None = None
    namespace: HistoryNamespace
    parent_ids: list[int]
    resource_refs: list[HistoryResourceRef]
    datatype_props: list[HistoryPropertySnapshot] = Field(default_factory=list)
    object_prop: HistoryObjectPropertySnapshot | None = None
    owl: OwlFeatures | None = None


class OntologyHistoryResourceBrief(BaseModel):
    resource_id: int
    revision: int
    name: str
    iri: str
    kind: ResourceKind
    label_i18n: dict[str, str] | None = None


class OntologyHistoryResourceOut(BaseModel):
    ontology_id: int
    ontology_revision: int
    resource_id: int
    revision: int
    checksum: str
    published_at: datetime
    snapshot: HistoryResourceSnapshot


class OntologyHistoryRuleBrief(BaseModel):
    rule_id: int = Field(gt=0, strict=True)
    revision: int = Field(gt=0, strict=True)
    identifier: str
    source_kind: RuleSourceKind
    source_reference: str
    snapshot_state: HistorySnapshotState


class OntologyHistoryRuleOut(OntologyHistoryRuleBrief):
    ontology_id: int
    ontology_revision: int
    snapshot: RuleOut | None = None


class OntologyRevisionContents(BaseModel):
    ontology_id: int
    revision: int
    published_at: datetime
    resources: list[OntologyHistoryResourceBrief]
    rules: list[OntologyHistoryRuleBrief]
