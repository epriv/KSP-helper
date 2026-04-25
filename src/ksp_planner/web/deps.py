"""FastAPI dependencies — DB connection wrapping."""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator
from pathlib import Path

from ksp_planner import db as dblib


def _db_path() -> Path:
    return Path(os.environ.get("KSP_DB_PATH", "ksp.db"))


def get_db() -> Iterator[sqlite3.Connection]:
    """Yield a read-only connection. Closed after the request."""
    conn = dblib.connect(_db_path(), read_only=True)
    try:
        yield conn
    finally:
        conn.close()
