"""Persist rule references on ontologies for source traceability (M-01)."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0010_ontology_rule_ids"
down_revision = "0009_model_edit_revision"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ontology_rule_ref",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "ontology_id", sa.Integer(), sa.ForeignKey("ontology.id"), nullable=False
        ),
        sa.Column(
            "rule_id", sa.Integer(), sa.ForeignKey("governance_rule.id"), nullable=False
        ),
        sa.Column("pinned_revision", sa.Integer(), nullable=False),
        sa.UniqueConstraint("ontology_id", "rule_id", name="uq_ontology_rule_ref"),
    )


def downgrade() -> None:
    op.drop_table("ontology_rule_ref")
