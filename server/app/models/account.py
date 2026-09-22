"""账号与权限数据模型。

设计取舍：

- 口令只存 PBKDF2-HMAC-SHA256 派生值，明文永不落库、不进日志、不出响应。
- 令牌是**不透明随机串**，库里只存 sha256 摘要：因此登出可以即时吊销、
  刷新可以轮转，不需要 JWT 签名密钥，也不引入额外依赖（见 security-and-license）。
- 审计日志只记动作码与对象名，不记口令等敏感字段。
"""

from __future__ import annotations

import secrets
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.enums import AuthTokenKind, UserRole, UserStatus


def new_user_id() -> str:
    """用户主键：UUID 风格随机串，不暴露注册顺序与规模。"""
    return secrets.token_hex(16)


class User(Base):
    """账号。

    表名用 `app_user` 而不是 `user`：`user` 在多个数据库里是保留字，
    迁移与手写 SQL 都要加引号，容易出错。
    """

    __tablename__ = "app_user"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_user_id)
    username: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(254), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    role: Mapped[UserRole] = mapped_column(default=UserRole.VIEWER, nullable=False)
    status: Mapped[UserStatus] = mapped_column(
        default=UserStatus.ACTIVE, nullable=False
    )
    display_name: Mapped[str | None] = mapped_column(String(64), default=None)
    avatar_url: Mapped[str | None] = mapped_column(String(512), default=None)
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class AuthToken(Base):
    """访问令牌与刷新令牌。

    只存摘要：数据库泄露也无法直接冒用；吊销就是标记 revoked_at。
    """

    __tablename__ = "auth_token"
    __table_args__ = (Index("ix_auth_token_user", "user_id", "kind"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("app_user.id"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    kind: Mapped[AuthTokenKind] = mapped_column(nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PasswordResetToken(Base):
    """找回口令的一次性凭据。用完即标记 used_at，不可重放。"""

    __tablename__ = "password_reset_token"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("app_user.id"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AuditLog(Base):
    """账号相关操作留痕。

    `actor` 存用户名快照：账号被删后日志仍可读，且不依赖外键存活。
    `target` 只放非敏感的对象名（受影响账号、被改动的对象），
    口令、令牌等敏感字段一律不入审计表。
    """

    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_created", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor_id: Mapped[str | None] = mapped_column(
        ForeignKey("app_user.id"), default=None
    )
    actor: Mapped[str] = mapped_column(String(32), nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    target: Mapped[str | None] = mapped_column(String(64), default=None)
    result: Mapped[str] = mapped_column(String(8), nullable=False)
    ip: Mapped[str | None] = mapped_column(String(45), default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
