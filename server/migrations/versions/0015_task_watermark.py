"""View template + extraction task persistence."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0015_task_watermark"
down_revision = "0014_view_template"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "extraction_task",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "mapping_revision_id",
            sa.Integer(),
            sa.ForeignKey("mapping_revision.id"),
            nullable=False,
        ),
        sa.Column(
            "datasource_id", sa.Integer(), sa.ForeignKey("datasource.id"), nullable=False
        ),
        sa.Column("namespace", sa.String(length=512), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column(
            "run_id", sa.Integer(), sa.ForeignKey("extraction_run.id"), nullable=True
        ),
        sa.Column("incremental", sa.Boolean(), nullable=False),
        sa.Column("run_after", sa.DateTime(timezone=True), nullable=True),
        sa.Column("progress", sa.JSON(), nullable=False),
        sa.Column("watermark", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_task_status", "extraction_task", ["status"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_task_status", table_name="extraction_task")
    op.drop_table("extraction_task")
