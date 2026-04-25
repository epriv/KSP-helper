"""Phase 3 comm network calculator tests."""

from math import radians

import pytest

from ksp_planner.comms import (
    comm_network_report,
    comm_range,
    min_sats_for_coverage,
    orbit_for_coverage,
    resonant_deploy,
    sat_separation,
)
from ksp_planner.db import get_antenna, get_body, get_dsn

# --------------------------------------------------------------------- #
#  Canonical worked example (see docs/features/comm-network.md)          #
# --------------------------------------------------------------------- #


def test_worked_example_3_sats_kerbin_ra15_dsn2(db):
    """3 sats at Kerbin, RA-15, DSN Lvl 2, 5° min elevation."""
    kerbin = get_body(db, "kerbin")
    ra15 = get_antenna(db, "RA-15 Relay Antenna")
    dsn2 = get_dsn(db, 2)

    r = comm_network_report(kerbin, 3, ra15, dsn2, min_elev_deg=5.0)

    assert r["body"] == "kerbin"
    assert r["n_sats"] == 3
    assert r["antenna"] == "RA-15 Relay Antenna"
    assert r["dsn_level"] == 2
    assert r["min_elev_deg"] == 5.0

    assert r["orbit_altitude_m"] == pytest.approx(814_318, abs=1)
    assert r["orbit_radius_m"] == pytest.approx(1_414_318, abs=1)
    assert r["period_s"] == pytest.approx(5623.6, abs=0.2)

    assert r["range_sat_to_sat_m"] == pytest.approx(1.5e10)
    assert r["range_sat_to_dsn_m"] == pytest.approx(2.7386128e10, rel=1e-6)
    assert r["sat_separation_m"] == pytest.approx(2_449_671, abs=1)

    assert r["coverage_ok"] is True
    assert r["coverage_margin_m"] == pytest.approx(r["range_sat_to_sat_m"] - r["sat_separation_m"])
    assert r["suggestion"] == ""


# --------------------------------------------------------------------- #
#  Primitive helpers                                                     #
# --------------------------------------------------------------------- #


def test_comm_range_symmetric():
    assert comm_range(1e10, 5e10) == pytest.approx(comm_range(5e10, 1e10))


def test_comm_range_self_equals_input():
    """sqrt(P × P) = P — the antenna's self-range equals its reference range."""
    assert comm_range(1.5e10, 1.5e10) == pytest.approx(1.5e10)


def test_orbit_for_coverage_matches_formula():
    """Spot-check: Kerbin R=600 km, N=3, ε=5° → orbit_r ≈ 1414.32 km."""
    orbit_r = orbit_for_coverage(600_000, 3, radians(5.0))
    assert orbit_r == pytest.approx(1_414_318, abs=1)


def test_sat_separation_n3_is_chord_of_equilateral_triangle():
    """3 sats at radius R: chord = R × sqrt(3)."""
    import math
    orbit_r = 1_000_000
    assert sat_separation(orbit_r, 3) == pytest.approx(orbit_r * math.sqrt(3))


# --------------------------------------------------------------------- #
#  Edge cases                                                            #
# --------------------------------------------------------------------- #


def test_two_sats_infeasible_with_positive_elevation():
    """N=2 with ε>0 is geometrically impossible."""
    with pytest.raises(ValueError, match="impossible"):
        orbit_for_coverage(600_000, 2, radians(5.0))


def test_one_sat_rejected():
    with pytest.raises(ValueError, match="at least 2"):
        orbit_for_coverage(600_000, 1, radians(5.0))


def test_coverage_fails_at_jool_with_weak_antenna(db):
    """Communotron 16 (500 km range) at Jool can't reach across the constellation."""
    jool = get_body(db, "jool")
    c16 = get_antenna(db, "Communotron 16")
    dsn1 = get_dsn(db, 1)
    r = comm_network_report(jool, 3, c16, dsn1, 5.0)
    assert r["coverage_ok"] is False
    assert r["coverage_margin_m"] < 0
    assert "add sats" in r["suggestion"]


def test_gilly_tiny_body(db):
    """Gilly (R=13 km) with RA-2 — massive margin."""
    gilly = get_body(db, "gilly")
    ra2 = get_antenna(db, "RA-2 Relay Antenna")
    dsn3 = get_dsn(db, 3)
    r = comm_network_report(gilly, 3, ra2, dsn3, 5.0)
    assert r["coverage_ok"] is True
    assert r["orbit_radius_m"] < 50_000
    assert r["coverage_margin_m"] > 1e9


def test_jool_big_body(db):
    """Jool (R=6000 km) with RA-15 — should still work at reasonable orbit."""
    jool = get_body(db, "jool")
    ra15 = get_antenna(db, "RA-15 Relay Antenna")
    dsn2 = get_dsn(db, 2)
    r = comm_network_report(jool, 3, ra15, dsn2, 5.0)
    assert r["coverage_ok"] is True


# --------------------------------------------------------------------- #
#  Inverse relationship between orbit_for_coverage and min_sats         #
# --------------------------------------------------------------------- #


@pytest.mark.parametrize("n_sats", [3, 4, 6, 8, 12])
def test_orbit_for_coverage_is_inverse_of_min_sats(n_sats):
    """Computing altitude from N, then inferring N back, should agree."""
    body_r = 600_000
    elev = radians(5.0)
    orbit_r = orbit_for_coverage(body_r, n_sats, elev)
    altitude = orbit_r - body_r
    inferred = min_sats_for_coverage(body_r, altitude, elev)
    assert inferred <= n_sats


def test_min_sats_infinite_below_minimum_altitude():
    """Below the geometric minimum altitude for any N, result is inf."""
    from math import isinf
    # For elev=5°, R=600km, orbit_r must exceed R/cos(some threshold)
    # Altitude 0 (surface) is always too low.
    assert isinf(min_sats_for_coverage(600_000, 0, radians(5.0)))


# --------------------------------------------------------------------- #
#  Resonant deploy                                                       #
# --------------------------------------------------------------------- #


def test_resonant_deploy_kerbin_3sat():
    # Canonical: Kerbin 3-sat constellation at 5° elevation gives orbit_r ≈ 1,414,320 m.
    orbit_r = 1_414_320.0
    mu = 3.5316e12
    result = resonant_deploy(orbit_r, 3, mu)
    assert result["ratio"] == "2/3"
    assert result["resonant_period_s"] == pytest.approx(3749, rel=0.01)
    # resonant altitude = resonant_sma_m - Kerbin_radius(600_000 m)
    assert (result["resonant_sma_m"] - 600_000) / 1000 == pytest.approx(479, rel=0.01)


@pytest.mark.parametrize("n,expected", [(3, "2/3"), (4, "3/4"), (5, "4/5"), (6, "5/6")])
def test_resonant_deploy_ratio_string(n, expected):
    result = resonant_deploy(1_000_000, n, 3.5316e12)
    assert result["ratio"] == expected
