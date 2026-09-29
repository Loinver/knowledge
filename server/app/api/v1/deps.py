"""账号路由的公共依赖：取令牌、取当前用户、要求管理员、取客户端地址。

放在 `api/v1/` 而不是 `core/`：这些是 HTTP 层的东西（请求头、Request），
领域服务不感知它们，也不该被它们污染。
"""

from __future__ import annotations

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_session
from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.domain.account_service import resolve_session
from app.models.account import User
from app.models.enums import UserRole
from app.semantics.backend import SemanticBackend
from app.semantics.rdflib_backend import RdflibBackend

# auto_error=False：缺令牌时自己抛统一错误码，而不是 FastAPI 默认的 403 裸响应。
bearer_scheme = HTTPBearer(auto_error=False)


def semantic_backend() -> SemanticBackend:
    """在应用边界选择语义实现，领域服务只接收协议。"""
    return RdflibBackend()


def client_ip(request: Request) -> str | None:
    """审计与登录限流用的来源地址。

    只有配置了可信代理层数时才读 X-Forwarded-For，并取倒数第 N 段——
    那是最外层可信代理亲眼看到的地址；更靠左的段都可能由客户端伪造。
    直连部署读头部等于让客户端自报地址，限流与审计都会失效。
    """
    hops = get_settings().trusted_proxy_count
    if hops > 0:
        forwarded = [
            part.strip()
            for part in request.headers.get("x-forwarded-for", "").split(",")
            if part.strip()
        ]
        if len(forwarded) >= hops:
            return forwarded[-hops]
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


# 逻辑只读的「写形」端点：只做测试/预览，不落库。对 VIEWER 放行，否则只读角色
# 连连接测试、样例预览、规则试跑都点不了。精确匹配：compile 与 validation 语义
# 偏读但会把预览行/报告落库，/{id}/test-connection 会写状态，都不放行。
_READ_ONLY_POST_PATHS = frozenset(
    {
        "/api/v1/datasources/test-connection",
        "/api/v1/datasources/preview",
    }
)


def _is_read_only_operation(method: str, path: str) -> bool:
    if method != "POST":
        return False
    if path in _READ_ONLY_POST_PATHS:
        return True
    return path.startswith("/api/v1/governance/rules/") and path.endswith("/test")


def authorize_business_request(
    request: Request,
    token: str = Depends(access_token),
    session: Session = Depends(get_session),
) -> None:
    """Authenticate without starting the business route's transaction."""
    # SELECT 会触发 autobegin；鉴权使用独立短会话，让业务路由自行管理事务。
    with Session(bind=session.get_bind()) as auth_session:
        user = resolve_session(auth_session, token)
        if (
            request.method not in {"GET", "HEAD", "OPTIONS"}
            and user.role
            not in {
                UserRole.EDITOR,
                UserRole.ADMIN,
            }
            and not _is_read_only_operation(request.method, request.url.path)
        ):
            raise KGError(ErrorCode.FORBIDDEN, {"role": str(user.role)})
