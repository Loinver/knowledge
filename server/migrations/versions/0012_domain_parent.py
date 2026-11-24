"""Business domain hierarchy: optional parent link for the domain tree."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0012_domain_parent"
down_revision = "0011_aggregate_edit_revision"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SQLite 不支持直接 ALTER 加约束，必须走 batch（copy-and-move）模式。
    # 列可空：既有域没有父域，平铺语义不变。
    with op.batch_alter_table("business_domain") as batch:
        batch.add_column(sa.Column("parent_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_business_domain_parent",
            "business_domain",
            ["parent_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("business_domain") as batch:
        batch.drop_constraint("fk_business_domain_parent", type_="foreignkey")
        batch.drop_column("parent_id")
