# Testing approach

TDD from Phase 0. Every calculator function gets a test **before** the implementation.

## Tools

- **pytest** — runner, fixtures, parametrize
- **hypothesis** — property-based testing for orbital math
- **coverage.py** (`pytest-cov`) — aim for 100% on pure modules (`orbital.py`, `comms.py`, `dv_map.py`)
- **Typer's `CliRunner`** — integration tests for the CLI
- **FastAPI's `TestClient`** — API tests in Phase 8

## Test pyramid

```
                        ┌─────────────┐
                        │  CLI / API  │   Phase 4, 8 — few, slow, end-to-end
                        └─────────────┘
                    ┌─────────────────────┐
                    │    integration      │   seeded DB + calculator
                    └─────────────────────┘
                ┌─────────────────────────────┐
                │     unit (pure modules)     │   most tests live here
                └─────────────────────────────┘
```

Most tests live at the unit layer because the calculators are pure functions. A unit test for `hohmann_dv` takes three floats in and asserts one float out — no fixtures, no setup.

## Fixtures (conftest.py)

```python
@pytest.fixture(scope="session")
def seed_db(tmp_path_factory):
    """Build a fresh ksp.db in a tmp dir, once per test session."""
    db_path = tmp_path_factory.mktemp("db") / "ksp.db"
    run_seed(db_path)
    return db_path

@pytest.fixture
def db(seed_db):
    """Per-test connection to the seeded DB, read-only."""
    conn = sqlite3.connect(f"file:{seed_db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()

@pytest.fixture
def kerbin(db):
    return get_body(db, "kerbin")
```

The seed runs **once per session**. Individual tests get a read-only connection — impossible to accidentally mutate the shared DB.

## What to test at each layer

### `seeds/*` and `db.py`

- **Known-value assertions** for every seeded body: μ, radius, SOI match the planning doc to the given precision.
- **Hierarchy integrity**: every `parent_id` resolves, no cycles, Kerbol is the only root.
- **Antenna roster**: expected set of 8 antennas present with correct power values.
- **DSN levels**: levels 1/2/3 present with correct power values.

These catch the likeliest bug: a typo in a seed literal. Humans miss 10⁹ vs 10¹⁰ in a code review. Tests do not.

### `orbital.py`

Canonical value tests — pin against known KSP numbers so a bad formula can't slip in:

| Assertion                                           | Expected     | Tolerance |
|-----------------------------------------------------|--------------|-----------|
| Kerbin sync orbit altitude                          | 2,863.33 km  | ±1 km     |
| Mun escape velocity at surface                      | 807 m/s      | ±1 m/s    |
| Kerbin surface gravity                              | 9.81 m/s²    | ±0.01     |
| LKO (100 km) orbital period                         | 30 m 10 s    | ±5 s      |
| Hohmann Kerbin (100 km LKO) → Duna (100 km)         | 1,060 m/s    | ±30 m/s   |

Property-based tests with `hypothesis`:

```python
@given(sma=st.floats(1e5, 1e10), mu=st.floats(1e10, 1e20))
def test_period_increases_with_sma(sma, mu):
    assert orbital_period(sma * 2, mu) > orbital_period(sma, mu)

@given(sma=st.floats(1e6, 1e9), mu=st.floats(1e11, 1e15))
def test_vis_viva_circular_identity(sma, mu):
    assert vis_viva(sma, sma, mu) == pytest.approx(sqrt(mu / sma))
```

Properties catch bugs that hand-picked examples miss (off-by-square-root, dropped factor of 2, etc.).

### `comms.py`

The regenerated worked example (see [features/comm-network.md](features/comm-network.md)) is the **canonical test**:

```python
def test_worked_example_3_sats_kerbin_ra15_dsn2(db):
    kerbin = get_body(db, "kerbin")
    report = comm_network_report(
        body=kerbin,
        n_sats=3,
        antenna=get_antenna(db, "RA-15 Relay Antenna"),
        dsn_level=get_dsn(db, 2),
        min_elev_deg=5,
    )
    assert report["orbit_altitude_m"] == pytest.approx(814_318, abs=1)
    assert report["sat_separation_m"] == pytest.approx(2_449_671, abs=1)
    assert report["range_sat_to_sat_m"] == pytest.approx(1.5e10)
    assert report["range_sat_to_dsn_m"] == pytest.approx(2.7386128e10, rel=1e-6)
    assert report["coverage_ok"] is True
    assert report["period_s"] == pytest.approx(5623.6, abs=0.2)  # ~1h 33m 43s
```

Edge cases:
- 2-sat constellation (impossible or requires unreasonable altitude — should flag)
- Coverage failure (RA-2 at Jool with 3 sats → margin negative, coverage_ok False)
- Tiny body (Gilly, radius 13 km)
- Body with big SOI (Jool)

### `dv_map.py`

- Known chart values: Kerbin surface → LKO = 3,400; LKO → Mun transfer = 860; etc.
- LCA correctness: `path_dv("mun_surface", "minmus_surface")` walks through LKO.
- Margin math: `total_planned == total_raw * (1 + margin_pct/100)` for any margin.
- Round-trip with aerobrake zeros the descent-to-surface leg for atmospheric bodies.
- **Cross-check test:** computed Hohmann Δv from `orbital.py` must match seeded chart value within 5%. Fails loud if either source drifts.

### `cli.py` (Phase 4)

Each subcommand gets a smoke test via Typer's `CliRunner`:

```python
def test_body_kerbin_prints_radius(runner):
    result = runner.invoke(app, ["body", "kerbin"])
    assert result.exit_code == 0
    assert "600" in result.stdout  # radius in km
    assert "3.53" in result.stdout  # μ
```

Not trying to test the formatting in detail — just that the subcommand runs and emits the right numbers.

### `web/` (Phase 8)

- Each endpoint: request validation (Pydantic rejects bad input with 422)
- Each endpoint: happy-path returns expected JSON shape
- Same calculator tests as the CLI layer still apply; don't duplicate them

## TDD rhythm

For each new function:

1. **Red** — write the test first, with the expected value from community data or hand calculation. Run it; watch it fail.
2. **Green** — write the minimum implementation that makes it pass. No extra features.
3. **Refactor** — tidy the implementation once tests are green. Tests stay green.

Commit after each green step so you always have a known-good state to roll back to.

## What we do *not* test

- **Rich output formatting.** Tests that assert on exact table borders or colors are brittle. Test the *data* that goes to Rich, not the rendered output.
- **Private helpers.** Test through the public API. If a private helper is hard to reach, that is a design smell — split the module.
- **Python stdlib.** No tests for `sqlite3`, `math.sqrt`, etc.

## Running tests

```
make test            # full suite
make test-unit       # pure-module tests only; fast
pytest tests/test_orbital.py -v
pytest -k hohmann    # tests matching substring
pytest --cov         # with coverage
```
