"""数据源连接管理（H-20）的请求/响应模型。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class DatasourceCreate(BaseModel):
    name: str
    kind: str  # sqlite/mysql/postgresql
    params: dict  # host/port/db_name 等
    credential: str | None = None  # 明文密码，后端加密后存


class DatasourceUpdate(BaseModel):
    name: str | None = None
    params: dict | None = None
    credential: str | None = None
    if_match: int


class DatasourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    kind: str
    params: dict  # 已脱敏，凭据字段是 ***
    status: str


class DatasourceBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    kind: str
    status: str


class TestConnectionRequest(BaseModel):
    kind: str
    params: dict
    credential: str | None = None


class TestConnectionResponse(BaseModel):
    ok: bool
    message: str = ""
    table_count: int | None = None
