"""抽取运行（H-32）的请求/响应模型。"""

from __future__ import annotations

from datetime import datetime

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
