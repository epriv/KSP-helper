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

# Δv chart — community Δv map values, normalised to a tree.
#
# Source: KSP community Δv map (Cuky's "Kerbin System Δv" subway-style chart),
# https://wiki.kerbalspaceprogram.com/wiki/Cheat_sheet#Delta-V_map
#
# Convention (chosen so Kerbin-departure totals match the chart):
#   - Kerbin trunk (kerbol_orbit ↔ kerbin_transfer ↔ kerbin_capture ↔ kerbin_LO): all 0.
#     The Kerbin SOI is the de-facto reference frame for the chart; LKO is the
#     baseline parking orbit for every "LKO → X" interplanetary number.
#   - For each planet other than Kerbin:
#       (kerbol_orbit ↔ planet_transfer)        : 0 (semantic)
#       (planet_transfer ↔ planet_capture)      : chart "LKO → planet" ejection
#       (planet_capture ↔ planet_low_orbit)     : chart capture burn at planet
#       (planet_low_orbit ↔ planet_surface)     : chart ascent/descent
#   - Mun & Minmus skip the capture node (per the design doc tree art); their
#     `<moon>_transfer ↔ <moon>_low_orbit` edge carries the capture burn.
#   - `aerobrake_on_descent` marks only real aerobraking venues (ballistic cost
#     discountable by atmospheric entry). Capture→LO edges whose chart value
#     already encodes aerocapture (Eve 80, Duna 360, Kerbin 0) use False to
#     prevent double-credit when `aerobrake=True` — they are already discounted
#     at the data-source level.
#   - Edges are seeded as adjacencies (parent, child, down_dv, up_dv, aerobrake_on_descent).
#     Two directed `dv_edges` rows are inserted per adjacency.
#
# `body_slug` ties a node to a `bodies.slug` row (NULL for abstract nodes like
# kerbol_orbit). `state` is one of the schema CHECK values.

# (slug, body_slug, state, parent_slug)
DV_NODES: list[tuple[str, str | None, str, str | None]] = [
    ("kerbol_orbit",     None,     "sun_orbit", None),

    # Moho
    ("moho_transfer",    "moho",   "transfer",  "kerbol_orbit"),
    ("moho_capture",     "moho",   "capture",   "moho_transfer"),
    ("moho_low_orbit",   "moho",   "low_orbit", "moho_capture"),
    ("moho_surface",     "moho",   "surface",   "moho_low_orbit"),

    # Eve + Gilly
    ("eve_transfer",     "eve",    "transfer",  "kerbol_orbit"),
    ("eve_capture",      "eve",    "capture",   "eve_transfer"),
    ("eve_low_orbit",    "eve",    "low_orbit", "eve_capture"),
    ("eve_surface",      "eve",    "surface",   "eve_low_orbit"),
    ("gilly_transfer",   "gilly",  "transfer",  "eve_low_orbit"),
    ("gilly_capture",    "gilly",  "capture",   "gilly_transfer"),
    ("gilly_low_orbit",  "gilly",  "low_orbit", "gilly_capture"),
    ("gilly_surface",    "gilly",  "surface",   "gilly_low_orbit"),

    # Kerbin trunk (zero-cost; kerbol_orbit ↔ kerbin_LO is semantic only)
    ("kerbin_transfer",  "kerbin", "transfer",  "kerbol_orbit"),
    ("kerbin_capture",   "kerbin", "capture",   "kerbin_transfer"),
    ("kerbin_low_orbit", "kerbin", "low_orbit", "kerbin_capture"),
    ("kerbin_surface",   "kerbin", "surface",   "kerbin_low_orbit"),

    # Mun & Minmus (no capture node; per design doc tree art)
    ("mun_transfer",     "mun",    "transfer",  "kerbin_low_orbit"),
    ("mun_low_orbit",    "mun",    "low_orbit", "mun_transfer"),
    ("mun_surface",      "mun",    "surface",   "mun_low_orbit"),
    ("minmus_transfer",  "minmus", "transfer",  "kerbin_low_orbit"),
    ("minmus_low_orbit", "minmus", "low_orbit", "minmus_transfer"),
    ("minmus_surface",   "minmus", "surface",   "minmus_low_orbit"),

    # Duna + Ike
    ("duna_transfer",    "duna",   "transfer",  "kerbol_orbit"),
    ("duna_capture",     "duna",   "capture",   "duna_transfer"),
    ("duna_low_orbit",   "duna",   "low_orbit", "duna_capture"),
    ("duna_surface",     "duna",   "surface",   "duna_low_orbit"),
    ("ike_transfer",     "ike",    "transfer",  "duna_low_orbit"),
    ("ike_capture",      "ike",    "capture",   "ike_transfer"),
    ("ike_low_orbit",    "ike",    "low_orbit", "ike_capture"),
    ("ike_surface",      "ike",    "surface",   "ike_low_orbit"),

    # Dres
    ("dres_transfer",    "dres",   "transfer",  "kerbol_orbit"),
    ("dres_capture",     "dres",   "capture",   "dres_transfer"),
    ("dres_low_orbit",   "dres",   "low_orbit", "dres_capture"),
    ("dres_surface",     "dres",   "surface",   "dres_low_orbit"),

    # Jool + 5 moons (no jool_surface — gas giant)
    ("jool_transfer",    "jool",   "transfer",  "kerbol_orbit"),
    ("jool_capture",     "jool",   "capture",   "jool_transfer"),
    ("jool_low_orbit",   "jool",   "low_orbit", "jool_capture"),
    ("laythe_transfer",  "laythe", "transfer",  "jool_low_orbit"),
    ("laythe_capture",   "laythe", "capture",   "laythe_transfer"),
    ("laythe_low_orbit", "laythe", "low_orbit", "laythe_capture"),
    ("laythe_surface",   "laythe", "surface",   "laythe_low_orbit"),
    ("vall_transfer",    "vall",   "transfer",  "jool_low_orbit"),
    ("vall_capture",     "vall",   "capture",   "vall_transfer"),
    ("vall_low_orbit",   "vall",   "low_orbit", "vall_capture"),
    ("vall_surface",     "vall",   "surface",   "vall_low_orbit"),
    ("tylo_transfer",    "tylo",   "transfer",  "jool_low_orbit"),
    ("tylo_capture",     "tylo",   "capture",   "tylo_transfer"),
    ("tylo_low_orbit",   "tylo",   "low_orbit", "tylo_capture"),
    ("tylo_surface",     "tylo",   "surface",   "tylo_low_orbit"),
    ("bop_transfer",     "bop",    "transfer",  "jool_low_orbit"),
    ("bop_capture",      "bop",    "capture",   "bop_transfer"),
    ("bop_low_orbit",    "bop",    "low_orbit", "bop_capture"),
    ("bop_surface",      "bop",    "surface",   "bop_low_orbit"),
    ("pol_transfer",     "pol",    "transfer",  "jool_low_orbit"),
    ("pol_capture",      "pol",    "capture",   "pol_transfer"),
    ("pol_low_orbit",    "pol",    "low_orbit", "pol_capture"),
    ("pol_surface",      "pol",    "surface",   "pol_low_orbit"),

    # Eeloo
    ("eeloo_transfer",   "eeloo",  "transfer",  "kerbol_orbit"),
    ("eeloo_capture",    "eeloo",  "capture",   "eeloo_transfer"),
    ("eeloo_low_orbit",  "eeloo",  "low_orbit", "eeloo_capture"),
    ("eeloo_surface",    "eeloo",  "surface",   "eeloo_low_orbit"),
]

