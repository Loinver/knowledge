"""账号领域服务：口令、会话令牌、用户管理与审计留痕。

设计取舍（完整理由见 `docs/adr/0002-account-auth.md`）：

- **口令**用标准库 `hashlib.pbkdf2_hmac` 派生，每次独立随机盐，格式
  ``pbkdf2_sha256$<iterations>$<salt_b64>$<digest_b64>``。不引入
  bcrypt/argon2：多一个需要编译或 wheel 可用的依赖，收益有限。
- **会话令牌是不透明随机串**，库里只存 sha256 摘要。因此登出可以即时吊销、
  刷新可以轮转，也不需要 JWT 签名密钥与随之而来的密钥轮换问题。
- 时间一律按 UTC 存取。SQLite 读回的是 naive，比较前用 `_as_utc` 归一，
  否则 `naive <= aware` 会直接抛 TypeError。
- 审计只记动作码与非敏感对象名，**失败也记**——登录失败是安全信号。

本模块不导入 FastAPI，不自行 `commit`：事务边界由路由持有。
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from base64 import urlsafe_b64decode, urlsafe_b64encode
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.models.account import AuditLog, AuthToken, PasswordResetToken, User
from app.models.enums import (
    AuditAction,
    AuditResult,
    AuthTokenKind,
    UserRole,
    UserStatus,
)
from app.schemas.account import (
    MIN_PASSWORD_LENGTH,
    PasswordChange,
    ProfileUpdate,
    RegisterRequest,
    TokenPair,
    UserCreate,
    UserPatch,
)

PBKDF2_SCHEME = "pbkdf2_sha256"
PBKDF2_ALGORITHM = "sha256"
SALT_BYTES = 16
# 不透明令牌的熵：32 字节随机 → 43 字符 URL 安全串
TOKEN_BYTES = 32
# 审计表的 ip 列宽，兼容 IPv6
IP_MAX_LENGTH = 45


# ---------------------------------------------------------------------------
# 口令派生
# ---------------------------------------------------------------------------


def hash_password(plaintext: str) -> str:
    """派生口令。返回可直接落库的自描述字符串。"""
    iterations = get_settings().password_iterations
    salt = secrets.token_bytes(SALT_BYTES)
    digest = hashlib.pbkdf2_hmac(PBKDF2_ALGORITHM, plaintext.encode(), salt, iterations)
    return "$".join(
        (
            PBKDF2_SCHEME,
            str(iterations),
            urlsafe_b64encode(salt).decode(),
            urlsafe_b64encode(digest).decode(),
        )
    )


def verify_password(plaintext: str, stored: str) -> bool:
    """校验口令。存储值格式非法时一律判失败，不抛异常。"""
    parts = stored.split("$")
    if len(parts) != 4:
        return False
    scheme, iterations_text, salt_text, digest_text = parts
    if scheme != PBKDF2_SCHEME or not iterations_text.isdigit():
        return False
    try:
        salt = urlsafe_b64decode(salt_text.encode())
        expected = urlsafe_b64decode(digest_text.encode())
    except ValueError:
        return False
    actual = hashlib.pbkdf2_hmac(
        PBKDF2_ALGORITHM, plaintext.encode(), salt, int(iterations_text)
    )
    return hmac.compare_digest(actual, expected)


def _validate_password(plaintext: str) -> None:
    """强度校验。

    只做长度下限：上限由 Pydantic 拦住（避免超长输入拖慢派生），
    更复杂的组成规则收益有限且容易把用户逼去写便利贴。
    """
    if len(plaintext) < MIN_PASSWORD_LENGTH:
        raise KGError(ErrorCode.WEAK_PASSWORD, {"min_length": MIN_PASSWORD_LENGTH})


# ---------------------------------------------------------------------------
# 时间与令牌
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(UTC)


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _hash_token(raw: str) -> str:
    """令牌摘要。库里只存这个值，泄库也无法直接冒用。"""
    return hashlib.sha256(raw.encode()).hexdigest()


def _issue_token(
    session: Session, user: User, kind: AuthTokenKind, ttl_seconds: int
) -> str:
    raw = secrets.token_urlsafe(TOKEN_BYTES)
    session.add(
        AuthToken(
            user_id=user.id,
            token_hash=_hash_token(raw),
            kind=kind,
            expires_at=_now() + timedelta(seconds=ttl_seconds),
        )
    )
    return raw


def issue_session(session: Session, user: User) -> TokenPair:
    """签发一对令牌。登录、注册、刷新都走这里。"""
    settings = get_settings()
    access = _issue_token(
        session, user, AuthTokenKind.ACCESS, settings.access_token_ttl_seconds
    )
    refresh = _issue_token(
        session, user, AuthTokenKind.REFRESH, settings.refresh_token_ttl_seconds
    )
    return TokenPair(
        access_token=access,
        refresh_token=refresh,
        expires_in=settings.access_token_ttl_seconds,
    )


def _load_token(session: Session, raw: str, kind: AuthTokenKind) -> AuthToken:
    """取出有效令牌记录。过期、已吊销、不存在统一按登录过期处理。"""
    record = session.scalar(
        select(AuthToken).where(
            AuthToken.token_hash == _hash_token(raw), AuthToken.kind == kind
        )
    )
    if record is None or record.revoked_at is not None:
        raise KGError(ErrorCode.TOKEN_EXPIRED, {"reason": "token_invalid"})
    if _as_utc(record.expires_at) <= _now():
        raise KGError(ErrorCode.TOKEN_EXPIRED, {"reason": "token_expired"})
    return record


def _revoke_tokens(
    session: Session, user_id: str, keep_hash: str | None = None
) -> None:
    """吊销某用户的令牌；`keep_hash` 用于改密时保留当前会话。"""
    now = _now()
    for record in session.scalars(
        select(AuthToken).where(AuthToken.user_id == user_id)
    ):
        if record.revoked_at is not None or record.token_hash == keep_hash:
            continue
        record.revoked_at = now


# ---------------------------------------------------------------------------
# 审计
# ---------------------------------------------------------------------------


def record_audit(
    session: Session,
    action: AuditAction,
    actor: str,
    result: AuditResult,
    *,
    actor_id: str | None = None,
    target: str | None = None,
    ip: str | None = None,
) -> AuditLog:
    """登记一条审计。调用方负责提交事务。"""
    entry = AuditLog(
        actor_id=actor_id,
        actor=actor[:32],
        action=str(action),
        target=target[:64] if target else None,
        result=str(result),
        ip=ip[:IP_MAX_LENGTH] if ip else None,
    )
    session.add(entry)
    return entry


# ---------------------------------------------------------------------------
# 用户查找
# ---------------------------------------------------------------------------


def get_user(session: Session, user_id: str) -> User:
    user = session.get(User, user_id)
    if user is None:
        raise KGError(ErrorCode.RESOURCE_NOT_FOUND, {"id": user_id})
    return user


def _find_user_by_account(session: Session, account: str) -> User | None:
    """按用户名或邮箱查找。两者都不区分大小写，避免「Admin 与 admin 各一个」。"""
    needle = account.strip().lower()
    if not needle:
        return None
    return session.scalar(
        select(User).where(
            or_(
                func.lower(User.username) == needle,
                User.email == needle,
            )
        )
    )


def _ensure_identity_available(session: Session, username: str, email: str) -> None:
    if session.scalar(
        select(User.id).where(func.lower(User.username) == username.strip().lower())
    ):
        raise KGError(ErrorCode.USERNAME_TAKEN, {"username": username})
    if session.scalar(select(User.id).where(User.email == email.strip().lower())):
        raise KGError(ErrorCode.EMAIL_TAKEN, {"email": email})


# ---------------------------------------------------------------------------
# 认证
# ---------------------------------------------------------------------------


def register(
    session: Session, payload: RegisterRequest, ip: str | None
) -> tuple[User, TokenPair]:
    """公开注册。开关关闭时直接拒绝，注册即建立会话。"""
    if not get_settings().allow_public_registration:
        raise KGError(ErrorCode.REGISTRATION_CLOSED)
    user = _create_user(
        session,
        username=payload.username,
        email=payload.email,
        password=payload.password,
        role=UserRole.VIEWER,
        display_name=payload.display_name,
    )
    record_audit(
        session,
        AuditAction.REGISTER,
        user.username,
        AuditResult.OK,
        actor_id=user.id,
        ip=ip,
    )
    return user, issue_session(session, user)


def create_user(
    session: Session, actor: User, payload: UserCreate, ip: str | None
) -> User:
    """管理员建号。"""
    user = _create_user(
        session,
        username=payload.username,
        email=payload.email,
        password=payload.password,
        role=payload.role,
        display_name=payload.display_name,
    )
    record_audit(
        session,
        AuditAction.REGISTER,
        actor.username,
        AuditResult.OK,
        actor_id=actor.id,
        target=user.username,
        ip=ip,
    )
    return user


def _create_user(
    session: Session,
    *,
    username: str,
    email: str,
    password: str,
    role: UserRole,
    display_name: str | None,
) -> User:
    normalized_username = username.strip()
    normalized_email = email.strip().lower()
    _validate_password(password)
    _ensure_identity_available(session, normalized_username, normalized_email)
    user = User(
        username=normalized_username,
        email=normalized_email,
        password_hash=hash_password(password),
        role=role,
        display_name=display_name,
    )
    session.add(user)
    session.flush()
    return user


def bootstrap_admin(
    session: Session,
    *,
    username: str,
    email: str,
    password: str,
    display_name: str | None = None,
) -> User:
    """创建首个管理员，供 `scripts/seed_admin.py` 使用。

    库里已有账号时拒绝执行：否则这个函数就成了任何人都能调用的提权入口。
    """
    if session.scalar(select(func.count()).select_from(User)):
        raise KGError(ErrorCode.ALREADY_EXISTS, {"reason": "users_exist"})
    return _create_user(
        session,
        username=username,
        email=email,
        password=password,
        role=UserRole.ADMIN,
        display_name=display_name,
    )


def _failed_login_count(session: Session, since: datetime, *conditions: Any) -> int:
    return (
        session.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(
                AuditLog.action == str(AuditAction.LOGIN),
                AuditLog.result == str(AuditResult.FAILED),
                AuditLog.created_at >= since,
                *conditions,
            )
        )
        or 0
    )


def _ensure_login_allowed(
    session: Session, user: User | None, account_key: str, ip: str | None
) -> None:
    """按审计表里的失败记录限流，多进程部署也共享同一份计数。

    计数维度是「账号 + 来源」与「来源」，不单独按账号锁定：
    否则任何人都能反复输错，把指定用户锁在门外。被拦下的尝试
    不校验口令、也不再记失败，避免攻击者自己把窗口一直续上。
    """
    settings = get_settings()
    window = timedelta(seconds=settings.login_failure_window_seconds)
    since = _now() - window
    if user is not None:
        # 成功登录后重新计数，免得偶尔输错的用户被历史失败拖累
        last_ok = session.scalar(
            select(func.max(AuditLog.created_at)).where(
                AuditLog.action == str(AuditAction.LOGIN),
                AuditLog.result == str(AuditResult.OK),
                AuditLog.actor_id == user.id,
            )
        )
        if last_ok is not None and _as_utc(last_ok) > since:
            since = _as_utc(last_ok)
        account_condition = AuditLog.actor_id == user.id
    else:
        account_condition = and_(
            AuditLog.actor_id.is_(None), AuditLog.actor == account_key
        )
    ip_condition = AuditLog.ip.is_(None) if ip is None else AuditLog.ip == ip

    blocked = (
        _failed_login_count(session, since, account_condition, ip_condition)
        >= settings.login_max_failures_per_account
    )
    if not blocked and ip is not None:
        blocked = (
            _failed_login_count(session, _now() - window, ip_condition)
            >= settings.login_max_failures_per_ip
        )
    if blocked:
        seconds = settings.login_failure_window_seconds
        raise KGError(
            ErrorCode.TOO_MANY_ATTEMPTS,
            {"retry_after": seconds, "retry_after_minutes": -(-seconds // 60)},
        )


def authenticate(session: Session, account: str, password: str, ip: str | None) -> User:
    """口令认证。

    「账号不存在」与「口令错误」返回同一个码，且都记一条失败审计，
    不给出可用于枚举账号的差异。失败过多时先限流，再谈口令。
    """
    user = _find_user_by_account(session, account)
    account_key = (account.strip() or "-")[:32]
    _ensure_login_allowed(session, user, account_key, ip)
    if user is None:
        record_audit(
            session,
            AuditAction.LOGIN,
            account_key,
            AuditResult.FAILED,
            ip=ip,
        )
        raise KGError(ErrorCode.INVALID_CREDENTIALS)
    if not verify_password(password, user.password_hash):
        record_audit(
            session,
            AuditAction.LOGIN,
            user.username,
            AuditResult.FAILED,
            actor_id=user.id,
            ip=ip,
        )
        raise KGError(ErrorCode.INVALID_CREDENTIALS)
    if user.status != UserStatus.ACTIVE:
        record_audit(
            session,
            AuditAction.LOGIN,
            user.username,
            AuditResult.FAILED,
            actor_id=user.id,
            ip=ip,
        )
        raise KGError(ErrorCode.USER_DISABLED, {"username": user.username})
    user.last_login_at = _now()
    record_audit(
        session,
        AuditAction.LOGIN,
        user.username,
        AuditResult.OK,
        actor_id=user.id,
        ip=ip,
    )
    return user


def resolve_session(session: Session, raw_access_token: str) -> User:
    """把访问令牌换成当前用户。令牌无效或被禁用都按未认证处理。"""
    record = _load_token(session, raw_access_token, AuthTokenKind.ACCESS)
    user = session.get(User, record.user_id)
    if user is None:
        raise KGError(ErrorCode.TOKEN_EXPIRED, {"reason": "user_missing"})
    if user.status != UserStatus.ACTIVE:
        raise KGError(ErrorCode.USER_DISABLED, {"username": user.username})
    return user


def refresh_session(session: Session, raw_refresh_token: str) -> TokenPair:
    """刷新访问令牌，并轮转刷新令牌：旧的立即失效，用过的不能再用。"""
    record = _load_token(session, raw_refresh_token, AuthTokenKind.REFRESH)
    user = session.get(User, record.user_id)
    if user is None:
        raise KGError(ErrorCode.TOKEN_EXPIRED, {"reason": "user_missing"})
    if user.status != UserStatus.ACTIVE:
        raise KGError(ErrorCode.USER_DISABLED, {"username": user.username})
    record.revoked_at = _now()
    return issue_session(session, user)


def logout_session(
    session: Session,
    user: User,
    raw_access_token: str,
    raw_refresh_token: str | None,
    ip: str | None,
) -> None:
    """吊销本次会话。刷新令牌给了就一并吊销，避免只登出一半。"""
    for raw, kind in (
        (raw_access_token, AuthTokenKind.ACCESS),
        (raw_refresh_token, AuthTokenKind.REFRESH),
    ):
        if not raw:
            continue
        record = session.scalar(
            select(AuthToken).where(
                AuthToken.token_hash == _hash_token(raw), AuthToken.kind == kind
            )
        )
        if record is not None and record.revoked_at is None:
            record.revoked_at = _now()
    record_audit(
        session,
        AuditAction.LOGOUT,
        user.username,
        AuditResult.OK,
        actor_id=user.id,
        ip=ip,
    )


# ---------------------------------------------------------------------------
# 口令找回
# ---------------------------------------------------------------------------


def _issue_reset_token(session: Session, user: User) -> str:
    raw = secrets.token_urlsafe(TOKEN_BYTES)
    session.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=_hash_token(raw),
            expires_at=_now()
            + timedelta(seconds=get_settings().reset_token_ttl_seconds),
        )
    )
    return raw


def request_password_reset(session: Session, email: str, ip: str | None) -> str | None:
    """登记重置申请，返回原始令牌（由路由决定是否下发给前端）。

    邮箱不存在时返回 None 且不报错：调用方无法据此判断账号是否存在。
    """
    user = session.scalar(select(User).where(User.email == email.strip().lower()))
    if user is None or user.status != UserStatus.ACTIVE:
        return None
    raw = _issue_reset_token(session, user)
    record_audit(
        session,
        AuditAction.RESET_REQUESTED,
        user.username,
        AuditResult.OK,
        actor_id=user.id,
        ip=ip,
    )
    return raw


def issue_reset_for_user(
    session: Session, actor: User, user_id: str, ip: str | None
) -> str:
    """管理员为他人签发一次性重置令牌，由管理员线下转交。

    没有邮件服务时，这是用户忘记口令后唯一的恢复途径。管理员拿到的
    只是一次性链接而不是口令本身，用户重置后所有旧会话随之失效。
    """
    target = get_user(session, user_id)
    if target.id == actor.id:
        # 自己的口令走「账号安全」改密，需要旧口令，不开这个旁路
        raise KGError(ErrorCode.FORBIDDEN, {"reason": "self_reset"})
    if target.status != UserStatus.ACTIVE:
        raise KGError(ErrorCode.USER_DISABLED, {"username": target.username})
    raw = _issue_reset_token(session, target)
    record_audit(
        session,
        AuditAction.RESET_REQUESTED,
        actor.username,
        AuditResult.OK,
        actor_id=actor.id,
        target=target.username,
        ip=ip,
    )
    return raw


def reset_password(
    session: Session, token: str, new_password: str, ip: str | None
) -> User:
    """凭邮件令牌改密。令牌一次性，改密后所有会话失效。"""
    record = session.scalar(
        select(PasswordResetToken).where(
            PasswordResetToken.token_hash == _hash_token(token)
        )
    )
    if record is None or record.used_at is not None:
        raise KGError(ErrorCode.RESET_TOKEN_INVALID)
    if _as_utc(record.expires_at) <= _now():
        raise KGError(ErrorCode.RESET_TOKEN_INVALID, {"reason": "expired"})
    user = session.get(User, record.user_id)
    if user is None or user.status != UserStatus.ACTIVE:
        raise KGError(ErrorCode.RESET_TOKEN_INVALID)
    _validate_password(new_password)
    record.used_at = _now()
    user.password_hash = hash_password(new_password)
    _revoke_tokens(session, user.id)
    record_audit(
        session,
        AuditAction.PASSWORD_RESET,
        user.username,
        AuditResult.OK,
        actor_id=user.id,
        ip=ip,
    )
    return user


# ---------------------------------------------------------------------------
# 资料与口令维护
# ---------------------------------------------------------------------------


def update_profile(
    session: Session, user: User, payload: ProfileUpdate, ip: str | None
) -> User:
    """更新个人资料。只覆盖显式传入的字段。"""
    changes = payload.model_dump(exclude_unset=True)
    if "display_name" in changes:
        user.display_name = changes["display_name"]
    if "avatar_url" in changes:
        user.avatar_url = changes["avatar_url"]
    record_audit(
        session,
        AuditAction.PROFILE_UPDATED,
        user.username,
        AuditResult.OK,
        actor_id=user.id,
        ip=ip,
    )
    return user


def change_password(
    session: Session,
    user: User,
    payload: PasswordChange,
    raw_access_token: str,
    ip: str | None,
) -> None:
    """改密。需要旧口令；当前会话保留，其他会话全部失效。"""
    if not verify_password(payload.old_password, user.password_hash):
        record_audit(
            session,
            AuditAction.PASSWORD_CHANGED,
            user.username,
            AuditResult.FAILED,
            actor_id=user.id,
            ip=ip,
        )
        raise KGError(ErrorCode.OLD_PASSWORD_INVALID)
    _validate_password(payload.new_password)
    user.password_hash = hash_password(payload.new_password)
    _revoke_tokens(session, user.id, keep_hash=_hash_token(raw_access_token))
    record_audit(
        session,
        AuditAction.PASSWORD_CHANGED,
        user.username,
        AuditResult.OK,
        actor_id=user.id,
        ip=ip,
    )


# ---------------------------------------------------------------------------
# 系统管理
# ---------------------------------------------------------------------------


def list_users(
    session: Session,
    *,
    q: str,
    role: UserRole | None,
    status: UserStatus | None,
    page: int,
    page_size: int,
) -> tuple[list[User], int]:
    conditions = []
    keyword = q.strip().lower()
    if keyword:
        conditions.append(
            or_(
                func.lower(User.username).contains(keyword),
                User.email.contains(keyword),
                func.lower(func.coalesce(User.display_name, "")).contains(keyword),
            )
        )
    if role is not None:
        conditions.append(User.role == role)
    if status is not None:
        conditions.append(User.status == status)

    total = (
        session.scalar(select(func.count()).select_from(User).where(*conditions)) or 0
    )
    items = list(
        session.scalars(
            select(User)
            .where(*conditions)
            .order_by(User.created_at.desc(), User.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return items, total


def patch_user(
    session: Session, actor: User, user_id: str, payload: UserPatch, ip: str | None
) -> User:
    """管理员改角色或状态。

    不允许管理员把自己降级或禁用：一旦最后一个管理员自锁，系统再没有
    任何界面入口能恢复，只能改库。
    """
    target = get_user(session, user_id)
    if target.id == actor.id:
        if payload.role is not None and payload.role != UserRole.ADMIN:
            raise KGError(ErrorCode.FORBIDDEN, {"reason": "self_demote"})
        if payload.status is not None and payload.status != UserStatus.ACTIVE:
            raise KGError(ErrorCode.FORBIDDEN, {"reason": "self_disable"})

    if payload.role is not None and payload.role != target.role:
        target.role = payload.role
        record_audit(
            session,
            AuditAction.ROLE_CHANGED,
            actor.username,
            AuditResult.OK,
            actor_id=actor.id,
            target=target.username,
            ip=ip,
        )
    if payload.status is not None and payload.status != target.status:
        target.status = payload.status
        if target.status != UserStatus.ACTIVE:
            # 禁用即踢下线，否则已签发的令牌还能继续用
            _revoke_tokens(session, target.id)
        record_audit(
            session,
            AuditAction.STATUS_CHANGED,
            actor.username,
            AuditResult.OK,
            actor_id=actor.id,
            target=target.username,
            ip=ip,
        )
    return target


def list_roles(session: Session) -> list[tuple[UserRole, int]]:
    """角色与成员数。角色名与说明由前端 i18n 渲染，后端不下发文案。"""
    rows = session.execute(select(User.role, func.count()).group_by(User.role)).all()
    counts: dict[UserRole, int] = {role: int(total) for role, total in rows}
    return [(role, counts.get(role, 0)) for role in UserRole]


def list_audit_logs(
    session: Session,
    *,
    q: str,
    action: AuditAction | None,
    page: int,
    page_size: int,
) -> tuple[list[AuditLog], int]:
    conditions = []
    keyword = q.strip().lower()
    if keyword:
        conditions.append(
            or_(
                func.lower(AuditLog.actor).contains(keyword),
                func.lower(func.coalesce(AuditLog.target, "")).contains(keyword),
            )
        )
    if action is not None:
        conditions.append(AuditLog.action == str(action))

    total = (
        session.scalar(select(func.count()).select_from(AuditLog).where(*conditions))
        or 0
    )
    items = list(
        session.scalars(
            select(AuditLog)
            .where(*conditions)
            .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return items, total
