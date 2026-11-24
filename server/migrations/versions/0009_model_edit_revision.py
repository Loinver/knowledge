"""Add draft edit CAS revision to model resources.

Revision ID: 0009_model_edit_revision
Revises: 0008_enum_dictionaries

This column is consumed by M-07 draft updates. It has its own migration so
rolling back M-05 enum dictionaries does not remove an unrelated concurrency
field from model resources.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0009_model_edit_revision"
down_revision = "0008_enum_dictionaries"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "model_resource",
        sa.Column("edit_revision", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("model_resource", "edit_revision")
