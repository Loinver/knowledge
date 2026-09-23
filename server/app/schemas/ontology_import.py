"""M-06 Turtle/JSON-LD 导入预览与显式解决契约。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ResourceKind

ImportFormat = Literal["turtle", "json-ld"]
ImportResolutionAction = Literal["USE_EXISTING", "SKIP"]


class OntologyImportPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format: ImportFormat
    content: str = Field(min_length=1, max_length=65536)
    ontology_id: int | None = Field(default=None, ge=1)


class ImportResourcePreview(BaseModel):
    iri: str
    kind: ResourceKind | None = None
    label_i18n: dict[str, str] = Field(default_factory=dict)
    existing_resource_id: int | None = None
    existing_revision: int | None = None
    conflict_codes: list[str] = Field(default_factory=list)


class OntologyImportConflict(BaseModel):
    iri: str
    code: str
    params: dict[str, object] = Field(default_factory=dict)


class OntologyImportPreview(BaseModel):
    format: ImportFormat
    root_iri: str | None = None
    triple_count: int
    resources: list[ImportResourcePreview]
    conflicts: list[OntologyImportConflict]
    requires_resolution: bool


class OntologyImportResolution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    iri: str = Field(min_length=1, max_length=2048)
    action: ImportResolutionAction
    resource_id: int | None = Field(default=None, ge=1)


class OntologyImportApplyRequest(OntologyImportPreviewRequest):
    ontology_id: int = Field(ge=1)
    resolutions: list[OntologyImportResolution] = Field(default_factory=list)


class OntologyImportResult(BaseModel):
    ontology_id: int
    root_iri: str | None = None
    added_resource_ids: list[int] = Field(default_factory=list)
    skipped_iris: list[str] = Field(default_factory=list)
    triple_count: int
