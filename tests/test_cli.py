"""Phase 4 CLI tests — smoke checks via Typer's CliRunner."""

from typer.testing import CliRunner

from ksp_planner import plans as plans_mod
from ksp_planner.cli import app

runner = CliRunner()


def _invoke(seed_db, *args):
    return runner.invoke(app, [*args, "--db", str(seed_db)])


COMMS_CFG = {
    "target": "kerbin",
    "sats": 3,
    "antenna": "RA-15 Relay Antenna",
    "dsn_level": 2,
    "min_elev": 5.0,
}
HOHMANN_CFG = {
    "source": "kerbin",
    "target": "duna",
    "from_alt_km": 100.0,
    "to_alt_km": 100.0,
}


def test_body_kerbin(seed_db):
    r = _invoke(seed_db, "body", "kerbin")
    assert r.exit_code == 0
    assert "Kerbin" in r.stdout
    assert "600.000 km" in r.stdout  # radius
    assert "9.81" in r.stdout  # surface gravity


def test_body_slug_case_insensitive(seed_db):
    r = _invoke(seed_db, "body", "KERBIN")
    assert r.exit_code == 0


def test_body_unknown_returns_error(seed_db):
    r = _invoke(seed_db, "body", "nibiru")
    assert r.exit_code == 1
    assert "Unknown body" in r.stdout


def test_bodies_lists_all_17(seed_db):
    r = _invoke(seed_db, "bodies")
    assert r.exit_code == 0
    for slug in [
        "kerbol", "moho", "eve", "gilly", "kerbin", "mun", "minmus",
        "duna", "ike", "dres", "jool", "laythe", "vall", "tylo",
        "bop", "pol", "eeloo",
    ]:
        assert slug in r.stdout


def test_bodies_filter_by_type(seed_db):
    r = _invoke(seed_db, "bodies", "--type", "moon")
    assert r.exit_code == 0
    assert "mun" in r.stdout
    assert "gilly" in r.stdout
    # Planets should not appear when filtering to moons
    assert "duna" not in r.stdout
    assert "eeloo" not in r.stdout


def test_antennas_lists_all_nine(seed_db):
    r = _invoke(seed_db, "antennas")
    assert r.exit_code == 0
    for name in [
        "Communotron 16-S", "Communotron 16", "Communotron DTS-M1",
        "Communotron HG-55", "Communotron 88-88",
        "HG-5 High Gain Antenna",
        "RA-2 Relay Antenna", "RA-15 Relay Antenna", "RA-100 Relay Antenna",
    ]:
        assert name in r.stdout


def test_dsn_lists_three_levels(seed_db):
    r = _invoke(seed_db, "dsn")
    assert r.exit_code == 0
    # Levels shown in a table
    assert "1" in r.stdout
    assert "2" in r.stdout
    assert "3" in r.stdout


def test_comms_default_flags(seed_db):
    """ksp comms kerbin → uses defaults (3 sats, RA-15, DSN 2, 5°)."""
    r = _invoke(seed_db, "comms", "kerbin")
    assert r.exit_code == 0
    assert "Comm network — kerbin" in r.stdout
    assert "COVERAGE OK" in r.stdout


def test_comms_custom_flags(seed_db):
    r = _invoke(
        seed_db, "comms", "kerbin",
        "--sats", "4",
        "--antenna", "RA-100 Relay Antenna",
        "--dsn", "3",
        "--min-elev", "10",
    )
    assert r.exit_code == 0
    assert "RA-100" in r.stdout


def test_comms_coverage_fails(seed_db):
    """Weak antenna at Jool → should still exit 0 but report failure."""
    r = _invoke(
        seed_db, "comms", "jool",
        "--antenna", "Communotron 16",
        "--dsn", "1",
    )
    assert r.exit_code == 0
    assert "COVERAGE FAILS" in r.stdout


def test_comms_unknown_antenna_errors(seed_db):
    r = _invoke(seed_db, "comms", "kerbin", "--antenna", "Made-Up Dish")
    assert r.exit_code == 1


def test_comms_two_sats_fails_gracefully(seed_db):
    """N=2 is geometrically infeasible — CLI should exit nonzero with a clear message."""
    r = _invoke(seed_db, "comms", "kerbin", "--sats", "2")
    assert r.exit_code == 1
    assert "impossible" in r.stdout.lower()


def test_missing_db_gives_hint(tmp_path):
    missing = tmp_path / "nowhere.db"
    r = runner.invoke(app, ["body", "kerbin", "--db", str(missing)])
    assert r.exit_code == 2
    assert "make seed" in r.stdout


# --------------------------------------------------------------------- #
#  Phase 5 CLI: hohmann / twr / dv-budget                               #
# --------------------------------------------------------------------- #


