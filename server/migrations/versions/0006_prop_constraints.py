"""Persist data-property and object-property constraints (M-07).

Revision ID: 0006_prop_constraints
Revises: 0005_standard_clause

M1 只落了属性名与关系端点引用；数据类型、枚举引用、可空性、默认值、
端点基数与 OWL 特征此前在读写往返中被丢弃。本迁移把它们落成正式列。
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006_prop_constraints"
down_revision = "0005_standard_clause"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "datatype_prop_detail",
        sa.Column(
            "resource_id",
            sa.Integer(),
            sa.ForeignKey("model_resource.id"),
            primary_key=True,
        ),
        sa.Column("prop_name", sa.String(128), nullable=False),
        sa.Column("datatype", sa.String(64), nullable=False),
        sa.Column("enum_dict_id", sa.Integer(), nullable=True),
        sa.Column("nullable", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("default_value", sa.String(256), nullable=True),
    )
    op.create_table(
        "object_prop_detail",
        sa.Column(
            "resource_id",
            sa.Integer(),
            sa.ForeignKey("model_resource.id"),
            primary_key=True,
        ),
        sa.Column("domain_min", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("domain_max", sa.Integer(), nullable=False, server_default="-1"),
        sa.Column("range_min", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("range_max", sa.Integer(), nullable=False, server_default="-1"),
        sa.Column("domain_role_i18n", sa.JSON(), nullable=True),
        sa.Column("domain_cardinality_role_i18n", sa.JSON(), nullable=True),
        sa.Column("range_role_i18n", sa.JSON(), nullable=True),
        sa.Column("range_cardinality_role_i18n", sa.JSON(), nullable=True),
        sa.Column("owl", sa.JSON(), nullable=False, server_default="{}"),
    )


def downgrade() -> None:
    op.drop_table("object_prop_detail")
    op.drop_table("datatype_prop_detail")
