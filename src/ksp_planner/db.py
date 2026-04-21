"""Read-only query helpers for ksp.db."""

from __future__ import annotations

import sqlite3
from pathlib import Path

DEFAULT_DB_PATH = Path("ksp.db")


def connect(db_path: Path | str | None = None, *, read_only: bool = True) -> sqlite3.Connection:
    path = Path(db_path) if db_path else DEFAULT_DB_PATH
    conn = (
        sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        if read_only
        else sqlite3.connect(path)
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_body(conn: sqlite3.Connection, slug: str) -> dict:
    row = conn.execute(
        """SELECT b.*,
                  o.sma_m, o.eccentricity, o.inclination_deg,
                  o.arg_periapsis_deg, o.lan_deg,
                  o.mean_anomaly_epoch_deg, o.epoch_s
           FROM bodies b
           LEFT JOIN orbits o ON o.body_id = b.id
           WHERE b.slug = ?""",
        (slug,),
    ).fetchone()
    if row is None:
        raise KeyError(f"No body with slug {slug!r}")
    return dict(row)


def list_bodies(conn: sqlite3.Connection, body_type: str | None = None) -> list[dict]:
    if body_type is None:
        rows = conn.execute("SELECT * FROM bodies ORDER BY id").fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM bodies WHERE body_type = ? ORDER BY id",
            (body_type,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_antenna(conn: sqlite3.Connection, name: str) -> dict:
    row = conn.execute("SELECT * FROM antennas WHERE name = ?", (name,)).fetchone()
    if row is None:
        raise KeyError(f"No antenna named {name!r}")
    return dict(row)


def list_antennas(conn: sqlite3.Connection) -> list[dict]:
    return [dict(r) for r in conn.execute("SELECT * FROM antennas ORDER BY id")]


def get_dsn(conn: sqlite3.Connection, level: int) -> dict:
    row = conn.execute("SELECT * FROM dsn_levels WHERE level = ?", (level,)).fetchone()
    if row is None:
        raise KeyError(f"No DSN level {level!r}")
    return dict(row)
