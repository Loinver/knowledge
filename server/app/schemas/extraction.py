"""抽取运行（H-32）的请求/响应模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.models.enums import RunResult


class RunPublicationManifest(BaseModel):
    """已生成的图谱结果集，不包含会随切换改变的 is_current。"""

    graph_revision_id: int
    published_at: datetime


class ExtractionRunExport(BaseModel):
    """下载专用白名单；不包含连接配置、样例行或异常原文。"""

    schema_version: Literal[1] = 1
    run_id: int
    mapping_revision_id: int
    datasource_id: int | None
    ontology_revision: int | None
    status: RunResult
    counts: dict[str, int]
    fingerprint: str | None
    started_at: datetime
    finished_at: datetime | None
    publication: RunPublicationManifest | None


class ExtractionRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    mapping_revision_id: int
    status: str
    cfg_snapshot: dict
    fingerprint: str | None
    counts: dict
    started_at: datetime
    finished_at: datetime | None


class GraphRevisionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    run_id: int
    is_current: bool
    publishable: bool
    published_at: datetime


class EntityIdentityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    graph_revision_id: int
    iri: str
    type_iri: str
    row_key: str
    attrs: dict


class GraphTripleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    graph_revision_id: int
    subject: str
    predicate: str
    object_: str
    props: dict | None = None


class DerivedEdgeOut(GraphTripleOut):
    """派生边：带产出规则与参与直接事实，可解释、可展开。"""

    rule_id: str | None = None
    source_fact_ids: list[int] | None = None


class FactEvidenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    graph_revision_id: int
    subject: str
    predicate: str
    object_: str
    source_id: int
    table_name: str
    row_key: str
    columns: list
    # 与 columns 对齐的转换链：{column, target, transform, params}。
    # 历史行可能为 None（该列是后加的），前端按"未记录"显示。
    column_transforms: list | None = None
    run_id: int
    evidence_type: str
    mapping_revision_id: int | None = None
    ontology_revision: int | None = None
    resource_revisions: dict | None = None
    rule_revisions: dict | None = None


class QuarantineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    run_id: int
    table_name: str
    row_key: str
    field: str
    raw_value: str | None
    transform_chain: list
    rule_id: str
    created_at: datetime


class TaskCreateRequest(BaseModel):
    mapping_revision_id: int
    datasource_id: int
    namespace: str = "https://example.org/kg/"
    incremental: bool = False
    run_after: datetime | None = None


class ExtractionTaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    mapping_revision_id: int
    datasource_id: int
    namespace: str
    status: str
    run_id: int | None
    incremental: bool
    run_after: datetime | None
    progress: dict
    watermark: dict | None
    error: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class RunStartRequest(BaseModel):
    mapping_revision_id: int
    datasource_id: int
    namespace: str = "https://example.org/kg/"


class EntityPage(BaseModel):
    graph_revision_id: int
    items: list[EntityIdentityOut]
    total: int
    page: int
    page_size: int


class EntityDetailOut(BaseModel):
    entity: EntityIdentityOut
    out_edges: list[GraphTripleOut]
    in_edges: list[GraphTripleOut]
    derived_edges: list[DerivedEdgeOut]
    evidence: list[FactEvidenceOut]


class FactOut(BaseModel):
    subject: str
    predicate: str
    object: str


class EvidenceTraceItem(FactOut):
    id: int
    source_id: int
    source_name: str | None
    source_kind: str | None
    table_name: str
    row_key: str
    columns: list[str]
    column_transforms: list | None = None
    run_id: int
    evidence_type: str
    quarantined: bool
    mapping_revision_id: int | None = None
    ontology_revision: int | None = None
    resource_revisions: dict | None = None
    rule_revisions: dict | None = None


class EvidenceTraceOut(BaseModel):
    graph_revision_id: int
    evidences: list[EvidenceTraceItem]
    total_count: int
    quarantined_count: int


class FactTraceOut(EvidenceTraceOut):
    fact: FactOut


class EntityTraceIdentity(BaseModel):
    iri: str
    type_iri: str


class EntityTraceOut(EvidenceTraceOut):
    entity: EntityTraceIdentity


class GraphViewNode(EntityIdentityOut):
    distance: int


class GraphViewEdge(GraphTripleOut):
    kind: Literal["DIRECT", "DERIVED"]


class GraphTypeCount(BaseModel):
    type_iri: str
    count: int


class GraphViewOut(BaseModel):
    graph_revision_id: int
    run_id: int
    ontology_id: int | None = None
    ontology_revision: int | None = None
    nodes: list[GraphViewNode]
    edges: list[GraphViewEdge]
    type_counts: list[GraphTypeCount]
    entity_total: int
    quarantine_count: int
    truncated: bool


class ReverseTraceFact(BaseModel):
    subject: str
    predicate: str
    object: str
    evidence_id: int
    evidence_type: str
    run_id: int


class ReverseTraceOut(BaseModel):
    """反向追溯：来源行 → 参与的事实与实体（源行反查产出）。"""

    graph_revision_id: int
    source_id: int
    source_name: str | None
    table_name: str
    row_key: str
    facts: list[ReverseTraceFact]
    entities: list[str]
