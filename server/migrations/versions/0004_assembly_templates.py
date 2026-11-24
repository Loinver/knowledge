"""Add revision control and labels to existing assembly templates."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004_assembly_templates"
down_revision = "0003_ontology_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "assembly_template",
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "assembly_template",
        sa.Column("label_i18n", sa.JSON(), nullable=False, server_default="{}"),
    )


def downgrade() -> None:
    op.drop_column("assembly_template", "label_i18n")
    op.drop_column("assembly_template", "revision")
