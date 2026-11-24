"""Run the model-config migration only on a disposable SQLite database."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

SERVER = Path(__file__).resolve().parents[1]


def test_model_config_upgrade_downgrade_upgrade(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path}/models-migration.db"
    env = {**os.environ, "KG_DATABASE_URL": url}

    def migrate(direction: str, revision: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "alembic", direction, revision],
            cwd=SERVER,
            env=env,
            capture_output=True,
            text=True,
            timeout=90,
        )

    upgraded = migrate("upgrade", "head")
    assert upgraded.returncode == 0, upgraded.stderr
    engine = create_engine(url)
    try:
        inspector = inspect(engine)
        assert {"ai_model_config", "ai_model_default"} <= set(
            inspector.get_table_names()
        )
        with engine.connect() as connection:
            assert connection.execute(
                text(
                    "SELECT capability, config_id, revision "
                    "FROM ai_model_default ORDER BY capability"
                )
            ).all() == [("CHAT", None, 1), ("EMBEDDING", None, 1)]
    finally:
        engine.dispose()

    downgraded = migrate("downgrade", "0020_knowledge_bases")
    assert downgraded.returncode == 0, downgraded.stderr
    engine = create_engine(url)
    try:
        assert not {"ai_model_config", "ai_model_default"}.intersection(
            inspect(engine).get_table_names()
        )
    finally:
        engine.dispose()
    upgraded_again = migrate("upgrade", "head")
    assert upgraded_again.returncode == 0, upgraded_again.stderr
