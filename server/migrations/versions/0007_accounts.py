"""Account, session and audit tables.

Revision ID: 0007_accounts
Revises: 0006_prop_constraints

口令只存 PBKDF2 派生值；令牌只存 sha256 摘要，因此登出可即时吊销、
刷新可轮转，且不需要 JWT 签名密钥（不新增依赖）。
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007_accounts"
down_revision = "0006_prop_constraints"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "app_user",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("username", sa.String(32), nullable=False, unique=True),
        sa.Column("email", sa.String(254), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(256), nullable=False),
        sa.Column("role", sa.String(16), nullable=False, server_default="VIEWER"),
        sa.Column("status", sa.String(16), nullable=False, server_default="ACTIVE"),
        sa.Column("display_name", sa.String(64), nullable=True),
        sa.Column("avatar_url", sa.String(512), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "role IN ('ADMIN', 'EDITOR', 'VIEWER')", name="ck_user_role"
        ),
        sa.CheckConstraint("status IN ('ACTIVE', 'DISABLED')", name="ck_user_status"),
    )

    op.create_table(
        "auth_token",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id", sa.String(32), sa.ForeignKey("app_user.id"), nullable=False
        ),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("kind IN ('ACCESS', 'REFRESH')", name="ck_token_kind"),
    )
    op.create_index("ix_auth_token_user", "auth_token", ["user_id", "kind"])

    op.create_table(
        "password_reset_token",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id", sa.String(32), sa.ForeignKey("app_user.id"), nullable=False
        ),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "actor_id", sa.String(32), sa.ForeignKey("app_user.id"), nullable=True
        ),
        sa.Column("actor", sa.String(32), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("target", sa.String(64), nullable=True),
        sa.Column("result", sa.String(8), nullable=False),
        sa.Column("ip", sa.String(45), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_audit_created", "audit_log", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_audit_created", table_name="audit_log")
    op.drop_table("audit_log")
    op.drop_table("password_reset_token")
    op.drop_index("ix_auth_token_user", table_name="auth_token")
    op.drop_table("auth_token")
    op.drop_table("app_user")
