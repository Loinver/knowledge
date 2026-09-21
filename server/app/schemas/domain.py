"""业务域管理（H-10）的请求/响应模型。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ResourceStatus


class DomainMemberAdd(BaseModel):
    """添加成员。as_ref=True 表示跨域引用。"""

    resource_id: int
    as_ref: bool = False
    owner_domain_id: int | None = None


class DomainMemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    domain_id: int
    resource_id: int
    as_ref: bool
    owner_domain_id: int | None = None


class DomainCreate(BaseModel):
    name: str
    iri: str
    label_i18n: dict[str, str]
    definition_i18n: dict[str, str] | None = None
    member_ids: list[int] = Field(default_factory=list)


class DomainUpdate(BaseModel):
    label_i18n: dict[str, str] | None = None
    definition_i18n: dict[str, str] | None = None
    if_match: int


class DomainOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    iri: str
    label_i18n: dict[str, str] | None = None
    definition_i18n: dict[str, str] | None = None
    status: ResourceStatus
    current_revision: int


class DomainBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    iri: str
    label_i18n: dict[str, str] | None = None
    status: ResourceStatus
    current_revision: int


class PublishCheckResult(BaseModel):
    """发布前检查结果。"""

    member_exists: bool
    versions_available: bool
    dependencies_complete: bool
    no_circular_ref: bool
    can_publish: bool
    issues: list[str] = Field(default_factory=list)
