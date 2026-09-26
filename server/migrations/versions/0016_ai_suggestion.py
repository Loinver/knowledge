"""AI suggestion review queue: explainable, human-confirmed suggestions."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0016_ai_suggestion"
down_revision = "0015_task_watermark"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_suggestion",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("target_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_suggestion_status", "ai_suggestion", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_suggestion_status", table_name="ai_suggestion")
    op.drop_table("ai_suggestion")
