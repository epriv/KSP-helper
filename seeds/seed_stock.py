"""Seed ksp.db with stock KSP1 values.

Bodies come from seeds/data/bodies.ini (KSPTOT, verbatim).
Antennas and DSN are inlined below with source citations.

Run via:  make seed    (or)    uv run python -m seeds.seed_stock
"""

from __future__ import annotations

import configparser
import sqlite3
from math import pi
from pathlib import Path

SCHEMA_SQL = Path(__file__).parent / "schema.sql"
BODIES_INI = Path(__file__).parent / "data" / "bodies.ini"

# KSPTOT names "Sun" what KSP's UI calls "Kerbol". Display keeps Kerbol.
KSPTOT_NAME_MAP = {"Sun": "Kerbol"}

# Oxygen atmosphere → only Kerbin and Laythe in stock.
OXYGEN_ATMOSPHERES = {"kerbin", "laythe"}

# Antenna reference range (antennaPower in KSP, unit = metres).
# Source: Kerbalism/Kerbalism Patches-Antennas.cfg comment table (stock KSP 1.8+).
# Shape: (name, range_m, is_relay, combinable)
# `combinable` reflects the stock antennaCombinable flag; directional dishes are not combinable.
ANTENNAS: list[tuple[str, float, bool, bool]] = [
    ("Communotron 16-S",       5.0e5,  False, False),
    ("Communotron 16",         5.0e5,  False, True),
    ("Communotron DTS-M1",     2.0e9,  False, True),
    ("Communotron HG-55",      1.5e10, False, False),
    ("Communotron 88-88",      1.0e11, False, False),
    ("HG-5 High Gain Antenna", 5.0e6,  True,  True),
    ("RA-2 Relay Antenna",     2.0e9,  True,  True),
    ("RA-15 Relay Antenna",    1.5e10, True,  True),
    ("RA-100 Relay Antenna",   1.0e11, True,  True),
]

# Source: sarbian/CustomBarnKit default.cfg, TRACKING.DSNRange (stock mirror).
DSN_LEVELS: list[tuple[int, float]] = [
    (1, 2.0e9),
    (2, 5.0e10),
    (3, 2.5e11),
]


def km_to_m(km: float | str) -> float:
    return float(km) * 1000.0


def kmmu_to_simu(gm_km: float | str) -> float:
    """Convert km³/s² → m³/s²."""
    return float(gm_km) * 1.0e9


def compute_soi_m(sma_m: float, mu_body: float, mu_parent: float) -> float:
    """Laplace sphere of influence: a × (μ/μ_parent)^(2/5)."""
    return sma_m * (mu_body / mu_parent) ** 0.4


def sync_orbit_radius_m(mu: float, rotation_period_s: float) -> float:
    """Kepler's third law: r = (μ T² / (4π²))^(1/3)."""
    return (mu * rotation_period_s ** 2 / (4.0 * pi ** 2)) ** (1.0 / 3.0)


def classify_body_type(ksptot_name: str, parent_name: str | None) -> str:
    if parent_name is None:
        return "star"
    if parent_name == "Sun":
        return "planet"
    return "moon"


def seed(db_path: Path) -> None:
    db_path = Path(db_path)
    if db_path.exists():
        db_path.unlink()

    cp = configparser.ConfigParser(strict=False)
    cp.read(BODIES_INI)

    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(SCHEMA_SQL.read_text())
        cur = conn.cursor()

        # First pass: insert bodies without parent_id/soi (we need the IDs first).
        # `ksptot_meta[section] = (body_id, parent_ksptot, mu_body, sma_m_or_None)`
        ksptot_meta: dict[str, tuple[int, str | None, float, float | None]] = {}

        for section in cp.sections():
            body = {k.lower(): v for k, v in cp.items(section)}
            parent = body.get("parent", "").strip() or None

            name = KSPTOT_NAME_MAP.get(section, section)
            slug = name.lower()
            mu = kmmu_to_simu(body["gm"])
            radius = km_to_m(body["radius"])
            atm_hgt_km = float(body.get("atmohgt", 0) or 0)
            atm_height = km_to_m(atm_hgt_km) if atm_hgt_km > 0 else None
            has_oxygen = 1 if slug in OXYGEN_ATMOSPHERES else 0
            rot = float(body.get("rotperiod", 0) or 0)
            sidereal = rot if rot > 0 else None
            sync_r = sync_orbit_radius_m(mu, sidereal) if sidereal else None
            body_type = classify_body_type(section, parent)

            cur.execute(
                """INSERT INTO bodies
                       (name, slug, body_type, radius_m, mu_m3s2,
                        atm_height_m, has_oxygen, sidereal_day_s, sync_orbit_m)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (name, slug, body_type, radius, mu,
                 atm_height, has_oxygen, sidereal, sync_r),
            )
            sma_m = km_to_m(body["sma"]) if parent else None
            ksptot_meta[section] = (cur.lastrowid, parent, mu, sma_m)

        # Second pass: wire parent_id, compute SOI, insert orbit row.
        for section, (body_id, parent_name, mu_body, sma_m) in ksptot_meta.items():
            if parent_name is None:
                continue
            parent_id, _, mu_parent, _ = ksptot_meta[parent_name]
            soi = compute_soi_m(sma_m, mu_body, mu_parent)
            cur.execute(
                "UPDATE bodies SET parent_id = ?, soi_m = ? WHERE id = ?",
                (parent_id, soi, body_id),
            )
            body = {k.lower(): v for k, v in cp.items(section)}
            cur.execute(
                """INSERT INTO orbits
                       (body_id, sma_m, eccentricity, inclination_deg,
                        arg_periapsis_deg, lan_deg, mean_anomaly_epoch_deg, epoch_s)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    body_id,
                    sma_m,
                    float(body.get("ecc", 0) or 0),
                    float(body.get("inc", 0) or 0),
                    float(body.get("arg", 0) or 0),
                    float(body.get("raan", 0) or 0),
                    float(body.get("mean", 0) or 0),
                    float(body.get("epoch", 0) or 0),
                ),
            )

        for name, range_m, is_relay, combinable in ANTENNAS:
            cur.execute(
                "INSERT INTO antennas (name, range_m, is_relay, combinable) VALUES (?, ?, ?, ?)",
                (name, range_m, int(is_relay), int(combinable)),
            )

        for level, range_m in DSN_LEVELS:
            cur.execute(
                "INSERT INTO dsn_levels (level, range_m) VALUES (?, ?)",
                (level, range_m),
            )

        conn.commit()
    finally:
        conn.close()


def main() -> None:
    target = Path.cwd() / "ksp.db"
    seed(target)
    print(f"Seeded {target}")


if __name__ == "__main__":
    main()
