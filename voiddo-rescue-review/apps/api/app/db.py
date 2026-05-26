from __future__ import annotations

import os
from pathlib import Path
import psycopg
from psycopg.rows import dict_row

from .config import get_settings


def connect():
    return psycopg.connect(get_settings().database_url)


def connect_dict():
    return psycopg.connect(get_settings().database_url, row_factory=dict_row)


def fetch_one(query: str, params: tuple = ()):
    with connect_dict() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            return cur.fetchone()


def fetch_all(query: str, params: tuple = ()):
    with connect_dict() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            return cur.fetchall()


def execute(query: str, params: tuple = ()):
    with connect_dict() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            row = cur.fetchone() if cur.description else None
        conn.commit()
        return row


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
