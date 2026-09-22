"""统一错误异常与 FastAPI handler。

KGError 携带错误码与结构化参数；handler 把它转成与成功响应同构的外壳
`{ code, message, params, data: null }`，message 只是兜底英文。
界面永远用 code 走 i18n，不展示 message。

除 KGError 外，FastAPI 自带的请求校验失败与 HTTPException 也统一成同一外壳，
避免出现「有的接口是外壳、有的接口是 { detail: ... }」的割裂。
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.error_codes import HTTP_STATUS, ErrorCode
from app.schemas.response import ErrorResponse

# HTTP 状态码 → 兜底错误码。用于 FastAPI/Starlette 自带异常的统一化。
STATUS_FALLBACK_CODE: dict[int, ErrorCode] = {
    400: ErrorCode.INVALID_REQUEST,
    401: ErrorCode.TOKEN_EXPIRED,
    403: ErrorCode.FORBIDDEN,
    404: ErrorCode.RESOURCE_NOT_FOUND,
    409: ErrorCode.REVISION_CONFLICT,
    422: ErrorCode.VALIDATION_VIOLATION,
    503: ErrorCode.SOURCE_UNREACHABLE,
}


class KGError(Exception):
    """领域错误。携带错误码与供前端 i18n 占位替换的结构化参数。"""

    def __init__(
        self,
        code: ErrorCode,
        params: dict[str, object] | None = None,
        message: str = "",
    ) -> None:
        self.code = code
        self.params = params or {}
        self.message = message or code.value
        super().__init__(code.value)


def _error_payload(
    code: ErrorCode | str, params: dict[str, object], message: str = ""
) -> dict[str, object]:
    return ErrorResponse(
        code=str(code),
        message=message or str(code),
        params=dict(params),
        data=None,
    ).model_dump()


def install_error_handler(app: FastAPI) -> None:
    """注册统一错误 handler。在 app 创建后调用一次。"""

    @app.exception_handler(KGError)
    async def _handle_kg_error(_: Request, exc: KGError) -> JSONResponse:
        status = HTTP_STATUS.get(exc.code, 400)
        return JSONResponse(
            status_code=status,
            content=_error_payload(exc.code, exc.params, exc.message),
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(
        _: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # 保持 FastAPI 原生的 422（请求体/参数不可处理），只把响应体换成统一外壳。
        issues = [
            {
                "field": ".".join(str(part) for part in error["loc"][1:]),
                "type": error["type"],
            }
            for error in exc.errors()
        ]
        payload = _error_payload(
            ErrorCode.INVALID_REQUEST, {"reason": "invalid_request", "issues": issues}
        )
        return JSONResponse(status_code=422, content=payload)

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http_error(
        _: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        status = exc.status_code
        code = STATUS_FALLBACK_CODE.get(status, ErrorCode.INVALID_REQUEST)
        params: dict[str, object] = {"reason": "http_error"}
        return JSONResponse(
            status_code=status, content=_error_payload(code, params, str(exc.detail))
        )
