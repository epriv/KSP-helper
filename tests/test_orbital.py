"""Phase 2 orbital mechanics tests.

Canonical values pinned against KSP community numbers + property-based invariants.
"""

import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from ksp_planner.db import get_body
from ksp_planner.orbital import (
    G0,
    burn_time,
    escape_velocity,
    hill_sphere,
    hohmann_dv,
    interbody_hohmann,
    orbital_period,
    surface_gravity,
    sync_orbit_radius,
    tsiolkovsky_dv,
    tsiolkovsky_mass_ratio,
    twr,
    vis_viva,
)

# --------------------------------------------------------------------- #
#  Known-value tests                                                     #
# --------------------------------------------------------------------- #


def test_kerbin_surface_gravity(db):
    k = get_body(db, "kerbin")
    assert surface_gravity(k["mu_m3s2"], k["radius_m"]) == pytest.approx(9.81, rel=1e-3)


def test_mun_escape_velocity(db):
    m = get_body(db, "mun")
    assert escape_velocity(m["radius_m"], m["mu_m3s2"]) == pytest.approx(807, abs=1)


def test_kerbin_sync_orbit_altitude(db):
    """Keostationary altitude — community canonical value is ~2863.33 km."""
    k = get_body(db, "kerbin")
    r = sync_orbit_radius(k["mu_m3s2"], k["sidereal_day_s"])
    assert (r - k["radius_m"]) / 1000 == pytest.approx(2863.33, abs=2)


def test_lko_100km_period(db):
    """100-km Low Kerbin Orbit: T ≈ 1958 s (~32.6 min)."""
    k = get_body(db, "kerbin")
    T = orbital_period(k["radius_m"] + 100_000, k["mu_m3s2"])
    assert T == pytest.approx(1958, abs=5)


def test_hohmann_lko_to_keostationary(db):
    """100-km LKO → keostationary Hohmann total Δv ≈ 1075 m/s."""
    k = get_body(db, "kerbin")
    r_lko = k["radius_m"] + 100_000
    r_keo = k["sync_orbit_m"]
    dv1, dv2, total = hohmann_dv(r_lko, r_keo, k["mu_m3s2"])
    assert total == pytest.approx(1075, abs=5)
    assert dv1 > 0
    assert dv2 > 0


def test_hohmann_100_to_200_km_lko(db):
    """100 km → 200 km circular Kerbin Hohmann: total Δv ≈ 144 m/s."""
    k = get_body(db, "kerbin")
    r1 = k["radius_m"] + 100_000
    r2 = k["radius_m"] + 200_000
    _, _, total = hohmann_dv(r1, r2, k["mu_m3s2"])
    assert total == pytest.approx(144, abs=2)


def test_hohmann_zero_when_radii_equal():
    """Transfer between identical orbits costs nothing."""
    r = 700_000.0
    mu = 3.5316e12
    dv1, dv2, total = hohmann_dv(r, r, mu)
    assert (dv1, dv2, total) == (0.0, 0.0, 0.0)


def test_kerbin_hill_sphere_exceeds_soi(db):
    """Hill sphere should be at least as large as SOI (SOI ⊂ Hill)."""
    k = get_body(db, "kerbin")
    kerbol = get_body(db, "kerbol")
    r_hill = hill_sphere(k["sma_m"], k["eccentricity"], k["mu_m3s2"], kerbol["mu_m3s2"])
    assert r_hill >= k["soi_m"]


# --------------------------------------------------------------------- #
#  Property-based invariants                                             #
# --------------------------------------------------------------------- #

_finite = {"allow_nan": False, "allow_infinity": False}
_sma = st.floats(min_value=1e5, max_value=1e10, **_finite)
_mu = st.floats(min_value=1e10, max_value=1e18, **_finite)


@given(sma=_sma, mu=_mu)
def test_period_monotonic_in_sma(sma, mu):
    assert orbital_period(sma * 1.5, mu) > orbital_period(sma, mu)


