"""统一响应封装。

所有 JSON 接口（文件下载等二进制响应除外）统一返回外壳：

.. code-block:: json

    { "code": "KG.OK", "message": "OK", "data": { "...业务数据..." } }

失败时结构与成功一致，只是 ``code`` 为具体错误码、``data`` 为 ``null``，
并附带供前端 i18n 占位替换的 ``params``：

.. code-block:: json

    { "code": "KG.REVISION_CONFLICT", "message": "...", "params": {}, "data": null }

路由只需把 ``response_model=X`` 改成 ``response_model=ApiResponse[X]``，
返回值无需改动：``_wrap_payload`` 会把裸数据自动塞进 ``data``。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator

OK_CODE = "KG.OK"
OK_MESSAGE = "OK"


class ApiResponse[T](BaseModel):
    """统一成功响应外壳：code + message + data。"""

    code: str = Field(default=OK_CODE, description="业务状态码，成功固定为 KG.OK")
    message: str = Field(
        default=OK_MESSAGE, description="兜底英文消息，界面一律按 code 走 i18n"
    )
    data: T | None = Field(default=None, description="业务数据；无数据时为 null")

    @model_validator(mode="before")
    @classmethod
    def _wrap_payload(cls, value: Any) -> Any:
        """允许路由直接返回裸数据，自动补上 code/message 外壳。"""
        if isinstance(value, dict) and "code" in value and "data" in value:
            return value
        return {"code": OK_CODE, "message": OK_MESSAGE, "data": value}


class ErrorResponse(BaseModel):
    """统一失败响应外壳，结构与成功一致，额外带 params。"""

    code: str = Field(description="错误码，如 KG.REVISION_CONFLICT")
    message: str = Field(default="", description="兜底英文消息，界面按 code 走 i18n")
    params: dict[str, Any] = Field(
        default_factory=dict, description="结构化参数，供前端 i18n 占位替换"
    )
    data: None = Field(default=None, description="失败时固定为 null")


def ok(data: Any = None, message: str = OK_MESSAGE) -> dict[str, Any]:
    """手工构造成功外壳（一般不需要，路由直接返回裸数据即可）。"""
    return {"code": OK_CODE, "message": message, "data": data}
