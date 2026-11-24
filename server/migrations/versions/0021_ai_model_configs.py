"""Persist administrator-managed AI model endpoints and selections."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0021_ai_model_configs"
down_revision = "0020_knowledge_bases"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_model_config",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("capability", sa.String(16), nullable=False),
        sa.Column("base_url", sa.String(2048), nullable=False),
        sa.Column("model", sa.String(255), nullable=False),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("model_version", sa.String(100), nullable=False, server_default="1"),
        sa.Column("credential_cipher", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("name", name="uq_ai_model_config_name"),
        sa.CheckConstraint(
            "capability IN ('CHAT', 'EMBEDDING')", name="ck_ai_model_config_capability"
        ),
        sa.CheckConstraint(
            "timeout_seconds >= 1 AND timeout_seconds <= 120",
            name="ck_ai_model_config_timeout",
        ),
    )
    op.create_index(
        "ix_ai_model_config_capability_enabled",
        "ai_model_config",
        ["capability", "enabled"],
    )
    op.create_table(
        "ai_model_default",
        sa.Column("capability", sa.String(16), primary_key=True),
        sa.Column(
            "config_id",
            sa.Integer(),
            sa.ForeignKey("ai_model_config.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "capability IN ('CHAT', 'EMBEDDING')", name="ck_ai_model_default_capability"
        ),
    )
    op.bulk_insert(
        sa.table(
            "ai_model_default",
            sa.column("capability", sa.String(16)),
            sa.column("config_id", sa.Integer()),
            sa.column("revision", sa.Integer()),
        ),
        [
            {"capability": "CHAT", "config_id": None, "revision": 1},
            {"capability": "EMBEDDING", "config_id": None, "revision": 1},
        ],
    )


def downgrade() -> None:
    op.drop_table("ai_model_default")
    op.drop_index("ix_ai_model_config_capability_enabled", table_name="ai_model_config")
    op.drop_table("ai_model_config")
