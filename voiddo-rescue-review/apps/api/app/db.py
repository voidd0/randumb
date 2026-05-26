from __future__ import annotations

import os
from pathlib import Path
import psycopg

from .config import get_settings


def connect():
    return psycopg.connect(get_settings().database_url)


def migrate() -> None:
    migrations_dir = Path(__file__).resolve().parent.parent / "migrations"
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations "
                "(filename text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
            )
            for path in sorted(migrations_dir.glob("*.sql")):
                cur.execute("SELECT 1 FROM schema_migrations WHERE filename = %s", (path.name,))
                if cur.fetchone():
                    continue
                cur.execute(path.read_text())
                cur.execute("INSERT INTO schema_migrations(filename) VALUES (%s)", (path.name,))
        conn.commit()


if __name__ == "__main__":
    command = os.environ.get("VOIDDO_RESCUE_DB_COMMAND", "migrate")
    if command != "migrate":
        raise SystemExit(f"unknown db command: {command}")
    migrate()
