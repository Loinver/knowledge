"""抽取运行（H-32）的请求/响应模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


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
    run_id: int
    evidence_type: str


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
    derived_edges: list[GraphTripleOut]
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
    run_id: int
    evidence_type: str
    quarantined: bool


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
    nodes: list[GraphViewNode]
    edges: list[GraphViewEdge]
    type_counts: list[GraphTypeCount]
    entity_total: int
    quarantine_count: int
    truncated: bool
