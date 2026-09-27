"""事实证据补属性级转换链：从"用了哪些列"到"这个值怎么算出来的"。"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0017_evidence_transforms"
down_revision = "0016_ai_suggestion"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 历史行没有转换链，保持可空：读回时按"未记录"处理，不伪造成 IDENTITY。
    op.add_column(
        "fact_evidence",
        sa.Column("column_transforms", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("fact_evidence", "column_transforms")
