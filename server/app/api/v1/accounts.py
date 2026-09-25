"""账号管理路由：用户、角色与操作日志（/users、/roles、/audit-logs）。

除「自己的资料与口令」外，本模块全部端点要求管理员。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.api.v1.deps import access_token, client_ip, current_user, require_admin
from app.core.config import get_settings
from app.core.db import get_session
from app.core.errors import KGError
from app.domain import account_service
from app.models.account import User
from app.models.enums import AuditAction, UserRole, UserStatus
from app.schemas.account import (
    AuditLogOut,
    AuditLogPage,
    PasswordChange,
    PasswordResetIssued,
    ProfileUpdate,
    RoleOut,
    UserCreate,
    UserOut,
    UserPage,
    UserPatch,
)
from app.schemas.response import ApiResponse

router = APIRouter(tags=["accounts"])

PAGE_SIZE = Query(20, ge=1, le=200)


# --- 自己的资料与口令（任何登录用户） -------------------------------------


@router.get("/users/me/profile", response_model=ApiResponse[UserOut])
def read_my_profile(user: User = Depends(current_user)) -> UserOut:
    """个人中心资料。"""
    return UserOut.model_validate(user)


@router.patch("/users/me/profile", response_model=ApiResponse[UserOut])
def update_my_profile(
    payload: ProfileUpdate,
    request: Request,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> UserOut:
    """更新昵称与头像。只覆盖显式传入的字段。"""
    account_service.update_profile(session, user, payload, client_ip(request))
    session.commit()
    return UserOut.model_validate(user)


@router.put("/users/me/password", response_model=ApiResponse[None])
def change_my_password(
    payload: PasswordChange,
    request: Request,
    token: str = Depends(access_token),
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> None:
    """改密。旧口令错误同样留痕，因此异常路径也提交一次。"""
    try:
        account_service.change_password(
            session, user, payload, token, client_ip(request)
        )
    except KGError:
        session.commit()
        raise
    session.commit()


# --- 用户管理（仅管理员） -------------------------------------------------


@router.get("/users", response_model=ApiResponse[UserPage])
def list_users(
    q: str = Query(""),
    role: UserRole | None = Query(None),
    status: UserStatus | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = PAGE_SIZE,
    _admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
) -> UserPage:
    items, total = account_service.list_users(
        session, q=q, role=role, status=status, page=page, page_size=page_size
    )
    return UserPage(
        items=[UserOut.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/users", response_model=ApiResponse[UserOut], status_code=201)
def create_user(
    payload: UserCreate,
    request: Request,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
) -> UserOut:
    """管理员建号。公开注册关闭时，这是唯一的建号入口。"""
    user = account_service.create_user(session, admin, payload, client_ip(request))
    session.commit()
    return UserOut.model_validate(user)


@router.patch("/users/{user_id}", response_model=ApiResponse[UserOut])
def patch_user(
    user_id: str,
    payload: UserPatch,
    request: Request,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
) -> UserOut:
    """改角色或启停账号。管理员不能把自己降级或禁用。"""
    user = account_service.patch_user(
        session, admin, user_id, payload, client_ip(request)
    )
    session.commit()
    return UserOut.model_validate(user)


@router.post(
    "/users/{user_id}/password-reset",
    response_model=ApiResponse[PasswordResetIssued],
    status_code=201,
)
def issue_password_reset(
    user_id: str,
    request: Request,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
) -> PasswordResetIssued:
    """为他人签发一次性重置令牌。没有邮件服务时，这是找回口令的途径。"""
    token = account_service.issue_reset_for_user(
        session, admin, user_id, client_ip(request)
    )
    session.commit()
    return PasswordResetIssued(
        reset_token=token, expires_in=get_settings().reset_token_ttl_seconds
    )


# --- 角色与操作日志（仅管理员） -------------------------------------------


@router.get("/roles", response_model=ApiResponse[list[RoleOut]])
def list_roles(
    _admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
) -> list[RoleOut]:
    """角色与成员数。角色名与说明由前端按 code 走 i18n。"""
    return [
        RoleOut(code=code, member_count=count)
        for code, count in account_service.list_roles(session)
    ]


@router.get("/audit-logs", response_model=ApiResponse[AuditLogPage])
def list_audit_logs(
    q: str = Query(""),
    action: AuditAction | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = PAGE_SIZE,
    _admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
) -> AuditLogPage:
    """全局操作日志，按时间倒序。"""
    items, total = account_service.list_audit_logs(
        session, q=q, action=action, page=page, page_size=page_size
    )
    return AuditLogPage(
        items=[AuditLogOut.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )
