"""Replay modeling migrations against a disposable SQLite database only."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect, text


def test_modeling_upgrade_preserves_existing_assets(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path}/migration.db"
    env = {**os.environ, "KG_DATABASE_URL": url}
    server = Path(__file__).resolve().parents[1]

    def migrate(direction: str, revision: str) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "alembic", direction, revision],
            cwd=server,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, result.stderr

    migrate("upgrade", "0021_ai_model_configs")
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO ontology "
                "(id,name,iri,label_i18n,status,current_revision,edit_revision) "
                "VALUES (1,'Prior','urn:prior','{}','DRAFT',0,3)"
            )
        )
    migrate("upgrade", "head")
    inspector = inspect(engine)
    assert {
        "ontology_modeling_proposal",
        "ontology_modeling_revision",
        "ontology_modeling_validation",
        "ontology_modeling_application",
    } <= set(inspector.get_table_names())
    assert "binding" in {
        column["name"] for column in inspector.get_columns("validation_report")
    }
    assert "synonyms" in {
        column["name"] for column in inspector.get_columns("model_resource")
    }
    with engine.connect() as connection:
        assert connection.execute(
            text("SELECT name,edit_revision FROM ontology WHERE id=1")
        ).one() == ("Prior", 3)
    engine.dispose()
    migrate("downgrade", "0021_ai_model_configs")
    migrate("upgrade", "head")
