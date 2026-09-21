"""受限样例预览（H-22）的请求/响应模型。

样例不持久化、不入导出包、不入运行日志。凭据不出现在预览结果。
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class PreviewRequest(BaseModel):
    datasource_id: int
    table: str
    schema: str = "main"
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class PreviewColumnMeta(BaseModel):
    name: str
    type: str


class PreviewResponse(BaseModel):
    """样例预览结果。仅返回，不入库不入日志。"""

    datasource_id: int
    table: str
    schema: str
    columns: list[PreviewColumnMeta]
    rows: list[dict]
    total_returned: int
    truncated: bool
