"""PC14 immutable business asset audit metadata."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0019_asset_audit"
down_revision = "0018_data_prop_constraints"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "asset_audit_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("actor_id", sa.String(32), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("object_type", sa.String(32), nullable=False),
        sa.Column("object_id", sa.Integer(), nullable=True),
        sa.Column("version_before", sa.JSON(), nullable=True),
        sa.Column("version_after", sa.JSON(), nullable=True),
        sa.Column("result", sa.String(8), nullable=False),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("correlation_id", sa.String(32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_asset_audit_created", "asset_audit_log", ["created_at", "id"])
    op.create_index(
        "ix_asset_audit_actor", "asset_audit_log", ["actor_id", "created_at"]
    )
    op.create_index(
        "ix_asset_audit_object",
        "asset_audit_log",
        ["object_type", "object_id", "created_at"],
    )
    op.create_index(
        "ix_asset_audit_correlation", "asset_audit_log", ["correlation_id"], unique=True
    )


def downgrade() -> None:
    # Empty installations can replay migrations; retained history is never erased.
    audit = sa.table("asset_audit_log", sa.column("id", sa.Integer()))
    if op.get_bind().scalar(sa.select(audit.c.id).limit(1)) is not None:
        raise RuntimeError(
            "Asset audit retention requires an explicit archival decision"
        )
    op.drop_table("asset_audit_log")
