from __future__ import annotations

import os

import psycopg
from psycopg.rows import dict_row


def database_url() -> str:
    return os.environ.get("DATABASE_URL", "postgresql://voiddo_rescue:change-me@postgres:5432/voiddo_rescue")


def connect():
    return psycopg.connect(database_url(), row_factory=dict_row)
