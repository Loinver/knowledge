"""完整导入预览与内容绑定契约；旧装配接口保持兼容。"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.enums import ResourceKind
from app.schemas.ontology_import import (
    OntologyImportConflict,
    OntologyImportPreviewRequest,
)


class OntologyRestoreRequest(OntologyImportPreviewRequest):
    preview_digest: str = Field(pattern=r"^[a-f0-9]{64}$")


class RestoreResourceOut(BaseModel):
    iri: str
    name: str
    kind: ResourceKind
    namespace_iri: str
    namespace_prefix: str
    dependencies: list[str]
    existing_resource_id: int | None = None


class OntologyRestorePreview(BaseModel):
    preview_digest: str
    name: str | None
    root_iri: str | None
    source_revision: int | None
    triple_count: int
    resources: list[RestoreResourceOut]
    enum_names: list[str]
    conflicts: list[OntologyImportConflict]
    unsupported_triples: list[str]
    can_apply: bool


class OntologyRestoreResult(BaseModel):
    ontology_id: int
    current_revision: int
    source_revision: int | None
    created_resource_count: int
    created_dictionary_count: int
