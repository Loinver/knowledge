"""View template persistence: layout binding pinned to an ontology revision."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0014_view_template"
down_revision = "0013_extraction_traceability"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "view_template",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name_i18n", sa.JSON(), nullable=False),
        sa.Column("layout_id", sa.String(length=64), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column(
            "ontology_id",
            sa.Integer(),
            sa.ForeignKey("ontology.id"),
            nullable=False,
        ),
        sa.Column("ontology_revision", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("view_template")
