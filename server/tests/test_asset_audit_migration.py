"""Only isolated temporary databases; never run Alembic against the dev database."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text

SERVER = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("from_previous", [False, True])
def test_asset_audit_upgrade_preserves_existing_data(
    tmp_path: Path, from_previous: bool
) -> None:
    url = f"sqlite:///{tmp_path}/migration.db"
    env = {**os.environ, "KG_DATABASE_URL": url}

    def migrate(revision: str) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", revision],
            cwd=SERVER,
            env=env,
            text=True,
            capture_output=True,
            timeout=60,
        )
        assert result.returncode == 0, result.stderr

    if from_previous:
        migrate("0018_data_prop_constraints")
        engine = create_engine(url)
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO ontology (name, iri, status, current_revision) "
                    "VALUES ('ExistingOntology', 'https://example.org/existing', "
                    "'DRAFT', 0)"
                )
            )
        engine.dispose()
    migrate("0019_asset_audit")
    engine = create_engine(url)
    try:
        inspector = inspect(engine)
        assert inspector.get_foreign_keys("asset_audit_log") == []
        assert {
            column["name"] for column in inspector.get_columns("asset_audit_log")
        } == {
            "id",
            "actor_id",
            "action",
            "object_type",
            "object_id",
            "version_before",
            "version_after",
            "result",
            "error_code",
            "correlation_id",
            "created_at",
        }
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT COUNT(*) FROM asset_audit_log")) == 0
            if from_previous:
                assert (
                    connection.scalar(text("SELECT name FROM ontology"))
                    == "ExistingOntology"
                )
    finally:
        engine.dispose()


def test_downgrade_refuses_to_erase_retained_history(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path}/retained-audit.db"
    env = {**os.environ, "KG_DATABASE_URL": url}

    def migrate(direction: str, revision: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "alembic", direction, revision],
            cwd=SERVER,
            env=env,
            text=True,
            capture_output=True,
            timeout=60,
        )

    upgraded = migrate("upgrade", "0019_asset_audit")
    assert upgraded.returncode == 0, upgraded.stderr
    engine = create_engine(url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO asset_audit_log "
                    "(actor_id, action, object_type, result, correlation_id) "
                    "VALUES ('deleted-actor', 'CREATE', 'ONTOLOGY', "
                    "'OK', 'retained-event')"
                )
            )
        downgraded = migrate("downgrade", "0018_data_prop_constraints")
        assert downgraded.returncode != 0
        assert "retention requires an explicit archival decision" in downgraded.stderr
        with engine.connect() as connection:
            assert (
                connection.scalar(text("SELECT actor_id FROM asset_audit_log"))
                == "deleted-actor"
            )
            assert (
                connection.scalar(text("SELECT version_num FROM alembic_version"))
                == "0019_asset_audit"
            )
    finally:
        engine.dispose()
