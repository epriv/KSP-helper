"""Phase 8f — pure scanning math tests."""

from __future__ import annotations

import math

import pytest

from ksp_planner.scanning import (
    SweetSpot,
    days_to_full_coverage,
    find_sweet_spots,
    ground_track_shift_m,
    is_resonant,
    swath_width_m,
)

_R = 600_000.0
_MU = 3_531_600_000_000.0
_T_ROT = 21_549.425183090


def _period(alt_m: float) -> float:
    return 2 * math.pi * math.sqrt((_R + alt_m) ** 3 / _MU)


def test_swath_width_kerbin_250km_5deg():
    assert swath_width_m(250_000, 5.0) == pytest.approx(21_830, rel=0.001)


def test_swath_width_zero_fov_is_zero():
    assert swath_width_m(500_000, 0.0) == pytest.approx(0, abs=1e-6)


def test_swath_width_scales_with_altitude():
    w1 = swath_width_m(100_000, 5.0)
    w2 = swath_width_m(200_000, 5.0)
    assert w2 == pytest.approx(2 * w1, rel=0.001)


def test_ground_track_shift_kerbin_250km():
    T = _period(250_000)
    S = ground_track_shift_m(_R, T, _T_ROT)
    assert S == pytest.approx(458_372, rel=0.001)


def test_ground_track_shift_longer_period_means_larger_shift():
    T_low  = _period(100_000)
    T_high = _period(500_000)
    S_low  = ground_track_shift_m(_R, T_low,  _T_ROT)
    S_high = ground_track_shift_m(_R, T_high, _T_ROT)
    assert S_high > S_low


def test_is_resonant_exact_integer_8():
    assert is_resonant(8.0, max_q=12, tolerance=0.005) == (True, "8/1")


def test_is_resonant_exact_integer_4():
    assert is_resonant(4.0, max_q=12, tolerance=0.005) == (True, "4/1")


def test_is_resonant_nonresonant_763km_kerbin():
    opd = _T_ROT / _period(763_000)
    resonant, _ = is_resonant(opd, max_q=12, tolerance=0.005)
    assert not resonant


def test_is_resonant_returns_ratio_string():
    resonant, ratio = is_resonant(8.0, max_q=12, tolerance=0.005)
    assert resonant
    assert ratio == "8/1"


def test_is_resonant_nonresonant_returns_empty_ratio():
    opd = _T_ROT / _period(763_000)
    _, ratio = is_resonant(opd, max_q=12, tolerance=0.005)
    assert ratio == ""


def test_is_resonant_catches_near_resonant():
    # 3.002 is within 0.5% of 3/1 (error = 0.067%) — must be caught
    resonant, ratio = is_resonant(3.002, max_q=12, tolerance=0.005)
    assert resonant
    assert ratio == "3/1"


def test_is_resonant_passes_outside_tolerance():
    # 3.02 is 0.67% away from 3/1 — outside 0.5% tolerance, not resonant
    resonant, _ = is_resonant(3.02, max_q=12, tolerance=0.005)
    assert not resonant


def test_days_to_coverage_is_positive():
    T = _period(763_000)
    days = days_to_full_coverage(_R, 763_000, 5.0, T, _T_ROT)
    assert days > 0


def test_days_to_coverage_wider_fov_means_fewer_days():
    T = _period(500_000)
    days_narrow = days_to_full_coverage(_R, 500_000, 2.0, T, _T_ROT)
    days_wide   = days_to_full_coverage(_R, 500_000, 5.0, T, _T_ROT)
    assert days_wide < days_narrow


def test_days_to_coverage_zero_fov_returns_inf():
    import math as _math
    T = _period(500_000)
    days = days_to_full_coverage(_R, 500_000, 0.0, T, _T_ROT)
    assert _math.isinf(days)


def test_find_sweet_spots_returns_nonempty_for_kerbin():
    results = find_sweet_spots(_R, _MU, _T_ROT, 5.0)
    assert len(results) > 0


def test_find_sweet_spots_all_nonresonant():
    results = find_sweet_spots(_R, _MU, _T_ROT, 5.0)
    assert all(not r.resonant for r in results)


def test_find_sweet_spots_sorted_ascending_by_days():
    results = find_sweet_spots(_R, _MU, _T_ROT, 5.0, top_n=5)
    days = [r.days_to_coverage for r in results]
    assert days == sorted(days)


def test_find_sweet_spots_top_n_respected():
    results = find_sweet_spots(_R, _MU, _T_ROT, 5.0, top_n=2)
    assert len(results) <= 2


def test_find_sweet_spots_altitudes_within_search_range():
    results = find_sweet_spots(_R, _MU, _T_ROT, 5.0,
                               min_alt_m=80_000, max_alt_m=2_500_000)
    for r in results:
        assert 80 <= r.altitude_km <= 2500


def test_find_sweet_spots_sweetspot_type():
    results = find_sweet_spots(_R, _MU, _T_ROT, 5.0)
    assert all(isinstance(r, SweetSpot) for r in results)
