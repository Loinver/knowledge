"""Bind validation reports to their immutable semantic input.

Revision ID: 0022_validation_binding
Revises: 0021_ai_model_configs
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0022_validation_binding"
down_revision = "0021_ai_model_configs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("validation_report", sa.Column("binding", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("validation_report", "binding")
