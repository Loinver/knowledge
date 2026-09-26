"""Extraction traceability: edge payloads, derived-edge provenance, evidence frozen pins.

- graph_triple.props: ASSOCIATIVE 关联属性随边落库（持股比例/金额/角色）。
- derived_edge: 规则 ID + 参与直接事实 + 推导产物，使派生事实可解释。
- fact_evidence: 抽取当时的映射/本体/资源/规则版本冻结引用。
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0013_extraction_traceability"
down_revision = "0012_domain_parent"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("governance_rule") as batch:
        batch.drop_constraint("ck_governance_rule_language", type_="check")
        batch.create_check_constraint(
            "ck_governance_rule_language",
            "language IN ('SHACL', 'OWL', 'DATA', 'DERIVATION')",
        )
    with op.batch_alter_table("graph_triple") as batch:
        batch.add_column(sa.Column("props", sa.JSON(), nullable=True))
    with op.batch_alter_table("derived_edge") as batch:
        batch.add_column(sa.Column("props", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("rule_id", sa.String(length=128), nullable=True))
        batch.add_column(sa.Column("source_fact_ids", sa.JSON(), nullable=True))
    with op.batch_alter_table("fact_evidence") as batch:
        batch.add_column(sa.Column("mapping_revision_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("ontology_revision", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("resource_revisions", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("rule_revisions", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("fact_evidence") as batch:
        batch.drop_column("rule_revisions")
        batch.drop_column("resource_revisions")
        batch.drop_column("ontology_revision")
        batch.drop_column("mapping_revision_id")
    with op.batch_alter_table("derived_edge") as batch:
        batch.drop_column("source_fact_ids")
        batch.drop_column("rule_id")
        batch.drop_column("props")
    with op.batch_alter_table("graph_triple") as batch:
        batch.drop_column("props")
    with op.batch_alter_table("governance_rule") as batch:
        batch.drop_constraint("ck_governance_rule_language", type_="check")
        batch.create_check_constraint(
            "ck_governance_rule_language", "language IN ('SHACL', 'OWL')"
        )
