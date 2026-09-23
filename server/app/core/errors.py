"""不依赖 Web 框架的领域错误；HTTP 映射位于 app.api.errors。"""

from __future__ import annotations

from app.core.error_codes import ErrorCode


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
