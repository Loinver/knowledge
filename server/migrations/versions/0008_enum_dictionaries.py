"""Versioned enum dictionaries and explicit property pins.

Revision ID: 0008_enum_dictionaries
Revises: 0007_accounts
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008_enum_dictionaries"
down_revision = "0007_accounts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 旧占位 ID 没有字典内容，不能伪造字典或静默清除引用。
    unresolved = list(
        op.get_bind().execute(
            sa.text(
                "SELECT resource_id, enum_dict_id FROM datatype_prop_detail "
                "WHERE enum_dict_id IS NOT NULL ORDER BY resource_id"
            )
        )
    )
    if unresolved:
        raise RuntimeError(
            f"Unresolved legacy enum references: {unresolved}. "
            "Restore their dictionary definitions or explicitly resolve these "
            "references before upgrading."
        )
    op.create_table(
        "enum_dictionary",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(128), unique=True, nullable=False),
        sa.Column("label_i18n", sa.JSON(), nullable=False),
        sa.Column("definition_i18n", sa.JSON(), nullable=False),
        sa.Column("entries", sa.JSON(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint("revision > 0", name="ck_enum_revision"),
    )
    op.create_table(
        "enum_dictionary_revision",
        sa.Column(
            "dictionary_id",
            sa.Integer(),
            sa.ForeignKey("enum_dictionary.id"),
            primary_key=True,
        ),
        sa.Column("revision", sa.Integer(), primary_key=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.CheckConstraint("revision > 0", name="ck_enum_history_revision"),
    )
    with op.batch_alter_table("datatype_prop_detail") as batch:
        batch.add_column(sa.Column("enum_dict_revision", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_prop_enum_dictionary", "enum_dictionary", ["enum_dict_id"], ["id"]
        )
        batch.create_foreign_key(
            "fk_prop_enum_revision",
            "enum_dictionary_revision",
            ["enum_dict_id", "enum_dict_revision"],
            ["dictionary_id", "revision"],
        )
        batch.create_check_constraint(
            "ck_prop_enum_pin",
            "(enum_dict_id IS NULL AND enum_dict_revision IS NULL) OR "
            "(enum_dict_id IS NOT NULL AND enum_dict_revision IS NOT NULL)",
        )


def downgrade() -> None:
    if op.get_bind().execute(sa.text("SELECT id FROM enum_dictionary LIMIT 1")).first():
        raise RuntimeError(
            "Cannot downgrade while enum dictionaries exist: "
            "this would discard dictionary history and leave unresolved "
            "property references."
        )
    with op.batch_alter_table("datatype_prop_detail") as batch:
        batch.drop_constraint("ck_prop_enum_pin", type_="check")
        batch.drop_constraint("fk_prop_enum_revision", type_="foreignkey")
        batch.drop_constraint("fk_prop_enum_dictionary", type_="foreignkey")
        batch.drop_column("enum_dict_revision")
    op.drop_table("enum_dictionary_revision")
    op.drop_table("enum_dictionary")
