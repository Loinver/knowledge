"""Add the rule library without changing existing resources.

Revision ID: 0002_rule_library
Revises: 67ccedb5a0e9
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_rule_library"
down_revision = "67ccedb5a0e9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "governance_rule",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("identifier", sa.String(128), nullable=False),
        sa.Column("name_i18n", sa.JSON(), nullable=False),
        sa.Column("category", sa.String(128), nullable=False),
        sa.Column("source_kind", sa.String(16), nullable=False),
        sa.Column("source_reference", sa.String(512), nullable=False),
        sa.Column("target_iri", sa.String(2048), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("language", sa.String(8), nullable=False),
        sa.Column("expression", sa.Text(), nullable=False),
        sa.Column("execution", sa.String(8), nullable=False),
        sa.Column("positive_example", sa.Text(), nullable=False),
        sa.Column("negative_example", sa.Text(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("identifier", name="uq_governance_rule_identifier"),
        sa.CheckConstraint("revision >= 1", name="ck_governance_rule_revision"),
        sa.CheckConstraint(
            "source_kind IN ('STANDARD', 'ENTERPRISE')",
            name="ck_governance_rule_source_kind",
        ),
        sa.CheckConstraint(
            "severity IN ('INFO', 'WARNING', 'VIOLATION')",
            name="ck_governance_rule_severity",
        ),
        sa.CheckConstraint(
            "language IN ('SHACL', 'OWL')", name="ck_governance_rule_language"
        ),
        sa.CheckConstraint(
            "execution IN ('AUTO', 'MANUAL')", name="ck_governance_rule_execution"
        ),
    )


def downgrade() -> None:
    op.drop_table("governance_rule")
