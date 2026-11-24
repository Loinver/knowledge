"""Persist resource and ontology multilingual aliases.

Revision ID: 0024_ontology_synonyms
Revises: 0023_ontology_modeling
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0024_ontology_synonyms"
down_revision = "0023_ontology_modeling"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("model_resource", "ontology"):
        op.add_column(
            table,
            sa.Column("synonyms", sa.JSON(), nullable=False, server_default="[]"),
        )


def downgrade() -> None:
    for table in ("ontology", "model_resource"):
        op.drop_column(table, "synonyms")
