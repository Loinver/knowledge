"""认证路由（/auth/*）：注册、登录、刷新、登出、口令找回与当前用户。

事务边界在路由：领域服务只登记变更，成功与「失败但需留痕」两种情形
分别提交，见 `login` 与 `change_password`。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.v1.deps import access_token, client_ip, current_user
from app.core.config import get_settings
from app.core.db import get_session
from app.core.errors import KGError
from app.domain import account_service
from app.models.account import User
from app.schemas.account import (
    MIN_PASSWORD_LENGTH,
    AuthConfigOut,
    ForgotPasswordResult,
    LoginRequest,
    LogoutRequest,
    PasswordResetRequest,
    PasswordResetSubmit,
    RefreshRequest,
    RegisterRequest,
    TokenPair,
    UserOut,
)
from app.schemas.response import ApiResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/config", response_model=ApiResponse[AuthConfigOut])
def auth_config() -> AuthConfigOut:
    """公开配置：前端据此决定是否展示注册入口、口令长度提示。"""
    return AuthConfigOut(
        registration_enabled=get_settings().allow_public_registration,
        password_min_length=MIN_PASSWORD_LENGTH,
    )


@router.post("/register", response_model=ApiResponse[TokenPair], status_code=201)
def register(
    payload: RegisterRequest,
    request: Request,
    session: Session = Depends(get_session),
) -> TokenPair:
    """公开注册，成功即建立会话。默认关闭（`KG_ALLOW_PUBLIC_REGISTRATION=1` 打开）。"""
    _user, tokens = account_service.register(session, payload, client_ip(request))
    session.commit()
    return tokens


@router.post("/login", response_model=ApiResponse[TokenPair])
def login(
    payload: LoginRequest,
    request: Request,
    session: Session = Depends(get_session),
) -> TokenPair:
    """登录。失败也要留痕，所以异常路径同样提交一次。"""
    try:
        user = account_service.authenticate(
            session, payload.account, payload.password, client_ip(request)
        )
    except KGError:
        session.commit()
        raise
    tokens = account_service.issue_session(session, user)
    session.commit()
    return tokens


@router.post("/refresh", response_model=ApiResponse[TokenPair])
def refresh(
    payload: RefreshRequest, session: Session = Depends(get_session)
) -> TokenPair:
    """刷新访问令牌。旧刷新令牌立即失效（轮转）。"""
    tokens = account_service.refresh_session(session, payload.refresh_token)
    session.commit()
    return tokens


@router.post("/logout", response_model=ApiResponse[None])
def logout(
    request: Request,
    payload: LogoutRequest | None = None,
    token: str = Depends(access_token),
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> None:
    """登出。请求体可选：带上 `refresh_token` 才能把会话彻底吊销。"""
    account_service.logout_session(
        session,
        user,
        token,
        payload.refresh_token if payload else None,
        client_ip(request),
    )
    session.commit()


@router.post("/forgot-password", response_model=ApiResponse[ForgotPasswordResult])
def forgot_password(
    payload: PasswordResetRequest,
    request: Request,
    session: Session = Depends(get_session),
) -> ForgotPasswordResult:
    """申请重置。邮箱是否存在都返回 200，避免账号枚举。

    开发态没有邮件服务，`reset_token` 直接下发（`KG_EXPOSE_RESET_TOKEN=0` 关闭）；
    生产由后端发信，响应里只有 `null`。
    """
    settings = get_settings()
    raw = account_service.request_password_reset(
        session, payload.email, client_ip(request)
    )
    session.commit()
    if raw is None or not settings.expose_reset_token:
        return ForgotPasswordResult(reset_token=None, expires_in=0)
    return ForgotPasswordResult(
        reset_token=raw, expires_in=settings.reset_token_ttl_seconds
    )


@router.post("/reset-password", response_model=ApiResponse[None])
def reset_password(
    payload: PasswordResetSubmit,
    request: Request,
    session: Session = Depends(get_session),
) -> None:
    """凭邮件令牌重置口令。令牌一次性，用后所有会话失效。"""
    account_service.reset_password(
        session, payload.token, payload.password, client_ip(request)
    )
    session.commit()


@router.get("/me", response_model=ApiResponse[UserOut])
def me(user: User = Depends(current_user)) -> UserOut:
    """当前用户信息：布局用户区与路由守卫都依赖它。"""
    return UserOut.model_validate(user)
