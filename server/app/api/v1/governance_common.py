"""治理接口共用的错误码、请求修订号和事务会话边界。"""

from __future__ import annotations

import re
from collections.abc import Callable, Coroutine, Iterator
from typing import Any

from fastapi import Depends, Header, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.error_codes import ErrorCode
from app.core.errors import KGError


class GovernanceRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()

        async def handle(request: Request) -> Response:
            try:
                return await handler(request)
            except RequestValidationError as exc:
                issues = [
                    {
                        "field": ".".join(str(part) for part in error["loc"][1:]),
                        "type": error["type"],
                    }
                    for error in exc.errors()
                ]
                raise KGError(ErrorCode.INVALID_REQUEST, {"issues": issues}) from exc

        return handle


def governance_session(session: Session = Depends(get_session)) -> Iterator[Session]:
    try:
        yield session
    finally:
        session.close()


def required_revision(if_match: str | None = Header(None)) -> int:
    if if_match is None:
        raise KGError(ErrorCode.INVALID_REQUEST, {"reason": "if_match_required"})
    match = re.fullmatch(r'(?:"([1-9][0-9]{0,9})"|([1-9][0-9]{0,9}))', if_match)
    if match is None:
        raise KGError(ErrorCode.INVALID_REQUEST, {"reason": "invalid_if_match"})
    return int(match.group(1) or match.group(2))