def test_hohmann_kerbin_to_duna(seed_db):
    r = _invoke(seed_db, "hohmann", "kerbin", "duna")
    assert r.exit_code == 0
    assert "Kerbin" in r.stdout and "Duna" in r.stdout
    # Match community canonical ejection Δv ~1060 (allow formatting variance).
    assert "1,0" in r.stdout or "1,1" in r.stdout


def test_hohmann_mismatched_parents_errors(seed_db):
    """Mun orbits Kerbin; Duna orbits Kerbol — incompatible for patched-conics."""
    r = _invoke(seed_db, "hohmann", "mun", "duna")
    assert r.exit_code == 1
    assert "parent" in r.stdout.lower()


def test_twr_kerbin(seed_db):
    r = _invoke(seed_db, "twr", "--thrust", "200000", "--mass", "10000")
    assert r.exit_code == 0
    assert "TWR" in r.stdout
    assert "2.0" in r.stdout  # 200000 / (10000 * 9.81) ≈ 2.039


def test_twr_lift_off_warning_below_1(seed_db):
    r = _invoke(seed_db, "twr", "--thrust", "1000", "--mass", "1000")
    assert r.exit_code == 0
    assert "lift off" in r.stdout.lower()


def test_dv_budget_basic():
    """dv-budget is pure math — no DB needed."""
    r = runner.invoke(app, ["dv-budget", "--isp", "345", "--wet", "10000", "--dry", "5000"])
    assert r.exit_code == 0
    assert "Δv" in r.stdout
    assert "2,345" in r.stdout or "2345" in r.stdout


def test_dv_budget_with_thrust_shows_burn_time():
    r = runner.invoke(app, [
        "dv-budget", "--isp", "345", "--wet", "10000", "--dry", "5000",
        "--thrust", "200000",
    ])
    assert r.exit_code == 0
    assert "Burn time" in r.stdout


def test_dv_budget_zero_fuel_errors():
    r = runner.invoke(app, ["dv-budget", "--isp", "345", "--wet", "5000", "--dry", "5000"])
    assert r.exit_code == 1


# --------------------------------------------------------------------- #
#  Phase 6b CLI: `ksp plan` subcommand group                            #
# --------------------------------------------------------------------- #


def test_plan_list_empty(writable_db):
    r = _invoke(writable_db, "plan", "list")
    assert r.exit_code == 0
    assert "no plans" in r.stdout.lower()


def test_plan_list_shows_saved_plans(writable_db):
    plans_mod.save(writable_db, "my-relay", "comms", COMMS_CFG)
    plans_mod.save(writable_db, "to-duna", "hohmann", HOHMANN_CFG)
    r = _invoke(writable_db, "plan", "list")
    assert r.exit_code == 0
    assert "my-relay" in r.stdout
    assert "to-duna" in r.stdout
    assert "comms" in r.stdout
    assert "hohmann" in r.stdout


def test_plan_show_displays_config(writable_db):
    plans_mod.save(writable_db, "my-relay", "comms", COMMS_CFG)
    r = _invoke(writable_db, "plan", "show", "my-relay")
    assert r.exit_code == 0
    assert "my-relay" in r.stdout
    assert "comms" in r.stdout
    assert "kerbin" in r.stdout
    assert "RA-15" in r.stdout


def test_plan_show_unknown_errors(writable_db):
    r = _invoke(writable_db, "plan", "show", "ghost")
    assert r.exit_code == 1
    assert "ghost" in r.stdout


def test_plan_run_comms_reproduces_comms_output(writable_db):
    plans_mod.save(writable_db, "my-relay", "comms", COMMS_CFG)
    r = _invoke(writable_db, "plan", "run", "my-relay")
    assert r.exit_code == 0
    assert "Comm network — kerbin" in r.stdout
    assert "COVERAGE OK" in r.stdout


def test_plan_run_hohmann_reproduces_hohmann_output(writable_db):
    plans_mod.save(writable_db, "to-duna", "hohmann", HOHMANN_CFG)
    r = _invoke(writable_db, "plan", "run", "to-duna")
    assert r.exit_code == 0
    assert "Kerbin" in r.stdout
    assert "Duna" in r.stdout
    assert "Hohmann" in r.stdout


def test_plan_run_unknown_errors(writable_db):
    r = _invoke(writable_db, "plan", "run", "ghost")
    assert r.exit_code == 1


def test_plan_delete_removes_plan(writable_db):
    plans_mod.save(writable_db, "doomed", "comms", COMMS_CFG)
    r = _invoke(writable_db, "plan", "delete", "doomed")
    assert r.exit_code == 0
    assert plans_mod.list_all(writable_db) == []


def test_plan_delete_unknown_errors(writable_db):
    r = _invoke(writable_db, "plan", "delete", "ghost")
    assert r.exit_code == 1


# --------------------------------------------------------------------- #
#  Phase 6c: --save on twr / dv-budget and plan run dispatch            #
# --------------------------------------------------------------------- #


