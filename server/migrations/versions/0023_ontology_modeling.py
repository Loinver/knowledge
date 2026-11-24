"""Add review-only modeling proposals, immutable revisions and apply receipts."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0023_ontology_modeling"
down_revision = "0022_validation_binding"
branch_labels = None
depends_on = None


def _created() -> sa.Column:
    return sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )


def upgrade() -> None:
    op.create_table(
        "ontology_modeling_proposal",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "ontology_id", sa.Integer(), sa.ForeignKey("ontology.id"), nullable=False
        ),
        sa.Column("actor_id", sa.String(32), nullable=False),
        sa.Column("request_key", sa.String(128), nullable=False),
        sa.Column("request_digest", sa.String(64), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("context", sa.JSON(), nullable=False),
        sa.Column("provenance", sa.JSON(), nullable=False),
        _created(),
        sa.UniqueConstraint("actor_id", "request_key"),
    )
    op.create_index(
        "ix_ontology_modeling_proposal_ontology_id",
        "ontology_modeling_proposal",
        ["ontology_id"],
    )
    op.create_table(
        "ontology_modeling_revision",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "proposal_id",
            sa.String(32),
            sa.ForeignKey("ontology_modeling_proposal.id"),
            nullable=False,
        ),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("candidate", sa.JSON(), nullable=False),
        sa.Column("candidate_digest", sa.String(64), nullable=False),
        sa.Column("actor_id", sa.String(32), nullable=False),
        sa.Column("origin", sa.String(16), nullable=False),
        sa.Column("note", sa.String(1000), nullable=False),
        _created(),
        sa.UniqueConstraint("proposal_id", "revision"),
    )
    op.create_table(
        "ontology_modeling_validation",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "proposal_id",
            sa.String(32),
            sa.ForeignKey("ontology_modeling_proposal.id"),
            nullable=False,
        ),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("report", sa.JSON(), nullable=False),
        _created(),
    )
    op.create_index(
        "ix_ontology_modeling_validation_proposal_id",
        "ontology_modeling_validation",
        ["proposal_id"],
    )
    op.create_table(
        "ontology_modeling_application",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "proposal_id",
            sa.String(32),
            sa.ForeignKey("ontology_modeling_proposal.id"),
            nullable=False,
        ),
        sa.Column("actor_id", sa.String(32), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_digest", sa.String(64), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        _created(),
        sa.UniqueConstraint("proposal_id"),
        sa.UniqueConstraint("actor_id", "idempotency_key"),
    )


def downgrade() -> None:
    op.drop_table("ontology_modeling_application")
    op.drop_table("ontology_modeling_validation")
    op.drop_table("ontology_modeling_revision")
    op.drop_table("ontology_modeling_proposal")
