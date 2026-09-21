"""本体装配与设计器（H-13）的请求/响应模型。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ResourceStatus


class OntologyRefAdd(BaseModel):
    """添加引用资源（域或单类型）。按 IRI 去重。"""

    resource_id: int
    pinned_revision: int | None = None


class OntologyCreate(BaseModel):
    name: str
    iri: str
    label_i18n: dict[str, str]
    definition_i18n: dict[str, str] | None = None
    template_id: int | None = None
    ref_resource_ids: list[int] = Field(default_factory=list)


class OntologyUpdate(BaseModel):
    label_i18n: dict[str, str] | None = None
    definition_i18n: dict[str, str] | None = None
    if_match: int


class OntologyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    iri: str
    label_i18n: dict[str, str] | None = None
    definition_i18n: dict[str, str] | None = None
    status: ResourceStatus
    current_revision: int
    template_id: int | None = None


class OntologyBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    iri: str
    label_i18n: dict[str, str] | None = None
    status: ResourceStatus
    current_revision: int


class OntologyRefOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    ontology_id: int
    resource_id: int
    pinned_revision: int | None = None


class CanvasLayoutUpdate(BaseModel):
    """画布布局更新。拖节点只改这里，不产生语义版本。"""

    positions: dict


class CanvasLayoutOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    scope: str
    owner_id: int
    positions: dict


class ConflictInfo(BaseModel):
    """相同资源不兼容版本冲突。"""

    resource_id: int
    resource_name: str
    existing_revision: int
    new_revision: int
