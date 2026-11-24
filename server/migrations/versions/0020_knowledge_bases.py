"""Add knowledge uploads, generation indexes and explicit graph links.

Downgrade removes these new tables and all knowledge data; back up before rollback.
Existing graph, account and evidence rows are never altered by this migration.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0020_knowledge_bases"
down_revision = "0019_asset_audit"
branch_labels = None
depends_on = None


def _created() -> sa.Column:
    return sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )


def _updated() -> sa.Column:
    return sa.Column(
        "updated_at",
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )


def upgrade() -> None:
    op.create_table(
        "knowledge_base",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.String(4000), nullable=False),
        sa.Column(
            "created_by", sa.String(32), sa.ForeignKey("app_user.id"), nullable=False
        ),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("index_revision", sa.Integer(), nullable=False, server_default="0"),
        _created(),
        _updated(),
    )
    op.create_table(
        "knowledge_document",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "kb_id", sa.Integer(), sa.ForeignKey("knowledge_base.id"), nullable=False
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("media_type", sa.String(100), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("generation", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("active_generation", sa.Integer(), nullable=True),
        _created(),
        _updated(),
        sa.UniqueConstraint("kb_id", "content_hash", name="uq_knowledge_document_hash"),
        sa.CheckConstraint(
            "length(content) <= 2097152", name="ck_knowledge_content_size"
        ),
    )
    op.create_index("ix_knowledge_document_kb_id", "knowledge_document", ["kb_id"])
    op.create_table(
        "knowledge_index",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "document_id",
            sa.String(32),
            sa.ForeignKey("knowledge_document.id"),
            nullable=False,
        ),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("normalized_text", sa.Text(), nullable=False),
        sa.Column("parser_version", sa.String(100), nullable=False),
        sa.Column("chunker_version", sa.String(100), nullable=False),
        sa.Column("embedding_version", sa.String(100), nullable=True),
        sa.Column("embedding_model", sa.String(255), nullable=True),
        sa.Column("embedding_dimensions", sa.Integer(), nullable=True),
        sa.Column("parse_status", sa.String(16), nullable=False),
        sa.Column("semantic_status", sa.String(32), nullable=False),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column("error_reason", sa.String(200), nullable=True),
        _created(),
        sa.UniqueConstraint(
            "document_id", "generation", name="uq_knowledge_index_generation"
        ),
        sa.CheckConstraint(
            "parse_status IN ('SUCCESS', 'PARTIAL')", name="ck_knowledge_parse_status"
        ),
        sa.CheckConstraint(
            "semantic_status IN ('NOT_CONFIGURED', 'INDEXING', 'READY', 'FAILED')",
            name="ck_knowledge_semantic_status",
        ),
    )
    op.create_table(
        "knowledge_chunk",
        sa.Column("id", sa.String(100), primary_key=True),
        sa.Column(
            "index_id",
            sa.String(32),
            sa.ForeignKey("knowledge_index.id"),
            nullable=False,
        ),
        sa.Column("text", sa.String(800), nullable=False),
        sa.Column("location", sa.JSON(), nullable=False),
        sa.Column("section", sa.Text(), nullable=True),
        sa.Column("vector", sa.JSON(), nullable=True),
        sa.CheckConstraint("length(text) <= 800", name="ck_knowledge_chunk_size"),
    )
    op.create_index("ix_knowledge_chunk_index_id", "knowledge_chunk", ["index_id"])
    op.create_table(
        "knowledge_task",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "document_id",
            sa.String(32),
            sa.ForeignKey("knowledge_document.id"),
            nullable=False,
        ),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("phase", sa.String(16), nullable=False),
        sa.Column("processed_chunks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_chunks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("error_reason", sa.String(200), nullable=True),
        sa.Column("worker_id", sa.String(64), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        _created(),
        sa.UniqueConstraint(
            "document_id", "generation", name="uq_knowledge_task_generation"
        ),
        sa.CheckConstraint(
            "status IN ('QUEUED', 'RUNNING', 'SUCCESS', 'PARTIAL', "
            "'FAILED', 'CANCELLED', 'INTERRUPTED')",
            name="ck_knowledge_task_status",
        ),
        sa.CheckConstraint(
            "phase IN ('QUEUED', 'EXTRACTING', 'INDEXING', 'FINISHED')",
            name="ck_knowledge_task_phase",
        ),
    )
    op.create_index(
        "ix_knowledge_task_claim",
        "knowledge_task",
        ["status", "expires_at", "created_at"],
    )
    op.create_table(
        "knowledge_graph_link",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "chunk_id",
            sa.String(100),
            sa.ForeignKey("knowledge_chunk.id"),
            nullable=False,
        ),
        sa.Column(
            "graph_revision_id",
            sa.Integer(),
            sa.ForeignKey("graph_revision.id"),
            nullable=False,
        ),
        sa.Column("entity_iri", sa.String(2000), nullable=False),
        sa.Column(
            "fact_id", sa.Integer(), sa.ForeignKey("graph_triple.id"), nullable=True
        ),
        sa.Column("predicate", sa.String(2000), nullable=True),
        sa.Column("object_iri", sa.String(2000), nullable=True),
        sa.Column(
            "created_by", sa.String(32), sa.ForeignKey("app_user.id"), nullable=False
        ),
        _created(),
        sa.UniqueConstraint(
            "chunk_id",
            "graph_revision_id",
            "entity_iri",
            "fact_id",
            name="uq_knowledge_graph_link",
        ),
    )
    op.create_index(
        "ix_knowledge_graph_link_chunk_id", "knowledge_graph_link", ["chunk_id"]
    )
    op.create_index(
        "ix_knowledge_graph_link_graph_revision_id",
        "knowledge_graph_link",
        ["graph_revision_id"],
    )


def downgrade() -> None:
    # Explicitly destructive to knowledge data only; do not run on a live DB.
    for name in (
        "knowledge_graph_link",
        "knowledge_task",
        "knowledge_chunk",
        "knowledge_index",
        "knowledge_document",
        "knowledge_base",
    ):
        op.drop_table(name)
