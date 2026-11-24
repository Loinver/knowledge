"""AI 建议（第三批）的请求/响应模型。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DocumentExtractRequest(BaseModel):
    ontology_id: int = Field(gt=0)
    text: str = Field(min_length=1, max_length=200_000)


class AiSuggestionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    kind: str
    target_id: int
    status: str
    title: str
    payload: dict
    explanation: str
    created_at: datetime
    resolved_at: datetime | None


class AiSuggestionPage(BaseModel):
    items: list[AiSuggestionOut]
    total: int
