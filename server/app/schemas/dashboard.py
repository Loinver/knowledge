"""工作台汇总统计的响应契约。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class DashboardStatsOut(BaseModel):
    entity_types: int = Field(ge=0)
    relation_types: int = Field(ge=0)
    domains: int = Field(ge=0)
    ontologies: int = Field(ge=0)
    datasources: int = Field(ge=0)
    mappings: int = Field(ge=0)
    runs: int = Field(ge=0)
    current_graph_id: int | None = Field(ge=1)
    result_set_count: int = Field(
        ge=0, description="All graph revisions, including history"
    )
    quarantine_count: int = Field(
        ge=0, description="Quarantine records for the current graph's run only"
    )
    unpublished_count: int = Field(
        ge=0, description="Draft entity types, relation types, domains and ontologies"
    )
