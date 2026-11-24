"""Replay the appended migration only against disposable databases."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text

SERVER = Path(__file__).resolve().parents[1]
TABLES = {
    "knowledge_base",
    "knowledge_document",
    "knowledge_index",
    "knowledge_chunk",
    "knowledge_task",
    "knowledge_graph_link",
}


@pytest.mark.parametrize("existing", [False, True])
def test_knowledge_upgrade_and_isolated_rollback(
    tmp_path: Path, existing: bool
) -> None:
    url = f"sqlite:///{tmp_path}/migration.db"
    env = {**os.environ, "KG_DATABASE_URL": url}

    def migrate(direction: str, revision: str) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "alembic", direction, revision],
            cwd=SERVER,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, result.stderr

    if existing:
        migrate("upgrade", "0019_asset_audit")
        engine = create_engine(url)
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO ontology (name, iri, status, current_revision) "
                    "VALUES ('Retained', 'https://example.test/retained', 'DRAFT', 0)"
                )
            )
        engine.dispose()
    migrate("upgrade", "0020_knowledge_bases")
    engine = create_engine(url)
    try:
        inspector = inspect(engine)
        assert set(inspector.get_table_names()) >= TABLES
        assert {
            column["name"] for column in inspector.get_columns("knowledge_document")
        } == {
            "id",
            "kb_id",
            "name",
            "media_type",
            "content",
            "content_hash",
            "revision",
            "archived",
            "generation",
            "active_generation",
            "created_at",
            "updated_at",
        }
        assert {
            tuple(unique["column_names"])
            for unique in inspector.get_unique_constraints("knowledge_document")
        } == {("kb_id", "content_hash")}
        assert {
            fk["referred_table"]
            for fk in inspector.get_foreign_keys("knowledge_graph_link")
        } == {
            "knowledge_chunk",
            "graph_revision",
            "graph_triple",
            "app_user",
        }
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO app_user "
                    "(id, username, email, password_hash, role, status) "
                    "VALUES ('actor', 'actor', 'actor@example.test', "
                    "'unused', 'EDITOR', 'ACTIVE')"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO knowledge_base (name, description, created_by) "
                    "VALUES ('new knowledge', '', 'actor')"
                )
            )
    finally:
        engine.dispose()
    migrate("downgrade", "0019_asset_audit")
    engine = create_engine(url)
    try:
        assert not TABLES.intersection(inspect(engine).get_table_names())
        with engine.connect() as connection:
            assert (
                connection.scalar(
                    text("SELECT username FROM app_user WHERE id = 'actor'")
                )
                == "actor"
            )
            if existing:
                assert (
                    connection.scalar(text("SELECT name FROM ontology")) == "Retained"
                )
    finally:
        engine.dispose()
    migrate("upgrade", "0020_knowledge_bases")
