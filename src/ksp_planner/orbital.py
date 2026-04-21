"""Orbital mechanics — pure functions.

All inputs and outputs in SI units: metres, seconds, m³/s² for μ.
"""

from __future__ import annotations

from math import log, pi, sqrt

G0 = 9.80665  # standard gravitational acceleration, used for Isp conversions


def orbital_period(sma_m: float, mu: float) -> float:
    """Kepler's third law: T = 2π × sqrt(a³/μ)."""
    return 2 * pi * sqrt(sma_m ** 3 / mu)


def vis_viva(sma_m: float, r_m: float, mu: float) -> float:
    """Orbital speed at radius r on an orbit of semi-major axis a: v = sqrt(μ(2/r − 1/a))."""
    return sqrt(mu * (2 / r_m - 1 / sma_m))


def escape_velocity(r_m: float, mu: float) -> float:
    """Minimum speed to escape the parent body's gravity from radius r."""
    return sqrt(2 * mu / r_m)


def surface_gravity(mu: float, radius_m: float) -> float:
    """g = μ/r² at the body's surface."""
    return mu / radius_m ** 2


def sync_orbit_radius(mu: float, rotation_period_s: float) -> float:
    """Radius at which orbital period equals the body's sidereal day."""
    return (mu * rotation_period_s ** 2 / (4 * pi ** 2)) ** (1 / 3)


def hohmann_dv(r1_m: float, r2_m: float, mu: float) -> tuple[float, float, float]:
    """Two-impulse Hohmann transfer between two coplanar circular orbits.

    Returns (dv_departure, dv_arrival, dv_total) in m/s — always non-negative.
    Works regardless of which radius is larger.
    """
    a_trans = (r1_m + r2_m) / 2
    v_circ_1 = sqrt(mu / r1_m)
    v_circ_2 = sqrt(mu / r2_m)
    v_trans_at_1 = sqrt(mu * (2 / r1_m - 1 / a_trans))
    v_trans_at_2 = sqrt(mu * (2 / r2_m - 1 / a_trans))
    dv1 = abs(v_trans_at_1 - v_circ_1)
    dv2 = abs(v_circ_2 - v_trans_at_2)
    return dv1, dv2, dv1 + dv2


def hill_sphere(sma_m: float, ecc: float, mu_body: float, mu_parent: float) -> float:
    """Hill sphere: a(1−e) × (μ/(3 μ_parent))^(1/3)."""
    return sma_m * (1 - ecc) * (mu_body / (3 * mu_parent)) ** (1 / 3)


def tsiolkovsky_dv(isp_s: float, wet_kg: float, dry_kg: float) -> float:
    """Ideal rocket equation: Δv = Isp × g₀ × ln(m_wet / m_dry)."""
    if dry_kg <= 0 or wet_kg <= dry_kg:
        raise ValueError("wet mass must exceed dry mass and both must be positive")
    return isp_s * G0 * log(wet_kg / dry_kg)


def tsiolkovsky_mass_ratio(dv_m_s: float, isp_s: float) -> float:
    """Inverse Tsiolkovsky: m_wet / m_dry needed to deliver Δv at given Isp."""
    from math import exp
    return exp(dv_m_s / (isp_s * G0))


def twr(thrust_n: float, mass_kg: float, g_m_s2: float) -> float:
    """Thrust-to-weight ratio at the given local gravity."""
    return thrust_n / (mass_kg * g_m_s2)


def burn_time(wet_kg: float, dry_kg: float, isp_s: float, thrust_n: float) -> float:
    """Burn duration at constant thrust: (m_wet − m_dry) × Isp × g₀ / thrust."""
    return (wet_kg - dry_kg) * isp_s * G0 / thrust_n


def interbody_hohmann(
    *,
    mu_parent: float,
    sma_source_m: float,
    sma_target_m: float,
    mu_source_body: float,
    r_parking_source_m: float,
    mu_target_body: float,
    r_parking_target_m: float,
) -> dict:
    """Patched-conics Hohmann between two bodies orbiting a common parent.

    Models the trip as (1) ejection from a circular parking orbit at the source,
    (2) heliocentric Hohmann from source's orbit to target's orbit, (3) insertion
    into a circular parking orbit at the target. All orbits assumed coplanar.
    """
    # Parent-frame transfer orbit.
    a_trans = (sma_source_m + sma_target_m) / 2
    v_src_circ = sqrt(mu_parent / sma_source_m)
    v_tgt_circ = sqrt(mu_parent / sma_target_m)
    v_trans_at_src = sqrt(mu_parent * (2 / sma_source_m - 1 / a_trans))
    v_trans_at_tgt = sqrt(mu_parent * (2 / sma_target_m - 1 / a_trans))

    # Hyperbolic excess needed at each SOI boundary.
    v_hyp_source = abs(v_trans_at_src - v_src_circ)
    v_hyp_target = abs(v_tgt_circ - v_trans_at_tgt)

    # Ejection / insertion burns: boost from circular parking onto a hyperbolic trajectory.
    v_park_src = sqrt(mu_source_body / r_parking_source_m)
    dv_eject = sqrt(v_hyp_source ** 2 + 2 * mu_source_body / r_parking_source_m) - v_park_src

    v_park_tgt = sqrt(mu_target_body / r_parking_target_m)
    dv_insert = sqrt(v_hyp_target ** 2 + 2 * mu_target_body / r_parking_target_m) - v_park_tgt

    return {
        "dv_eject_m_s": dv_eject,
        "dv_insert_m_s": dv_insert,
        "dv_total_m_s": dv_eject + dv_insert,
        "transfer_time_s": pi * sqrt(a_trans ** 3 / mu_parent),
        "v_hyp_source_m_s": v_hyp_source,
        "v_hyp_target_m_s": v_hyp_target,
    }
