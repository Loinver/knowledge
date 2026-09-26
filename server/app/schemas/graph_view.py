"""图谱分析（diff/path/推荐）与视图模板的请求/响应模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DiffTriple(BaseModel):
    subject: str
    predicate: str
    object: str


class GraphDiffOut(BaseModel):
    base_graph_revision_id: int
    target_graph_revision_id: int
    entities_added: list[str]
    entities_removed: list[str]
    triples_added: list[DiffTriple]
    triples_removed: list[DiffTriple]
    entity_added_count: int
    entity_removed_count: int
    triple_added_count: int
    triple_removed_count: int
    truncated: bool


class PathOut(BaseModel):
    graph_revision_id: int
    from_iri: str
    to_iri: str
    max_hops: int
    found: bool
    hops: int
    nodes: list[str]
    edge_ids: list[int]


class LayoutRecommendation(BaseModel):
    layout_id: str
    reason_key: str
    reason_params: dict[str, Any] = Field(default_factory=dict)


class GraphRecommendationOut(BaseModel):
    graph_revision_id: int
    signals: dict[str, Any]
    recommendations: list[LayoutRecommendation]


class ViewTemplateCreate(BaseModel):
    name_i18n: dict[str, str]
    layout_id: str = Field(min_length=1, max_length=64)
    config: dict = Field(default_factory=dict)
    ontology_id: int = Field(gt=0)
    ontology_revision: int = Field(gt=0)

    def model_post_init(self, __context: Any) -> None:
        if not self.name_i18n.get("zh-CN", "").strip() or set(self.name_i18n) - {
            "zh-CN",
            "en-US",
        }:
            from app.core.error_codes import ErrorCode
            from app.core.errors import KGError

            raise KGError(ErrorCode.INVALID_NAME, {"field": "name_i18n"})


class ViewTemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name_i18n: dict[str, str]
    layout_id: str
    config: dict
    ontology_id: int
    ontology_revision: int
    created_at: datetime
    updated_at: datetime
    stale: bool = False


class ViewTemplatePage(BaseModel):
    items: list[ViewTemplateOut]
    total: int
    page: int
    page_size: int
