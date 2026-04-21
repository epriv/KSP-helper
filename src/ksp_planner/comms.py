"""Comm network calculator — pure functions.

All distances in metres, angles in radians unless the name says `_deg`.
"""

from __future__ import annotations

from math import acos, ceil, cos, degrees, inf, pi, radians, sin, sqrt

from ksp_planner.orbital import orbital_period


def comm_range(range_a_m: float, range_b_m: float) -> float:
    """Max link distance between two endpoints — geometric mean of their reference ranges."""
    return sqrt(range_a_m * range_b_m)


def orbit_for_coverage(body_radius_m: float, n_sats: int, min_elev_rad: float) -> float:
    """Minimum orbital radius for full coverage by N evenly spaced sats at min elevation ε.

    Raises ValueError when the geometry makes coverage impossible (e.g. N=2 with ε>0).
    """
    if n_sats < 2:
        raise ValueError("need at least 2 satellites")
    half_angle = pi / n_sats
    denom = cos(half_angle + min_elev_rad)
    if denom <= 0:
        raise ValueError(
            f"coverage geometrically impossible: N={n_sats} sats at "
            f"elev={degrees(min_elev_rad):.1f}° would require an unbounded orbit"
        )
    return body_radius_m * cos(min_elev_rad) / denom


def sat_separation(orbit_radius_m: float, n_sats: int) -> float:
    """Chord distance between adjacent sats in an evenly spaced N-gon constellation."""
    return 2 * orbit_radius_m * sin(pi / n_sats)


def min_sats_for_coverage(
    body_radius_m: float, orbit_altitude_m: float, min_elev_rad: float
) -> float:
    """Smallest N such that N evenly spaced sats at this altitude cover the body.

    Returns `math.inf` if the altitude is below the geometric minimum (the satellite
    would have to be below the horizon at midpoint between neighbours).
    """
    orbit_r = body_radius_m + orbit_altitude_m
    ratio = body_radius_m * cos(min_elev_rad) / orbit_r
    if ratio >= 1:
        return inf
    half_gap = acos(ratio) - min_elev_rad
    if half_gap <= 0:
        return inf
    return ceil(pi / half_gap)


def comm_network_report(
    body: dict,
    n_sats: int,
    antenna: dict,
    dsn: dict,
    min_elev_deg: float = 5.0,
) -> dict:
    """Build a report dict for a target body + constellation configuration."""
    min_elev = radians(min_elev_deg)
    orbit_r = orbit_for_coverage(body["radius_m"], n_sats, min_elev)
    altitude = orbit_r - body["radius_m"]
    sep = sat_separation(orbit_r, n_sats)
    r_sat_sat = comm_range(antenna["range_m"], antenna["range_m"])
    r_sat_dsn = comm_range(antenna["range_m"], dsn["range_m"])
    period = orbital_period(orbit_r, body["mu_m3s2"])
    coverage_ok = sep < r_sat_sat
    margin = r_sat_sat - sep
    suggestion = (
        ""
        if coverage_ok
        else (
            f"sat separation ({sep/1000:,.1f} km) exceeds antenna range "
            f"({r_sat_sat/1000:,.1f} km) — add sats or pick a stronger antenna"
        )
    )
    return {
        "body": body["slug"],
        "n_sats": n_sats,
        "antenna": antenna["name"],
        "dsn_level": dsn["level"],
        "min_elev_deg": min_elev_deg,
        "orbit_altitude_m": altitude,
        "orbit_radius_m": orbit_r,
        "period_s": period,
        "range_sat_to_sat_m": r_sat_sat,
        "range_sat_to_dsn_m": r_sat_dsn,
        "sat_separation_m": sep,
        "coverage_ok": coverage_ok,
        "coverage_margin_m": margin,
        "suggestion": suggestion,
    }
