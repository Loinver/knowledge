"""账号路由的公共依赖：取令牌、取当前用户、要求管理员、取客户端地址。

放在 `api/v1/` 而不是 `core/`：这些是 HTTP 层的东西（请求头、Request），
领域服务不感知它们，也不该被它们污染。
"""

from __future__ import annotations

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.domain.account_service import resolve_session
from app.models.account import User
from app.models.enums import UserRole

# auto_error=False：缺令牌时自己抛统一错误码，而不是 FastAPI 默认的 403 裸响应。
bearer_scheme = HTTPBearer(auto_error=False)


def client_ip(request: Request) -> str | None:
    """审计用的来源地址。经反向代理时取 X-Forwarded-For 的第一段。"""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip() or None
    return request.client.host if request.client else None


def access_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> str:
    """取出裸访问令牌。登出与改密需要它来定位当前会话。"""
    if credentials is None or not credentials.credentials:
        raise KGError(ErrorCode.TOKEN_EXPIRED, {"reason": "missing_token"})
    return credentials.credentials


def current_user(
    token: str = Depends(access_token),
    session: Session = Depends(get_session),
) -> User:
    """当前登录用户。令牌无效、过期或账号被禁用都按未认证处理。"""
    return resolve_session(session, token)


def require_admin(user: User = Depends(current_user)) -> User:
    """系统管理接口的访问控制。"""
    if user.role != UserRole.ADMIN:
        raise KGError(ErrorCode.FORBIDDEN, {"role": str(user.role)})
    return user