@given(sma=_sma, mu=_mu)
def test_vis_viva_circular_identity(sma, mu):
    """On any orbit, speed at r = a equals the circular speed sqrt(μ/a)."""
    assert vis_viva(sma, sma, mu) == pytest.approx(math.sqrt(mu / sma), rel=1e-9)


@given(
    r1=st.floats(min_value=1e5, max_value=1e9, **_finite),
    r2=st.floats(min_value=1e5, max_value=1e9, **_finite),
    mu=_mu,
)
def test_hohmann_total_symmetric(r1, r2, mu):
    """Total Δv from r1→r2 equals total Δv from r2→r1."""
    _, _, t_ab = hohmann_dv(r1, r2, mu)
    _, _, t_ba = hohmann_dv(r2, r1, mu)
    assert t_ab == pytest.approx(t_ba, rel=1e-9)


@given(r_m=_sma, mu=_mu)
def test_escape_velocity_exceeds_circular(r_m, mu):
    v_esc = escape_velocity(r_m, mu)
    v_circ = math.sqrt(mu / r_m)
    assert v_esc == pytest.approx(v_circ * math.sqrt(2), rel=1e-9)


# --------------------------------------------------------------------- #
#  Phase 5: Tsiolkovsky / TWR / inter-body Hohmann                      #
# --------------------------------------------------------------------- #


def test_tsiolkovsky_known_case():
    """Isp=345, mass ratio 2 → Δv ≈ 2344 m/s (= 345 × 9.80665 × ln 2)."""
    dv = tsiolkovsky_dv(345, 10_000, 5_000)
    assert dv == pytest.approx(345 * G0 * math.log(2))
    assert dv == pytest.approx(2345, abs=2)


def test_tsiolkovsky_rejects_bad_masses():
    with pytest.raises(ValueError):
        tsiolkovsky_dv(345, 1000, 1000)  # no fuel
    with pytest.raises(ValueError):
        tsiolkovsky_dv(345, 500, 1000)  # dry > wet


def test_mass_ratio_inverse_of_dv():
    isp = 345
    wet, dry = 10_000, 3_000
    dv = tsiolkovsky_dv(isp, wet, dry)
    assert tsiolkovsky_mass_ratio(dv, isp) == pytest.approx(wet / dry)


def test_twr_basic():
    assert twr(20_000, 1_000, 9.81) == pytest.approx(20_000 / 9810)


def test_burn_time_consistency():
    """Fuel burned × Isp × g₀ / thrust = time."""
    wet, dry, isp, thrust = 10_000, 5_000, 345, 200_000
    t = burn_time(wet, dry, isp, thrust)
    assert t == pytest.approx(5_000 * 345 * G0 / 200_000)


def test_interbody_hohmann_kerbin_to_duna(db):
    """LKO (100 km) → low Duna orbit (100 km); ejection Δv ≈ 1060 m/s."""
    kerbin = get_body(db, "kerbin")
    duna = get_body(db, "duna")
    kerbol = get_body(db, "kerbol")

    result = interbody_hohmann(
        mu_parent=kerbol["mu_m3s2"],
        sma_source_m=kerbin["sma_m"],
        sma_target_m=duna["sma_m"],
        mu_source_body=kerbin["mu_m3s2"],
        r_parking_source_m=kerbin["radius_m"] + 100_000,
        mu_target_body=duna["mu_m3s2"],
        r_parking_target_m=duna["radius_m"] + 100_000,
    )
    # Community canonical: 1,060 m/s ejection from 100 km LKO.
    assert result["dv_eject_m_s"] == pytest.approx(1060, abs=15)
    assert result["dv_insert_m_s"] > 0
    assert result["dv_total_m_s"] == pytest.approx(
        result["dv_eject_m_s"] + result["dv_insert_m_s"]
    )
    # Transfer time ≈ 75 Earth days = ~6.5e6 s.
    assert result["transfer_time_s"] == pytest.approx(6.5e6, rel=0.1)
