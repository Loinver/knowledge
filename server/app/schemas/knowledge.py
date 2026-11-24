"""Knowledge-base transport contracts; generated frontend types use this source."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

TaskStatus = Literal[
    "QUEUED", "RUNNING", "SUCCESS", "PARTIAL", "FAILED", "CANCELLED", "INTERRUPTED"
]
TaskPhase = Literal["QUEUED", "EXTRACTING", "INDEXING", "FINISHED"]
SemanticStatus = Literal[
    "NOT_RUN", "NOT_CONFIGURED", "INDEXING", "READY", "FAILED", "STALE"
]
SearchMode = Literal["KEYWORD", "SEMANTIC", "HYBRID"]


class KnowledgeBaseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)

    @field_validator("name")
    @classmethod
    def nonblank_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("blank_name")
        return value.strip()


class KnowledgeBaseUpdate(KnowledgeBaseCreate):
    pass


class KnowledgeBaseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    description: str
    created_by: str
    revision: int
    archived: bool
    index_revision: int
    created_at: datetime
    updated_at: datetime
    document_count: int = 0
    searchable_count: int = 0
    semantic_count: int = 0
    processing_count: int = 0
    failed_count: int = 0
    partial_count: int = 0
    access_scope: Literal["GLOBAL"] = "GLOBAL"


class KnowledgeBasePage(BaseModel):
    items: list[KnowledgeBaseOut]
    total: int
    page: int
    page_size: int


class KnowledgeTaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    document_id: str
    generation: int
    status: TaskStatus
    phase: TaskPhase
    processed_chunks: int
    total_chunks: int
    error_code: str | None = None
    error_reason: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class KnowledgeTaskPage(BaseModel):
    items: list[KnowledgeTaskOut]
    total: int
    page: int
    page_size: int


class KnowledgeIndexOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    generation: int
    parser_version: str
    chunker_version: str
    embedding_version: str | None = None
    embedding_model: str | None = None
    embedding_dimensions: int | None = None
    parse_status: Literal["SUCCESS", "PARTIAL"]
    semantic_status: SemanticStatus
    warnings: list[dict] = Field(default_factory=list)
    error_reason: str | None = None
    created_at: datetime
    chunk_count: int = 0


class KnowledgeDocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    kb_id: int
    name: str
    media_type: str
    content_hash: str
    size_bytes: int
    revision: int
    archived: bool
    generation: int
    active_generation: int | None = None
    created_at: datetime
    updated_at: datetime
    searchable: bool = False
    semantic_status: SemanticStatus = "NOT_RUN"
    duplicate: bool = False
    active_index: KnowledgeIndexOut | None = None
    latest_task: KnowledgeTaskOut | None = None


class KnowledgeDocumentPage(BaseModel):
    items: list[KnowledgeDocumentOut]
    total: int
    page: int
    page_size: int


class KnowledgeLocation(BaseModel):
    start_offset: int
    end_offset: int
    start_line: int
    end_line: int
    paragraph_number: int | None = None
    row_number: int | None = None


class KnowledgeGraphLinkCreate(BaseModel):
    graph_revision_id: int = Field(gt=0)
    entity_iri: str = Field(min_length=1, max_length=2000)
    fact_id: int | None = Field(default=None, gt=0)


class KnowledgeGraphLinkOut(KnowledgeGraphLinkCreate):
    model_config = ConfigDict(from_attributes=True)
    id: str
    chunk_id: str
    predicate: str | None = None
    object_iri: str | None = None
    source: Literal["MANUAL"] = "MANUAL"


class KnowledgeSearchRequest(BaseModel):
    q: str = Field(min_length=1, max_length=2000)
    mode: SearchMode = "KEYWORD"
    top_k: int = Field(default=10, ge=1, le=50)
    min_similarity: float = Field(default=0.25, ge=-1, le=1)

    @field_validator("q")
    @classmethod
    def nonblank_query(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("blank_query")
        return value.strip()


class KnowledgeSearchHit(BaseModel):
    chunk_id: str
    index_id: str
    kb_id: int
    kb_name: str
    document_id: str
    document_name: str
    generation: int
    text: str
    location: KnowledgeLocation
    section: str | None = None
    score: float
    keyword_score: float | None = None
    similarity: float | None = None
    graph_links: list[KnowledgeGraphLinkOut] = Field(default_factory=list)


class KnowledgeGraphEvidenceOut(KnowledgeSearchHit):
    historical: bool


class KnowledgeCoverage(BaseModel):
    total_documents: int
    searchable_documents: int
    semantic_documents: int
    failed_documents: int
    processing_documents: int
    partial_documents: int
    searched_chunks: int
    excluded_semantic_chunks: int = 0


class KnowledgeSearchOut(BaseModel):
    query: str
    mode: SearchMode
    items: list[KnowledgeSearchHit]
    total_matches: int
    top_k: int
    min_similarity: float
    ranking_version: str
    embedding_version: str | None = None
    coverage: KnowledgeCoverage


class KnowledgeEvidenceOut(BaseModel):
    hit: KnowledgeSearchHit
    normalized_text: str
    parser_version: str
    chunker_version: str
    historical: bool
    archived: bool


class KnowledgeAnswerCitation(BaseModel):
    quote: str
    source: KnowledgeSearchHit


class KnowledgeAnswerOut(BaseModel):
    status: Literal["ANSWERED", "INSUFFICIENT_EVIDENCE"]
    question: str
    answer_mode: Literal["EXTRACTIVE"] = "EXTRACTIVE"
    citations: list[KnowledgeAnswerCitation]
    retrieval: KnowledgeSearchOut


class KnowledgeCapabilities(BaseModel):
    chat_configured: bool
    embedding_configured: bool
    embedding_model: str | None
    embedding_version: str | None
    supported_formats: list[str] = ["txt", "md", "csv"]
    max_file_bytes: int = 2 * 1024 * 1024
    max_chunks_per_document: int = 2000
    max_chunks_per_base: int = 10000
    max_documents_per_base: int = 100
    vector_storage: Literal["SQL_EXACT"] = "SQL_EXACT"
    access_scope: Literal["GLOBAL"] = "GLOBAL"
