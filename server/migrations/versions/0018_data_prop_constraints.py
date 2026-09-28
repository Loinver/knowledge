"""数据属性补基数/数值范围/来源条款列（GB/T 48000.3 附录 A）。"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0018_data_prop_constraints"
down_revision = "0017_evidence_transforms"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 历史行无约束，保持可空：读回时按"未声明"处理，不伪造成约束。
    op.add_column(
        "datatype_prop_detail",
        sa.Column("min_cardinality", sa.Integer(), nullable=True),
    )
    op.add_column(
        "datatype_prop_detail",
        sa.Column("max_cardinality", sa.Integer(), nullable=True),
    )
    op.add_column(
        "datatype_prop_detail",
        sa.Column("min_value", sa.String(length=256), nullable=True),
    )
    op.add_column(
        "datatype_prop_detail",
        sa.Column("max_value", sa.String(length=256), nullable=True),
    )
    op.add_column(
        "datatype_prop_detail",
        sa.Column("source_clause_ref", sa.String(length=256), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("datatype_prop_detail", "source_clause_ref")
    op.drop_column("datatype_prop_detail", "max_value")
    op.drop_column("datatype_prop_detail", "min_value")
    op.drop_column("datatype_prop_detail", "max_cardinality")
    op.drop_column("datatype_prop_detail", "min_cardinality")