def test_twr_save_creates_plan(writable_db):
    r = _invoke(
        writable_db, "twr",
        "--thrust", "200000", "--mass", "10000",
        "--save", "liftoff",
    )
    assert r.exit_code == 0
    assert "saved as plan 'liftoff'" in r.stdout
    loaded = plans_mod.load(writable_db, "liftoff")
    assert loaded["kind"] == "twr"
    assert loaded["config"]["thrust"] == 200000
    assert loaded["config"]["mass"] == 10000
    assert loaded["config"]["body"] == "kerbin"


def test_plan_run_twr_reproduces_twr_output(writable_db):
    plans_mod.save(
        writable_db, "liftoff", "twr",
        {"thrust": 200000, "mass": 10000, "body": "kerbin"},
    )
    r = _invoke(writable_db, "plan", "run", "liftoff")
    assert r.exit_code == 0
    assert "TWR" in r.stdout
    assert "2.0" in r.stdout


def test_dv_budget_save_creates_plan(writable_db):
    r = runner.invoke(app, [
        "dv-budget",
        "--isp", "345", "--wet", "10000", "--dry", "5000",
        "--save", "stage-1",
        "--db", str(writable_db),
    ])
    assert r.exit_code == 0
    assert "saved as plan 'stage-1'" in r.stdout
    loaded = plans_mod.load(writable_db, "stage-1")
    assert loaded["kind"] == "dv_budget"
    assert loaded["config"]["isp"] == 345
    assert loaded["config"]["wet"] == 10000
    assert loaded["config"]["dry"] == 5000


def test_plan_run_dv_budget_reproduces_dv_output(writable_db):
    plans_mod.save(
        writable_db, "stage-1", "dv_budget",
        {"isp": 345, "wet": 10000, "dry": 5000, "thrust": None},
    )
    r = _invoke(writable_db, "plan", "run", "stage-1")
    assert r.exit_code == 0
    assert "Δv" in r.stdout
    assert "2,345" in r.stdout or "2345" in r.stdout


def test_plan_run_dv_budget_with_thrust_shows_burn_time(writable_db):
    plans_mod.save(
        writable_db, "stage-1", "dv_budget",
        {"isp": 345, "wet": 10000, "dry": 5000, "thrust": 200000},
    )
    r = _invoke(writable_db, "plan", "run", "stage-1")
    assert r.exit_code == 0
    assert "Burn time" in r.stdout


# ---------- Phase 7a: ksp dv ----------

def test_dv_kerbin_to_mun_acceptance(seed_db):
    """Acceptance: ksp dv kerbin_surface mun_surface within ±50 m/s of chart total."""
    r = _invoke(seed_db, "dv", "kerbin_surface", "mun_surface")
    assert r.exit_code == 0
    assert "kerbin_surface" in r.stdout
    assert "mun_surface" in r.stdout
    # raw total = 5150; planned = 5408 at default 5%
    assert "5,150" in r.stdout
    assert "5,408" in r.stdout  # 5150 * 1.05 = 5407.5 → "5,408" rounded


def test_dv_default_margin_is_5pct(seed_db):
    r = _invoke(seed_db, "dv", "kerbin_surface", "mun_surface")
    assert r.exit_code == 0
    assert "5%" in r.stdout or "5.0%" in r.stdout


def test_dv_custom_margin(seed_db):
    r = _invoke(seed_db, "dv", "kerbin_surface", "mun_surface", "--margin", "10")
    assert r.exit_code == 0
    # planned = 5150 * 1.10 = 5665
    assert "5,665" in r.stdout
    assert "10" in r.stdout  # margin label


def test_dv_zero_margin_shows_raw_only(seed_db):
    r = _invoke(seed_db, "dv", "kerbin_surface", "mun_surface", "--margin", "0")
    assert r.exit_code == 0
    assert "5,150" in r.stdout


def test_dv_unknown_from_slug_errors(seed_db):
    r = _invoke(seed_db, "dv", "nibiru_surface", "mun_surface")
    assert r.exit_code == 1
    assert "nibiru_surface" in r.stdout


def test_dv_unknown_to_slug_errors(seed_db):
    r = _invoke(seed_db, "dv", "kerbin_surface", "nibiru_surface")
    assert r.exit_code == 1
    assert "nibiru_surface" in r.stdout


def test_dv_lists_each_leg(seed_db):
    """Output should show every edge along the path so the user can audit it."""
    r = _invoke(seed_db, "dv", "kerbin_surface", "mun_surface")
    assert r.exit_code == 0
    # 4 legs: kerbin_surface → kerbin_low_orbit → mun_transfer → mun_low_orbit → mun_surface
    assert "kerbin_low_orbit" in r.stdout
    assert "mun_transfer" in r.stdout
    assert "mun_low_orbit" in r.stdout
    # individual leg costs
    assert "3,400" in r.stdout
    assert "860" in r.stdout
    assert "310" in r.stdout
    assert "580" in r.stdout
