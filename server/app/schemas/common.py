"""Pydantic v2 请求/响应模型。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class NamespaceCreate(BaseModel):
    prefix: str
    iri: str
    protected: bool = False
    label_i18n: dict[str, str] | None = None


class NamespaceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    prefix: str
    iri: str
    protected: bool
    label_i18n: dict[str, str] | None = None


class IriBuildRequest(BaseModel):
    namespace: str
    name: str


class IriBuildResponse(BaseModel):
    iri: str


class IriValidateResponse(BaseModel):
    name: bool
    namespace: bool


class ImpactItem(BaseModel):
    source_id: int
    role: str
    ref_id: int


class ImpactResponse(BaseModel):
    resource_id: int
    references: list[ImpactItem]
