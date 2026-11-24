"""数据源连接管理（H-20）的请求/响应模型。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, field_validator

from app.core.crypto import SENSITIVE_PARAM_KEYS


def _public_params_only(params: dict | None) -> dict | None:
    if params and any(str(name).lower() in SENSITIVE_PARAM_KEYS for name in params):
        raise ValueError("Datasource secrets belong in the credential field")
    return params


class DatasourceCreate(BaseModel):
    name: str
    kind: str  # sqlite/mysql/postgresql
    params: dict  # host/port/db_name 等
    credential: str | None = None  # 明文密码，后端加密后存

    _validate_params = field_validator("params")(_public_params_only)


class DatasourceUpdate(BaseModel):
    """连接信息更新。数据源没有版本列，连接参数按最后写入生效；
    唯一性由服务层校验（重名 409 ALREADY_EXISTS）。"""

    name: str | None = None
    params: dict | None = None
    credential: str | None = None

    _validate_params = field_validator("params")(_public_params_only)


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

    _validate_params = field_validator("params")(_public_params_only)


class TestConnectionResponse(BaseModel):
    ok: bool
    message: str = ""
    table_count: int | None = None
