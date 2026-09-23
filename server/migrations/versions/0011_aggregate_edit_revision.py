"""Separate aggregate editing tokens from published revision numbers."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0011_aggregate_edit_revision"
down_revision = "0010_ontology_rule_ids"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("mapping", "ontology", "business_domain"):
        op.add_column(
            table,
            sa.Column(
                "edit_revision", sa.Integer(), nullable=False, server_default="0"
            ),
        )


def downgrade() -> None:
    for table in ("business_domain", "ontology", "mapping"):
        op.drop_column(table, "edit_revision")
