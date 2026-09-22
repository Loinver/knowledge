"""Standard clause index with self-authored descriptions (M-03).

Revision ID: 0005_standard_clause
Revises: 0004_assembly_templates

Stores clause numbers plus self-authored bilingual descriptions only;
never the source text of the standard itself.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005_standard_clause"
down_revision = "0004_assembly_templates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "standard_clause",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("standard", sa.String(64), nullable=False),
        sa.Column("clause_number", sa.String(32), nullable=False),
        sa.Column("title_i18n", sa.JSON(), nullable=False),
        sa.Column("self_authored_description", sa.JSON(), nullable=False),
        sa.Column("product_fallback", sa.String(256), nullable=True),
        sa.Column(
            "appendix_nature",
            sa.String(12),
            nullable=False,
            server_default="NORMATIVE",
        ),
        sa.Column("date_lexicon", sa.String(128), nullable=True),
        sa.Column("clause_disambiguation", sa.String(512), nullable=True),
        sa.Column("example_domain", sa.String(128), nullable=True),
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
        sa.UniqueConstraint("standard", "clause_number", name="uq_clause_per_standard"),
        sa.CheckConstraint(
            "appendix_nature IN ('NORMATIVE', 'INFORMATIVE')",
            name="ck_clause_appendix_nature",
        ),
    )


def downgrade() -> None:
    op.drop_table("standard_clause")
