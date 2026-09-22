"""Freeze ontology header metadata for future publications.

Revision ID: 0003_ontology_metadata
Revises: 0002_rule_library

Existing revisions retain an empty snapshot; mutable headers cannot reconstruct
their historical values and must not be silently backfilled.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_ontology_metadata"
down_revision = "0002_rule_library"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ontology_revision",
        sa.Column(
            "metadata_snapshot",
            sa.JSON(),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("ontology_revision", "metadata_snapshot")
