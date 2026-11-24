"""装配模板、固定资源版本与模板来源契约。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import ResourceKind


class TemplateResource(BaseModel):
    resource_id: int = Field(gt=0)
    pinned_revision: int = Field(gt=0)


class TemplateMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=128)
    label_i18n: dict[str, str]
    source: str = Field(min_length=1, max_length=128)
    basis: str = Field(min_length=1, max_length=4000)

    @field_validator("label_i18n")
    @classmethod
    def labels(cls, value: dict[str, str]) -> dict[str, str]:
        if not value.get("zh-CN", "").strip() or set(value) - {"zh-CN", "en-US"}:
            raise ValueError("zh-CN label required; supported locales are zh-CN/en-US")
        if any(not text.strip() or len(text) > 256 for text in value.values()):
            raise ValueError("labels must contain 1-256 characters")
        return {key: text.strip() for key, text in value.items()}


class TemplateCreate(TemplateMetadata):
    resources: list[TemplateResource] = Field(default_factory=list, max_length=1000)

    @field_validator("resources")
    @classmethod
    def unique_resources(cls, value: list[TemplateResource]) -> list[TemplateResource]:
        if len({item.resource_id for item in value}) != len(value):
            raise ValueError("resource IDs must be unique")
        return value


class TemplateLink(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    label_i18n: dict[str, str]
    source: str
    basis: str
    builtin: bool
    revision: int


class TemplateOut(TemplateLink):
    resources: list[TemplateResource]
    reference_count: int


class TemplatePage(BaseModel):
    items: list[TemplateOut]
    total: int
    page: int
    page_size: int


class TemplateFromOntology(TemplateMetadata):
    ontology_id: int = Field(gt=0)
    ontology_revision: int = Field(gt=0)


class TemplateInstantiate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=128)
    iri: str = Field(min_length=1, max_length=640)
    label_i18n: dict[str, str]
    definition_i18n: dict[str, str] | None = None

    @field_validator("label_i18n")
    @classmethod
    def labels(cls, value: dict[str, str]) -> dict[str, str]:
        return TemplateMetadata.labels(value)


class TemplateResourceOption(BaseModel):
    resource_id: int
    name: str
    iri: str
    kind: ResourceKind
    label_i18n: dict[str, str] | None
    revisions: list[int]


class TemplateResourcePage(BaseModel):
    items: list[TemplateResourceOption]
    total: int
    page: int
    page_size: int
