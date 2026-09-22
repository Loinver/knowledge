"""账号体系传输契约（账号、会话令牌、用户管理、审计日志）。

与前端 `web/src/api/auth.ts` 一一对应，契约说明见
`docs/frontend-redesign-plan.zh-CN.md` 第 3 节。

两条硬规则在这里落地：

- 只传枚举码与错误码，不传中文（角色名、角色说明由前端 i18n 渲染，
  所以 `RoleOut` 只有 `code` 与 `member_count`，没有 `name_i18n`）。
- 口令强度不放在 Pydantic 的 `min_length` 上：那样只会得到泛化的
  `KG.INVALID_REQUEST`，而前端需要 `AUTH.WEAK_PASSWORD` 才能给出
  「密码至少 8 位」的具体提示。强度由领域服务判定。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from app.models.enums import AuditAction, AuditResult, UserRole, UserStatus

# 与前端注册页的校验规则保持一致（web/src/views/auth/Register.vue）。
USERNAME_PATTERN = r"^[A-Za-z0-9_]{3,32}$"
EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$"
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128


def _as_utc(value: datetime) -> datetime:
    """SQLite 读回的时间是 naive，序列化前补上 UTC 偏移。

    不补的话前端拿到的是不带时区的字符串，`new Date()` 会按本地时区解释，
    东八区用户看到的操作时间会差 8 小时。
    """
    return value if value.tzinfo else value.replace(tzinfo=UTC)


UtcDatetime = Annotated[datetime, AfterValidator(_as_utc)]


# ---------------------------------------------------------------------------
# 认证与会话
# ---------------------------------------------------------------------------


class RegisterRequest(BaseModel):
    """公开注册。默认关闭，仅在 `KG_ALLOW_PUBLIC_REGISTRATION=1` 时可用。"""

    username: str = Field(pattern=USERNAME_PATTERN)
    email: str = Field(pattern=EMAIL_PATTERN)
    password: str = Field(max_length=MAX_PASSWORD_LENGTH)
    display_name: str | None = Field(default=None, max_length=64)


class LoginRequest(BaseModel):
    """登录。`account` 同时接受用户名与邮箱。"""

    account: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class LogoutRequest(BaseModel):
    """登出。带上刷新令牌才能把会话彻底吊销，只给访问令牌则只失效当前凭据。"""

    refresh_token: str | None = None


class TokenPair(BaseModel):
    """登录、注册、刷新统一返回双令牌。`expires_in` 是访问令牌剩余秒数。"""

    access_token: str
    refresh_token: str
    expires_in: int


class AuthConfigOut(BaseModel):
    """公开的认证配置：前端据此决定是否展示注册入口。"""

    registration_enabled: bool
    password_min_length: int


# ---------------------------------------------------------------------------
# 用户与资料
# ---------------------------------------------------------------------------


class UserOut(BaseModel):
    """账号对外形态。`password_hash` 永不出现。"""

    model_config = ConfigDict(from_attributes=True)

    id: str
    username: str
    email: str
    role: UserRole
    status: UserStatus
    display_name: str | None = None
    avatar_url: str | None = None
    last_login_at: UtcDatetime | None = None


class UserCreate(BaseModel):
    """管理员建号。角色由管理员指定，注册开关不影响这条路径。"""

    username: str = Field(pattern=USERNAME_PATTERN)
    email: str = Field(pattern=EMAIL_PATTERN)
    password: str = Field(max_length=MAX_PASSWORD_LENGTH)
    role: UserRole = UserRole.VIEWER
    display_name: str | None = Field(default=None, max_length=64)


class UserPatch(BaseModel):
    """管理员改角色或状态。字段缺省表示不改，显式 null 非法。"""

    role: UserRole | None = None
    status: UserStatus | None = None


class ProfileUpdate(BaseModel):
    """个人中心资料。用 `exclude_unset` 区分「没传」与「传了 null」。"""

    display_name: str | None = Field(default=None, max_length=64)
    avatar_url: str | None = Field(default=None, max_length=512)


class PasswordChange(BaseModel):
    old_password: str = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)
    new_password: str = Field(max_length=MAX_PASSWORD_LENGTH)


class PasswordResetRequest(BaseModel):
    email: str = Field(min_length=1, max_length=254)


class PasswordResetSubmit(BaseModel):
    token: str = Field(min_length=1)
    password: str = Field(max_length=MAX_PASSWORD_LENGTH)


class ForgotPasswordResult(BaseModel):
    """重置申请结果。

    无论邮箱是否存在都返回 200，避免账号枚举；`reset_token` 仅在
    开发态（`KG_EXPOSE_RESET_TOKEN=1`）下发，生产由邮件送达。
    """

    reset_token: str | None = None
    expires_in: int = 0


# ---------------------------------------------------------------------------
# 系统管理
# ---------------------------------------------------------------------------


class RoleOut(BaseModel):
    """角色与成员数。角色名与说明是界面文案，由前端按 `code` 走 i18n。"""

    code: UserRole
    member_count: int


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    actor: str
    action: AuditAction
    target: str | None = None
    result: AuditResult
    ip: str | None = None
    created_at: UtcDatetime


class UserPage(BaseModel):
    items: list[UserOut]
    total: int
    page: int
    page_size: int


class AuditLogPage(BaseModel):
    items: list[AuditLogOut]
    total: int
    page: int
    page_size: int
