"""在 HTTP 边界把领域异常和框架异常映射为统一错误响应。"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.error_codes import HTTP_STATUS, ErrorCode
from app.core.errors import KGError
from app.schemas.response import ErrorResponse

STATUS_FALLBACK_CODE: dict[int, ErrorCode] = {
    400: ErrorCode.INVALID_REQUEST,
    401: ErrorCode.TOKEN_EXPIRED,
    403: ErrorCode.FORBIDDEN,
    404: ErrorCode.RESOURCE_NOT_FOUND,
    409: ErrorCode.REVISION_CONFLICT,
    422: ErrorCode.VALIDATION_VIOLATION,
    503: ErrorCode.SOURCE_UNREACHABLE,
}


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
        return JSONResponse(
            status_code=HTTP_STATUS.get(exc.code, 400),
            content=_error_payload(exc.code, exc.params, exc.message),
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(
        _: Request, exc: RequestValidationError
    ) -> JSONResponse:
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
        code = STATUS_FALLBACK_CODE.get(exc.status_code, ErrorCode.INVALID_REQUEST)
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_payload(code, {"reason": "http_error"}, str(exc.detail)),
            headers=exc.headers,
        )

    @app.exception_handler(SQLAlchemyError)
    async def _handle_database_error(_: Request, exc: SQLAlchemyError) -> JSONResponse:
        """元数据库异常单独成码。

        最常见的是本地库结构落后于代码（未执行 Alembic 迁移），查询直接报
        `no such column: xxx`。如果落到下面的兜底 handler，前端只能显示
        「服务端内部错误」，看不出该做什么；这里给出可执行的提示。
        原始异常仍由 Starlette 记录，响应体里不带 SQL 细节。
        """
        return JSONResponse(
            status_code=503,
            content=_error_payload(
                ErrorCode.DATABASE_ERROR,
                {"reason": type(exc).__name__},
            ),
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected(_: Request, exc: Exception) -> JSONResponse:
        """兜底：未预期异常也要返回统一外壳。

        没有这一层时，FastAPI 会由 Starlette 的 ServerErrorMiddleware 直接吐
        纯文本 `Internal Server Error`，前端拿不到 `code`，错误翻译层只能把
        axios 自己的 code（如 `ERR_BAD_RESPONSE`）当业务码显示出来。
        原始异常仍由 Starlette 记录到日志，这里只负责把响应体统一成外壳。
        """
        return JSONResponse(
            status_code=500,
            content=_error_payload(
                ErrorCode.INTERNAL_ERROR, {"reason": "internal_error"}
            ),
        )
