"""Phase 1 seed tests.

Values come from seeds/data/bodies.ini (KSPTOT) and the antenna/DSN tables
in seeds/seed_stock.py. These tests catch transcription regressions.
"""

import pytest

from ksp_planner.db import get_antenna, get_body, get_dsn, list_antennas, list_bodies

EXPECTED_BODIES = {
    "kerbol": {"radius_m":      261_600_000, "mu_m3s2": 1.1723328e18},
    "moho":   {"radius_m":          250_000, "mu_m3s2": 1.6860938e11},
    "eve":    {"radius_m":          700_000, "mu_m3s2": 8.1717302e12},
    "gilly":  {"radius_m":           13_000, "mu_m3s2": 8.289e6},
    "kerbin": {"radius_m":          600_000, "mu_m3s2": 3.5316e12},
    "mun":    {"radius_m":          200_000, "mu_m3s2": 6.5138398e10},
    "minmus": {"radius_m":           60_000, "mu_m3s2": 1.7658e9},
    "duna":   {"radius_m":          320_000, "mu_m3s2": 3.0136321e11},
    "ike":    {"radius_m":          130_000, "mu_m3s2": 1.8568369e10},
    "dres":   {"radius_m":          138_000, "mu_m3s2": 2.1484489e10},
    "jool":   {"radius_m":        6_000_000, "mu_m3s2": 2.8252800e14},
    "laythe": {"radius_m":          500_000, "mu_m3s2": 1.962e12},
    "vall":   {"radius_m":          300_000, "mu_m3s2": 2.0748150e11},
    "tylo":   {"radius_m":          600_000, "mu_m3s2": 2.8252800e12},
    "bop":    {"radius_m":           65_000, "mu_m3s2": 2.4868349e9},
    "pol":    {"radius_m":           44_000, "mu_m3s2": 7.2170208e8},
    "eeloo":  {"radius_m":          210_000, "mu_m3s2": 7.4410815e10},
}


@pytest.mark.parametrize(("slug", "expected"), EXPECTED_BODIES.items())
def test_body_physical_values(db, slug, expected):
    body = get_body(db, slug)
    assert body["radius_m"] == pytest.approx(expected["radius_m"])
    assert body["mu_m3s2"] == pytest.approx(expected["mu_m3s2"], rel=1e-4)


def test_all_17_bodies_present(db):
    assert len(list_bodies(db)) == 17


def test_surface_gravity_sanity(db):
    """g = μ/r² spot-checks — the failure mode that the original docx hit."""
    checks = [("kerbin", 9.81), ("mun", 1.63), ("eve", 16.7), ("duna", 2.94)]
    for slug, expected_g in checks:
        b = get_body(db, slug)
        g = b["mu_m3s2"] / b["radius_m"] ** 2
        assert g == pytest.approx(expected_g, rel=5e-3), f"{slug}: {g=}"


def test_body_hierarchy(db):
    bodies = list_bodies(db)
    by_id = {b["id"]: b for b in bodies}
    by_slug = {b["slug"]: b for b in bodies}

    roots = [b for b in bodies if b["parent_id"] is None]
    assert len(roots) == 1
    assert roots[0]["slug"] == "kerbol"

    expected_parents = {
        "moho": "kerbol", "eve": "kerbol", "gilly": "eve",
        "kerbin": "kerbol", "mun": "kerbin", "minmus": "kerbin",
        "duna": "kerbol", "ike": "duna", "dres": "kerbol",
        "jool": "kerbol", "laythe": "jool", "vall": "jool",
        "tylo": "jool", "bop": "jool", "pol": "jool", "eeloo": "kerbol",
    }
    for child, parent in expected_parents.items():
        assert by_id[by_slug[child]["parent_id"]]["slug"] == parent


def test_kerbol_has_no_orbit_or_soi(db):
    kerbol = get_body(db, "kerbol")
    assert kerbol["parent_id"] is None
    assert kerbol["soi_m"] is None
    assert kerbol["sma_m"] is None


def test_kerbin_sync_orbit(db):
    """Canonical Kerbin keostationary altitude ≈ 2,863.33 km."""
    k = get_body(db, "kerbin")
    alt_km = (k["sync_orbit_m"] - k["radius_m"]) / 1000
    assert alt_km == pytest.approx(2863.33, abs=2)


@pytest.mark.parametrize(("slug", "expected_soi_km"), [
    ("moho",   9_647),
    ("mun",    2_430),
    ("minmus", 2_247),
    ("kerbin", 84_159),
    ("duna",   47_922),
    ("jool",   2_455_985),
    ("eeloo",  119_083),
])
def test_soi_within_half_percent(db, slug, expected_soi_km):
    """Laplace-formula SOI should match doc values to ~0.5% (small method diff)."""
    body = get_body(db, slug)
    soi_km = body["soi_m"] / 1000
    assert soi_km == pytest.approx(expected_soi_km, rel=5e-3)


def test_atmospheric_bodies(db):
    with_atm = {b["slug"] for b in list_bodies(db) if b["atm_height_m"]}
    assert with_atm == {"kerbol", "eve", "kerbin", "duna", "jool", "laythe"}
    with_oxygen = {b["slug"] for b in list_bodies(db) if b["has_oxygen"]}
    assert with_oxygen == {"kerbin", "laythe"}


def test_orbital_elements_present(db):
    """Every non-Kerbol body has a fully populated orbit row."""
    for b in list_bodies(db):
        if b["slug"] == "kerbol":
            continue
        full = get_body(db, b["slug"])
        assert full["sma_m"] is not None
        assert full["eccentricity"] is not None
        assert full["inclination_deg"] is not None
        assert full["arg_periapsis_deg"] is not None
        assert full["lan_deg"] is not None
        assert full["mean_anomaly_epoch_deg"] is not None


def test_antenna_roster(db):
    names = {a["name"] for a in list_antennas(db)}
    assert names == {
        "Communotron 16-S", "Communotron 16", "Communotron DTS-M1",
        "Communotron HG-55", "Communotron 88-88",
        "HG-5 High Gain Antenna",
        "RA-2 Relay Antenna", "RA-15 Relay Antenna", "RA-100 Relay Antenna",
    }


@pytest.mark.parametrize(("name", "expected_range", "is_relay"), [
    ("Communotron 16-S",       5.0e5,  False),
    ("Communotron 16",         5.0e5,  False),
    ("Communotron DTS-M1",     2.0e9,  False),
    ("Communotron HG-55",      1.5e10, False),
    ("Communotron 88-88",      1.0e11, False),
    ("HG-5 High Gain Antenna", 5.0e6,  True),
    ("RA-2 Relay Antenna",     2.0e9,  True),
    ("RA-15 Relay Antenna",    1.5e10, True),
    ("RA-100 Relay Antenna",   1.0e11, True),
])
def test_antenna_values(db, name, expected_range, is_relay):
    a = get_antenna(db, name)
    assert a["range_m"] == pytest.approx(expected_range)
    assert bool(a["is_relay"]) is is_relay


@pytest.mark.parametrize(("level", "expected"), [
    (1, 2.0e9),
    (2, 5.0e10),
    (3, 2.5e11),
])
def test_dsn_levels(db, level, expected):
    assert get_dsn(db, level)["range_m"] == pytest.approx(expected)


def test_unknown_lookups_raise(db):
    with pytest.raises(KeyError):
        get_body(db, "nibiru")
    with pytest.raises(KeyError):
        get_antenna(db, "UHF Whip")
    with pytest.raises(KeyError):
        get_dsn(db, 99)
