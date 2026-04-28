"""Polar scanning orbit optimizer — pure functions.

Finds non-resonant 'sweet spot' altitudes for polar scanning orbits.
A resonant orbit repeats the same ground tracks after p orbits per q body
rotations, leaving permanent gaps. Non-resonant orbits fill coverage
quasi-uniformly over time.

All inputs in SI units (metres, seconds). Altitude-km fields in SweetSpot
are convenience outputs only.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class SweetSpot:
    altitude_km: float
    period_s: float
    swath_km: float
    shift_km: float
    orbits_per_day: float
    days_to_coverage: float
    resonant: bool
    resonant_ratio: str  # "p/q" if resonant, "" otherwise


def swath_width_m(altitude_m: float, fov_deg: float) -> float:
    """Ground swath width for a nadir-pointing sensor with full-cone FOV fov_deg."""
    return 2.0 * altitude_m * math.tan(math.radians(fov_deg / 2.0))


def ground_track_shift_m(
    body_radius_m: float,
    orbit_period_s: float,
    rotation_period_s: float,
) -> float:
    """Equatorial metres the body rotates under the satellite in one orbital period."""
    return 2.0 * math.pi * body_radius_m * orbit_period_s / rotation_period_s


def is_resonant(
    orbits_per_day: float,
    max_q: int = 12,
    tolerance: float = 0.005,
) -> tuple[bool, str]:
    """Return (True, 'p/q') when orbits_per_day is within tolerance of p/q for q <= max_q.

    A resonant orbit traces the same ground tracks every q rotations, preventing
    full coverage. Tolerance 0.5% (0.005) matches the precision needed to avoid
    near-resonant traps for KSP body rotation periods.
    """
    for q in range(1, max_q + 1):
        p = round(orbits_per_day * q)
        if p > 0 and abs(orbits_per_day - p / q) / orbits_per_day < tolerance:
            return True, f"{p}/{q}"
    return False, ""


def days_to_full_coverage(
    body_radius_m: float,
    altitude_m: float,
    fov_deg: float,
    orbit_period_s: float,
    rotation_period_s: float,
) -> float:
    """Estimate days until a non-resonant polar orbit achieves complete surface coverage.

    Uses the worst-case bound: ceil(circumference / swath) orbits, each covering
    a unique longitudinal strip. Resonant orbits would never complete; call
    is_resonant first and skip them.
    """
    circumference_m = 2.0 * math.pi * body_radius_m
    W_m = swath_width_m(altitude_m, fov_deg)
    if W_m <= 0:
        return float("inf")
    n_orbits = math.ceil(circumference_m / W_m)
    return n_orbits * orbit_period_s / rotation_period_s


def find_sweet_spots(
    body_radius_m: float,
    mu_m3s2: float,
    rotation_period_s: float,
    fov_deg: float,
    *,
    min_alt_m: float = 80_000,
    max_alt_m: float = 2_500_000,
    step_m: float = 1_000,
    max_resonance_q: int = 12,
    resonance_tol: float = 0.005,
    top_n: int = 3,
) -> list[SweetSpot]:
    """Return the top_n non-resonant sweet spots sorted by days to full coverage.

    Iterates altitudes from min_alt_m to max_alt_m in step_m increments (default
    1 km). Filters out resonant orbits, then returns the fastest-covering orbits.
    """
    candidates: list[SweetSpot] = []

    alt_m = min_alt_m
    while alt_m <= max_alt_m:
        sma_m = body_radius_m + alt_m
        T_orb = 2.0 * math.pi * math.sqrt(sma_m**3 / mu_m3s2)
        opd = rotation_period_s / T_orb

        resonant, ratio = is_resonant(opd, max_q=max_resonance_q, tolerance=resonance_tol)
        W_m = swath_width_m(alt_m, fov_deg)
        S_m = ground_track_shift_m(body_radius_m, T_orb, rotation_period_s)
        days = days_to_full_coverage(body_radius_m, alt_m, fov_deg, T_orb, rotation_period_s)

        candidates.append(
            SweetSpot(
                altitude_km=alt_m / 1000,
                period_s=T_orb,
                swath_km=W_m / 1000,
                shift_km=S_m / 1000,
                orbits_per_day=opd,
                days_to_coverage=days,
                resonant=resonant,
                resonant_ratio=ratio,
            )
        )
        alt_m += step_m

    non_resonant = [c for c in candidates if not c.resonant]
    non_resonant.sort(key=lambda c: c.days_to_coverage)
    return non_resonant[:top_n]
