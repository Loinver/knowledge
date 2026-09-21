"""统一错误异常与 FastAPI handler。

KGError 携带错误码与结构化参数；handler 把它转成
`{ code, params, message }` 响应体，message 只是兜底英文。
界面永远用 code 走 i18n，不展示 message。
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.error_codes import HTTP_STATUS, ErrorCode


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


def install_error_handler(app: FastAPI) -> None:
    """注册统一错误 handler。在 app 创建后调用一次。"""

    @app.exception_handler(KGError)
    async def _handle_kg_error(_: Request, exc: KGError) -> JSONResponse:
        status = HTTP_STATUS.get(exc.code, 400)
        return JSONResponse(
            status_code=status,
            content={
                "code": exc.code.value,
                "params": exc.params,
                "message": exc.message,
            },
        )
