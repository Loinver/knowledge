"""Inspect or migrate datasource secrets without touching the database by default.

Stop application writes and take a database backup before --apply. The current
KG_CRYPTO_KEY encrypts the result; set KG_OLD_CRYPTO_KEY in the environment if
the existing records used a different key. Neither key appears in CLI history.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from app.core.db import get_engine
from app.domain.source_service import reencrypt_datasources


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="commit the migration")
    parser.add_argument(
        "--backup-confirmed",
        action="store_true",
        help="confirm an external DB backup exists",
    )
    args = parser.parse_args()
    if args.apply and not args.backup_confirmed:
        parser.error("--apply requires --backup-confirmed")

    with Session(get_engine()) as session:
        changed = reencrypt_datasources(
            session, previous_key=os.environ.get("KG_OLD_CRYPTO_KEY") or None
        )
        if args.apply:
            session.commit()
        else:
            session.rollback()
    print(f"Datasource records requiring migration: {changed}")
    print("Applied." if args.apply else "Dry run; no changes saved.")


if __name__ == "__main__":
    main()