# (parent_slug, child_slug, down_dv_m_s, up_dv_m_s, aerobrake_on_descent)
# Two directed `dv_edges` rows are seeded per row (parent→child = down, child→parent = up).
# `aerobrake_on_descent` only annotates the parent→child direction.
DV_ADJACENCIES: list[tuple[str, str, float, float, bool]] = [
    # Kerbin trunk — all zero (LKO is the chart's baseline parking orbit)
    ("kerbol_orbit",     "kerbin_transfer",  0,    0,    False),
    ("kerbin_transfer",  "kerbin_capture",   0,    0,    False),
    ("kerbin_capture",   "kerbin_low_orbit", 0,    0,    False),  # pre-baked aerocapture
    ("kerbin_low_orbit", "kerbin_surface",   3400, 3400, True),   # asc 3400, desc 0 w/ aero

    # Mun (no capture node — capture burn folded into transfer→LO edge)
    ("kerbin_low_orbit", "mun_transfer",     860,  860,  False),
    ("mun_transfer",     "mun_low_orbit",    310,  310,  False),
    ("mun_low_orbit",    "mun_surface",      580,  580,  False),

    # Minmus
    ("kerbin_low_orbit", "minmus_transfer",  930,  930,  False),
    ("minmus_transfer",  "minmus_low_orbit", 160,  160,  False),
    ("minmus_low_orbit", "minmus_surface",   180,  180,  False),

    # Moho
    ("kerbol_orbit",     "moho_transfer",    0,    0,    False),
    ("moho_transfer",    "moho_capture",     2520, 2520, False),
    ("moho_capture",     "moho_low_orbit",   2410, 2410, False),
    ("moho_low_orbit",   "moho_surface",     870,  870,  False),

    # Eve
    ("kerbol_orbit",     "eve_transfer",     0,    0,    False),
    ("eve_transfer",     "eve_capture",      1080, 1080, False),
    ("eve_capture",      "eve_low_orbit",    80,   80,   False),  # pre-baked aerocapture
    ("eve_low_orbit",    "eve_surface",      8000, 8000, True),   # brutal asc, aerobrake desc
    # Gilly (under Eve LO; no capture cost effectively)
    ("eve_low_orbit",    "gilly_transfer",   60,   60,   False),
    ("gilly_transfer",   "gilly_capture",    0,    0,    False),
    ("gilly_capture",    "gilly_low_orbit",  410,  410,  False),
    ("gilly_low_orbit",  "gilly_surface",    30,   30,   False),

    # Duna
    ("kerbol_orbit",     "duna_transfer",    0,    0,    False),
    ("duna_transfer",    "duna_capture",     1060, 1060, False),
    ("duna_capture",     "duna_low_orbit",   360,  360,  False),  # pre-baked aerocapture
    ("duna_low_orbit",   "duna_surface",     1450, 1450, True),   # Duna descent aerobrake → ~250
    # Ike
    ("duna_low_orbit",   "ike_transfer",     30,   30,   False),
    ("ike_transfer",     "ike_capture",      0,    0,    False),
    ("ike_capture",      "ike_low_orbit",    180,  180,  False),
    ("ike_low_orbit",    "ike_surface",      390,  390,  False),

    # Dres
    ("kerbol_orbit",     "dres_transfer",    0,    0,    False),
    ("dres_transfer",    "dres_capture",     1140, 1140, False),
    ("dres_capture",     "dres_low_orbit",   1290, 1290, False),
    ("dres_low_orbit",   "dres_surface",     430,  430,  False),

    # Jool (no surface)
    ("kerbol_orbit",     "jool_transfer",    0,    0,    False),
    ("jool_transfer",    "jool_capture",     1980, 1980, True),   # Jool aerocapture possible
    ("jool_capture",     "jool_low_orbit",   2810, 2810, True),
    # Jool moons branch off jool_low_orbit
    ("jool_low_orbit",   "laythe_transfer",  240,  240,  False),
    ("laythe_transfer",  "laythe_capture",   0,    0,    False),
    ("laythe_capture",   "laythe_low_orbit", 1070, 1070, True),   # Laythe atmosphere
    ("laythe_low_orbit", "laythe_surface",   2900, 2900, True),
    ("jool_low_orbit",   "vall_transfer",    620,  620,  False),
    ("vall_transfer",    "vall_capture",     0,    0,    False),
    ("vall_capture",     "vall_low_orbit",   910,  910,  False),
    ("vall_low_orbit",   "vall_surface",     860,  860,  False),
    ("jool_low_orbit",   "tylo_transfer",    400,  400,  False),
    ("tylo_transfer",    "tylo_capture",     0,    0,    False),
    ("tylo_capture",     "tylo_low_orbit",   1100, 1100, False),
    ("tylo_low_orbit",   "tylo_surface",     2270, 2270, False),
    ("jool_low_orbit",   "bop_transfer",     220,  220,  False),
    ("bop_transfer",     "bop_capture",      0,    0,    False),
    ("bop_capture",      "bop_low_orbit",    900,  900,  False),
    ("bop_low_orbit",    "bop_surface",      220,  220,  False),
    ("jool_low_orbit",   "pol_transfer",     160,  160,  False),
    ("pol_transfer",     "pol_capture",      0,    0,    False),
    ("pol_capture",      "pol_low_orbit",    820,  820,  False),
    ("pol_low_orbit",    "pol_surface",      130,  130,  False),

    # Eeloo
    ("kerbol_orbit",     "eeloo_transfer",   0,    0,    False),
    ("eeloo_transfer",   "eeloo_capture",    1370, 1370, False),
    ("eeloo_capture",    "eeloo_low_orbit",  1330, 1330, False),
    ("eeloo_low_orbit",  "eeloo_surface",    620,  620,  False),
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

        # Δv chart: nodes first (parent_slug FK self-references; insert in tree order).
        body_id_by_slug = {
            slug: body_id for slug, body_id in cur.execute("SELECT slug, id FROM bodies")
        }
        for slug, body_slug, state, parent_slug in DV_NODES:
            body_id = body_id_by_slug[body_slug] if body_slug else None
            cur.execute(
                "INSERT INTO dv_nodes (slug, body_id, state, parent_slug) VALUES (?, ?, ?, ?)",
                (slug, body_id, state, parent_slug),
            )
        for parent, child, down_dv, up_dv, aerobrake in DV_ADJACENCIES:
            cur.execute(
                "INSERT INTO dv_edges (from_slug, to_slug, dv_m_s, can_aerobrake) "
                "VALUES (?, ?, ?, ?)",
                (parent, child, float(down_dv), int(aerobrake)),
            )
            cur.execute(
                "INSERT INTO dv_edges (from_slug, to_slug, dv_m_s, can_aerobrake) "
                "VALUES (?, ?, ?, ?)",
                (child, parent, float(up_dv), 0),
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
