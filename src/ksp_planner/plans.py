"""Mission plan persistence.

Plans store the *inputs* to a calculator, not the outputs. Loading a plan runs
the current calculator code against the saved config so formula updates
propagate automatically.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from ksp_planner import db as dblib

VALID_KINDS = frozenset({"comms", "hohmann", "twr", "dv_budget"})


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _writable(db_path: Path) -> sqlite3.Connection:
    return dblib.connect(db_path, read_only=False)


def save(db_path: Path, name: str, kind: str, config: dict) -> dict:
    """Insert or update a plan. Returns the resulting row as a dict."""
    if kind not in VALID_KINDS:
        raise ValueError(f"unknown plan kind: {kind!r}")
    if not name.strip():
        raise ValueError("name must not be empty")

    config_json = json.dumps(config, sort_keys=True)
    now = _now_iso()

    with _writable(db_path) as conn:
        existing = conn.execute(
            "SELECT id, created_at FROM plans WHERE name = ?", (name,)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE plans SET kind = ?, config_json = ?, updated_at = ? WHERE name = ?",
                (kind, config_json, now, name),
            )
        else:
            conn.execute(
                "INSERT INTO plans (name, kind, config_json, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (name, kind, config_json, now, now),
            )
        conn.commit()
    return load(db_path, name)


def load(db_path: Path, name: str) -> dict:
    with dblib.connect(db_path, read_only=True) as conn:
        row = conn.execute("SELECT * FROM plans WHERE name = ?", (name,)).fetchone()
    if row is None:
        raise KeyError(f"no plan named {name!r}")
    return {**dict(row), "config": json.loads(row["config_json"])}


def list_all(db_path: Path) -> list[dict]:
    with dblib.connect(db_path, read_only=True) as conn:
        rows = conn.execute("SELECT * FROM plans ORDER BY name").fetchall()
    return [{**dict(r), "config": json.loads(r["config_json"])} for r in rows]


def delete(db_path: Path, name: str) -> bool:
    """Delete a plan by name. Returns True if a row was removed."""
    with _writable(db_path) as conn:
        cur = conn.execute("DELETE FROM plans WHERE name = ?", (name,))
        conn.commit()
        return cur.rowcount > 0
