# Δv Planner 7d Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `--return` round-trip support to `ksp dv` and drop the aerobrake residual to 0% so Kerbin return descent comes out free.

**Architecture:** `plan_round_trip` is a thin wrapper that doubles the stops list and delegates to `plan_trip`. The aerobrake credit change is a one-line constant flip plus a dynamic renderer label and updated pinned test values. No schema or `TripPlan` shape changes.

**Tech Stack:** Python 3.12, Typer, Rich, pytest, SQLite. Existing Δv tree + LCA walk in `src/ksp_planner/dv_map.py`.

**Spec:** [`docs/superpowers/specs/2026-04-23-dv-planner-7d-design.md`](../specs/2026-04-23-dv-planner-7d-design.md)

---

## File map

| File | Responsibility | Change |
|---|---|---|
| `src/ksp_planner/dv_map.py` | Δv chart data structures + path walk + plan_trip | Flip residual constant to 0.0; add `plan_round_trip` |
| `src/ksp_planner/formatting.py` | Rich presentation helpers | Make `_aero_cell` label derive from `AEROBRAKE_RESIDUAL_PCT` |
| `src/ksp_planner/cli.py` | Typer app / CLI entry point | Add `--return` flag to `dv`; dispatch to `plan_round_trip` |
| `tests/test_dv_map.py` | dv_map unit + integration tests | Update 7c pins to new aerobraked values; add round-trip tests |
| `tests/test_cli.py` | CLI integration tests | Update 7c pins; add `--return` tests |
| `docs/PROGRESS.md` | Build log | Add 7d completion log + 7e resume notes |

---

## Task 1: Residual → 0% (lockstep constant + renderer + pin update)

**Files:**
- Modify: `src/ksp_planner/dv_map.py:56` (`AEROBRAKE_RESIDUAL_PCT` constant)
- Modify: `src/ksp_planner/formatting.py:170-223` (`_aero_cell` label + docstring)
- Modify: `tests/test_dv_map.py:182-223` (7c unit pins) and `:404-439` (7c integration pins)
- Modify: `tests/test_cli.py:475-512` (7c CLI pins)

### Why lockstep

The constant flip, the renderer label, and the pinned expected values are one semantic change. Splitting them leaves the suite red between steps. Edit all pins first (RED — tests fail against the old 20% constant), then flip the constant + renderer (GREEN — all pass).

- [ ] **Step 1.1: Update `tests/test_dv_map.py` 7c unit pins**

Replace lines 182-223 with:

```python
def test_plan_trip_aerobrake_zeroes_capable_edge(aero_tree):
    """1000 m/s descent with can_aerobrake=True → credited to 0 at 0% residual."""
    plan = plan_trip(aero_tree, [Stop("a"), Stop("d")])
    assert plan.total_raw == 1000
    # aerobraked = 1000 * 0.00 = 0 (full credit at 0% residual)
    assert plan.total_aerobraked == pytest.approx(0.0)
    assert plan.aerobrake is True


def test_plan_trip_aerobrake_false_is_noop(aero_tree):
    """aerobrake=False: total_aerobraked == total_raw (no credit applied)."""
    plan = plan_trip(aero_tree, [Stop("a"), Stop("d")], aerobrake=False)
    assert plan.total_raw == 1000
    assert plan.total_aerobraked == 1000
    assert plan.aerobrake is False


def test_plan_trip_aerobrake_on_non_capable_tree_has_no_effect(tree):
    """The existing `tree` fixture has can_aerobrake=False on every edge — no credit."""
    plan = plan_trip(tree, [Stop("a_left"), Stop("b_right_child")])
    assert plan.total_raw == 27
    assert plan.total_aerobraked == 27  # no flagged edges in the tree fixture


def test_plan_trip_aerobrake_planned_applies_margin(aero_tree):
    """total_aerobraked_planned == total_aerobraked * (1 + margin/100).

    Uses root→d path so aerobraked total is non-zero (100 from the non-aero
    root→a edge), making the 5% scaling meaningfully testable.
    """
    plan = plan_trip(aero_tree, [Stop("root"), Stop("d")])
    assert plan.total_aerobraked == pytest.approx(100.0)
    assert plan.total_aerobraked_planned == pytest.approx(100.0 * 1.05)


def test_plan_trip_aerobrake_planned_scales_with_custom_margin(aero_tree):
    plan = plan_trip(aero_tree, [Stop("root"), Stop("d")], margin_pct=10.0)
    assert plan.total_aerobraked == pytest.approx(100.0)
    assert plan.total_aerobraked_planned == pytest.approx(100.0 * 1.10)


def test_plan_trip_aerobrake_residual_constant_is_zero():
    """AEROBRAKE_RESIDUAL_PCT is the module lever (0.0 → aerobrake zeros capable edges)."""
    from ksp_planner.dv_map import AEROBRAKE_RESIDUAL_PCT

    assert AEROBRAKE_RESIDUAL_PCT == 0.0
```

- [ ] **Step 1.2: Update `tests/test_dv_map.py` 7c integration pins (kerbin→duna)**

Replace the `test_kerbin_to_duna_surface_aerobraked_totals` function (at line 404) with:

```python
def test_kerbin_to_duna_surface_aerobraked_totals(db):
    """kerbin→duna: raw 6,270; aerobraked 4,460 (duna capture 360→0, duna descent 1450→0)."""
    from ksp_planner.db import load_dv_graph

    g = load_dv_graph(db)
    plan = plan_trip(g, [Stop("kerbin_surface"), Stop("duna_surface")])
    assert plan.total_raw == pytest.approx(6270, abs=5)
    assert plan.total_aerobraked == pytest.approx(4460, abs=5)
    assert plan.total_aerobraked_planned == pytest.approx(4460 * 1.05, abs=10)
    assert plan.aerobrake is True
```

- [ ] **Step 1.3: Update `tests/test_dv_map.py` 7c integration pins (kerbin→eve)**

Replace the `test_kerbin_to_eve_surface_aerobraked_shows_dramatic_savings` function (at line 426) with:

```python
def test_kerbin_to_eve_surface_aerobraked_shows_dramatic_savings(db):
    """Eve descent (8000 ballistic) + Eve capture (80) both zeroed at 0% residual."""
    from ksp_planner.db import load_dv_graph

    g = load_dv_graph(db)
    plan = plan_trip(g, [Stop("kerbin_surface"), Stop("eve_surface")])
    # Outbound: 3400 (ascent, up — not aerobrakable) + 0 (trunk) + 1080 (Eve ejection)
    #           + 80 (Eve capture) + 8000 (Eve descent) = 12,560
    # With aerobrake: 3400 + 0 + 1080 + 0 + 0 = 4,480
    assert plan.total_raw == pytest.approx(12560, abs=10)
    assert plan.total_aerobraked == pytest.approx(4480, abs=10)
    assert plan.total_raw - plan.total_aerobraked > 8000
```

- [ ] **Step 1.4: Update `tests/test_cli.py` 7c CLI pins**

Replace lines 475-512 (the `# ---------- 7c: aerobrake rendering ----------` block) with:

```python
# ---------- 7c/7d: aerobrake rendering ----------


def test_dv_kerbin_to_duna_shows_with_aerobrake_row(seed_db):
    """Default (aerobrake on): panel shows 'With aerobrake' totals row."""
    r = _invoke(seed_db, "dv", "kerbin_surface", "duna_surface")
    assert r.exit_code == 0
    assert "Raw total" in r.stdout
    assert "With aerobrake" in r.stdout
    # raw 6,270; aerobraked 4,460; planned aerobraked 4,683
    assert "6,270" in r.stdout
    assert "4,460" in r.stdout


def test_dv_aerobrake_column_marks_credited_edges(seed_db):
    """The aero column shows '−100%' on can_aerobrake=True edges when aerobrake is on."""
    r = _invoke(seed_db, "dv", "kerbin_surface", "duna_surface")
    assert r.exit_code == 0
    # accept either hyphen shape
    assert "−100%" in r.stdout or "-100%" in r.stdout


def test_dv_no_aerobrake_hides_with_aerobrake_row(seed_db):
    """--no-aerobrake: only Raw total + Planned, no 'With aerobrake' row."""
    r = _invoke(seed_db, "dv", "kerbin_surface", "duna_surface", "--no-aerobrake")
    assert r.exit_code == 0
    assert "Raw total" in r.stdout
    assert "With aerobrake" not in r.stdout
    # planned should use the raw total, not an aerobraked figure
    # 6,270 * 1.05 = 6,584
    assert "6,584" in r.stdout


def test_dv_no_aerobrake_aero_column_shows_off(seed_db):
    """--no-aerobrake: aero column on creditable edges shows '✓ off' not '−100%'."""
    r = _invoke(seed_db, "dv", "kerbin_surface", "duna_surface", "--no-aerobrake")
    assert r.exit_code == 0
    assert "✓ off" in r.stdout
    assert "−100%" not in r.stdout and "-100%" not in r.stdout
```

- [ ] **Step 1.5: Run tests to confirm they fail against the old 20% constant**

Run: `cd "/Users/aj/Development/KSP App" && uv run pytest tests/test_dv_map.py tests/test_cli.py -k "aerobrake or _to_duna or _to_eve or residual" -v`

Expected: Multiple failures — `AEROBRAKE_RESIDUAL_PCT == 0.0` fails (it's 20.0), `4,460` not in output (it's 4,822), `−100%` not in output (it's −80%), etc. This confirms the pins are biting.

- [ ] **Step 1.6: Flip the residual constant**

Edit `src/ksp_planner/dv_map.py` line 54-56. Replace:

```python
# 20% residual = aerobrake credits 80% of a can_aerobrake edge's ballistic dv.
# Residual covers correction burns, safety margin, and imperfect atmospheric passes.
AEROBRAKE_RESIDUAL_PCT = 20.0
```

with:

```python
# 0% residual = aerobrake fully credits can_aerobrake edges (community-chart convention).
# The 5% trip margin is the safety buffer for correction burns and imperfect passes.
# Kept as a module constant so a future tune (e.g. 5%) is still a one-line change.
AEROBRAKE_RESIDUAL_PCT = 0.0
```

- [ ] **Step 1.7: Make the renderer label dynamic**

Edit `src/ksp_planner/formatting.py`:

At line 11, replace:
```python
from ksp_planner.dv_map import ACTION_SUFFIXES
```
with:
```python
from ksp_planner.dv_map import ACTION_SUFFIXES, AEROBRAKE_RESIDUAL_PCT
```

In the `dv_trip_panel` docstring (around line 176-182), replace:
```
    The `aero` column is tri-state:
        - "✓ −80%"  : edge is can_aerobrake=True and trip.aerobrake is True
        - "✓ off"   : edge is can_aerobrake=True but trip.aerobrake is False
        - ""        : edge cannot be aerobraked
```
with:
```
    The `aero` column is tri-state:
        - "✓ −N%"   : edge is can_aerobrake=True and trip.aerobrake is True
                      (N = 100 − AEROBRAKE_RESIDUAL_PCT, i.e. the discount applied)
        - "✓ off"   : edge is can_aerobrake=True but trip.aerobrake is False
        - ""        : edge cannot be aerobraked
```

In `_aero_cell` (around line 199-202), replace:
```python
    def _aero_cell(edge) -> str:
        if not edge.can_aerobrake:
            return ""
        return "✓ −80%" if trip.aerobrake else "✓ off"
```
with:
```python
    credit_pct = 100 - AEROBRAKE_RESIDUAL_PCT

    def _aero_cell(edge) -> str:
        if not edge.can_aerobrake:
            return ""
        return f"✓ −{credit_pct:g}%" if trip.aerobrake else "✓ off"
```

- [ ] **Step 1.8: Run the targeted tests — expect pass**

Run: `cd "/Users/aj/Development/KSP App" && uv run pytest tests/test_dv_map.py tests/test_cli.py -k "aerobrake or _to_duna or _to_eve or residual" -v`

Expected: all pass.

- [ ] **Step 1.9: Run the full suite to confirm no collateral regressions**

Run: `cd "/Users/aj/Development/KSP App" && make test`

Expected: all 192 tests pass.

- [ ] **Step 1.10: Commit**

```bash
cd "/Users/aj/Development/KSP App"
git add src/ksp_planner/dv_map.py src/ksp_planner/formatting.py tests/test_dv_map.py tests/test_cli.py
git commit -m "$(cat <<'EOF'
feat(7d): drop aerobrake residual to 0% (community-chart convention)

Aerobrakable edges now credit 100% under aerobrake=True, matching community
Δv chart convention. The 5% trip margin is the safety buffer; the residual
constant stays as a tunable module-level lever. Renderer label tracks the
constant so future tunes surface automatically. 7c pins updated in lockstep.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: `plan_round_trip`

**Files:**
- Modify: `src/ksp_planner/dv_map.py` (add `plan_round_trip` at end of module)
- Modify: `tests/test_dv_map.py` (add new test block)

- [ ] **Step 2.1: Write failing tests for `plan_round_trip`**

Append to `tests/test_dv_map.py`:

```python
# ---------- 7d: round-trip ----------


def test_plan_round_trip_two_stops_doubles_itinerary(tree):
    """[A, B] → legs for A→B→A; two legs, mirror image."""
    from ksp_planner.dv_map import plan_round_trip

    plan = plan_round_trip(tree, [Stop("a_left"), Stop("b_right_child")])
    assert len(plan.legs) == 2
    # Stops list on the TripPlan is doubled: [A, B, A]
    assert [s.slug for s in plan.stops] == ["a_left", "b_right_child", "a_left"]
    # Outbound edges + return edges should sum to twice the one-way raw
    one_way = plan_trip(tree, [Stop("a_left"), Stop("b_right_child")])
    assert plan.total_raw == pytest.approx(2 * one_way.total_raw)


def test_plan_round_trip_three_stops_doubles_with_turnaround(tree):
    """[A, B, C] → legs for A→B→C→B→A; four legs."""
    from ksp_planner.dv_map import plan_round_trip

    plan = plan_round_trip(
        tree, [Stop("a_left"), Stop("b_left_child"), Stop("b_right_child")]
    )
    assert len(plan.legs) == 4
    assert [s.slug for s in plan.stops] == [
        "a_left", "b_left_child", "b_right_child", "b_left_child", "a_left",
    ]


def test_plan_round_trip_requires_two_stops(tree):
    """Single stop is not a round trip."""
    from ksp_planner.dv_map import plan_round_trip

    with pytest.raises(ValueError, match="at least two stops"):
        plan_round_trip(tree, [Stop("a_left")])


def test_plan_round_trip_kerbin_to_mun_with_aerobrake(db):
    """Canonical acceptance: Kerbin surface → Mun surface → Kerbin surface.

    Outbound: 3,400 (ascent) + 860 (Mun transfer) + 310 (capture) + 580 (descent) = 5,150
    Return:   580 (ascent) + 310 (Mun escape) + 860 (Kerbin capture) + 3,400 (descent) = 5,150
        └─ Kerbin descent is can_aerobrake=True, credits to 0 under aerobrake=True.
    Return aerobraked: 580 + 310 + 860 + 0 = 1,750
    Round-trip raw: 10,300 · aerobraked: 6,900 · planned @ 5%: 7,245
    """
    from ksp_planner.db import load_dv_graph
    from ksp_planner.dv_map import plan_round_trip

    g = load_dv_graph(db)
    plan = plan_round_trip(g, [Stop("kerbin_surface"), Stop("mun_surface")])
    assert plan.total_raw == pytest.approx(10300, abs=5)
    assert plan.total_aerobraked == pytest.approx(6900, abs=5)
    assert plan.total_aerobraked_planned == pytest.approx(6900 * 1.05, abs=10)
    assert plan.aerobrake is True
    # Grand tour: 2 legs for outbound + return
    assert len(plan.legs) == 2


def test_plan_round_trip_kerbin_to_mun_no_aerobrake(db):
    """Without aerobrake, return Kerbin descent is fully ballistic — raw == aerobraked."""
    from ksp_planner.db import load_dv_graph
    from ksp_planner.dv_map import plan_round_trip

    g = load_dv_graph(db)
    plan = plan_round_trip(
        g, [Stop("kerbin_surface"), Stop("mun_surface")], aerobrake=False
    )
    assert plan.total_raw == pytest.approx(10300, abs=5)
    assert plan.total_aerobraked == plan.total_raw
    assert plan.aerobrake is False
```

- [ ] **Step 2.2: Run the new tests — expect fail**

Run: `cd "/Users/aj/Development/KSP App" && uv run pytest tests/test_dv_map.py -k "round_trip" -v`

Expected: FAIL with `ImportError: cannot import name 'plan_round_trip'` on each test.

- [ ] **Step 2.3: Implement `plan_round_trip`**

Append to `src/ksp_planner/dv_map.py`:

```python
def plan_round_trip(
    graph: DvGraph,
    stops: list[Stop],
    margin_pct: float = 5.0,
    aerobrake: bool = True,
) -> TripPlan:
    """Plan a round trip that returns to the starting stop.

    Doubles the itinerary: `[A, B]` → `[A, B, A]`; `[A, B, C]` → `[A, B, C, B, A]`.
    The doubled stops list is then passed to `plan_trip`, which produces legs for
    every pairwise hop. Composes with intermediate stops and aerobrake credit.
    """
    if len(stops) < 2:
        raise ValueError("round trip requires at least two stops")
    doubled = list(stops) + list(reversed(stops[:-1]))
    return plan_trip(graph, doubled, margin_pct=margin_pct, aerobrake=aerobrake)
```

- [ ] **Step 2.4: Run the new tests — expect pass**

Run: `cd "/Users/aj/Development/KSP App" && uv run pytest tests/test_dv_map.py -k "round_trip" -v`

Expected: all 5 new tests pass.

- [ ] **Step 2.5: Full suite check**

Run: `cd "/Users/aj/Development/KSP App" && make test`

Expected: 197 tests pass (192 + 5 new).

- [ ] **Step 2.6: Commit**

```bash
cd "/Users/aj/Development/KSP App"
git add src/ksp_planner/dv_map.py tests/test_dv_map.py
git commit -m "$(cat <<'EOF'
feat(7d): add plan_round_trip for A→B→A itineraries

Thin wrapper that doubles the stops list and delegates to plan_trip.
Composes with --via so [A, B, C] round-trips as [A, B, C, B, A]. Shape
foundation for future multi-stop round trips.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: `--return` CLI flag

**Files:**
- Modify: `src/ksp_planner/cli.py:312-356` (`dv` command)
- Modify: `tests/test_cli.py` (add new test block)

- [ ] **Step 3.1: Write failing CLI tests**

Append to `tests/test_cli.py`:

```python
# ---------- 7d: --return ----------


def test_dv_return_flag_round_trips_kerbin_to_mun(seed_db):
    """--return doubles the itinerary; aerobrake credits Kerbin return descent."""
    r = _invoke(seed_db, "dv", "kerbin_surface", "mun_surface", "--return")
    assert r.exit_code == 0
    # Round-trip raw = 10,300; aerobraked = 6,900; planned @ 5% = 7,245
    assert "10,300" in r.stdout
    assert "6,900" in r.stdout
    assert "7,245" in r.stdout


def test_dv_return_flag_no_aerobrake(seed_db):
    """--return --no-aerobrake: raw 10,300, planned 10,815, no aerobraked row."""
    r = _invoke(
        seed_db, "dv", "kerbin_surface", "mun_surface", "--return", "--no-aerobrake"
    )
    assert r.exit_code == 0
    assert "10,300" in r.stdout
    assert "10,815" in r.stdout  # 10,300 × 1.05
    assert "With aerobrake" not in r.stdout


def test_dv_return_composes_with_via(seed_db):
    """--via + --return: [A, B, C] → [A, B, C, B, A] — 4 legs."""
    r = _invoke(
        seed_db, "dv", "kerbin_surface", "minmus_surface",
        "--via", "mun:orbit", "--return",
    )
    assert r.exit_code == 0
    # The Mun intermediate stop should appear as an annotation row
    assert "stop: orbit (mun_low_orbit)" in r.stdout
    # And the title should advertise the via chain
    assert "mun(orbit)" in r.stdout


def test_dv_without_return_is_one_way(seed_db):
    """Regression: dropping --return leaves the default one-way behavior intact."""
    r = _invoke(seed_db, "dv", "kerbin_surface", "mun_surface")
    assert r.exit_code == 0
    # one-way raw 5,150 — not the round-trip 10,300
    assert "5,150" in r.stdout
    assert "10,300" not in r.stdout
```

- [ ] **Step 3.2: Run — expect fail**

Run: `cd "/Users/aj/Development/KSP App" && uv run pytest tests/test_cli.py -k "return" -v`

Expected: three tests fail (Typer reports `--return` as unknown option), one passes (the "without --return" regression test is already correct behavior).

- [ ] **Step 3.3: Add `--return` to the `dv` command**

Edit `src/ksp_planner/cli.py`.

At line 14, replace:
```python
from ksp_planner.dv_map import Stop, plan_trip, resolve_stop
```
with:
```python
from ksp_planner.dv_map import Stop, plan_round_trip, plan_trip, resolve_stop
```

Replace the `dv` command (lines 312-355) with:

```python
@app.command()
def dv(
    from_slug: Annotated[str, typer.Argument(help="Departure node slug, e.g. kerbin_surface")],
    to_slug: Annotated[str, typer.Argument(help="Arrival node slug, e.g. mun_surface")],
    via: Annotated[
        list[str] | None,
        typer.Option(
            "--via",
            help="Intermediate stop as body[:action]. Repeatable. action ∈ land|orbit|flyby, default orbit.",  # noqa: E501
        ),
    ] = None,
    margin: Annotated[
        float,
        typer.Option("--margin", "-m", help="Margin percentage on the raw total"),
    ] = 5.0,
    aerobrake: Annotated[
        bool,
        typer.Option(
            "--aerobrake/--no-aerobrake",
            help="Credit can_aerobrake=True descent edges. Default on.",
        ),
    ] = True,
    return_: Annotated[
        bool,
        typer.Option(
            "--return",
            help="Round-trip: append the reversed itinerary so the trip ends at the start.",
        ),
    ] = False,
    db: DbOption = Path("ksp.db"),
):
    """Walk the canonical Δv chart from one node to another and total the cost."""
    conn = _open(db)
    graph = dblib.load_dv_graph(conn)

    stops: list[Stop] = [Stop(from_slug.lower())]
    for raw in via or []:
        try:
            body, action = _parse_via(raw)
            stops.append(resolve_stop(graph, body.lower(), action.lower()))
        except (ValueError, KeyError) as e:
            console.print(f"[red]{e}[/]")
            raise typer.Exit(1) from None
    stops.append(Stop(to_slug.lower()))

    planner = plan_round_trip if return_ else plan_trip
    try:
        trip = planner(graph, stops, margin_pct=margin, aerobrake=aerobrake)
    except KeyError as e:
        console.print(f"[red]{e}[/]")
        raise typer.Exit(1) from None
    console.print(dv_trip_panel(trip, from_slug.lower(), to_slug.lower()))
```

- [ ] **Step 3.4: Run — expect pass**

Run: `cd "/Users/aj/Development/KSP App" && uv run pytest tests/test_cli.py -k "return" -v`

Expected: all 4 tests pass.

- [ ] **Step 3.5: Manual smoke check**

Run: `cd "/Users/aj/Development/KSP App" && uv run ksp dv kerbin_surface mun_surface --return`

Expected: panel shows outbound + return legs, turnaround stop annotation at Mun surface, raw total 10,300 m/s, "With aerobrake" 6,900 m/s, planned 7,245 m/s.

- [ ] **Step 3.6: Full suite check**

Run: `cd "/Users/aj/Development/KSP App" && make test`

Expected: 201 tests pass (197 + 4 new).

- [ ] **Step 3.7: Commit**

```bash
cd "/Users/aj/Development/KSP App"
git add src/ksp_planner/cli.py tests/test_cli.py
git commit -m "$(cat <<'EOF'
feat(7d): add --return flag to ksp dv

--return dispatches to plan_round_trip, producing A→…→A itineraries.
Composes with --via for multi-stop round trips. Acceptance:
ksp dv kerbin_surface mun_surface --return → raw 10,300, aerobraked 6,900.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Phase-close ritual

**Files:**
- Modify: `docs/PROGRESS.md` (add 7d completion log + 7e resume notes; bump test/status counts)

- [ ] **Step 4.1: Final full-suite + lint green check**

Run: `cd "/Users/aj/Development/KSP App" && make test && make lint`

Expected: all tests pass, ruff check clean.

- [ ] **Step 4.2: Simplify review on changed files**

Run the `/simplify` skill against the diff from this sub-phase. Focus files:
- `src/ksp_planner/dv_map.py` (new `plan_round_trip` + constant change)
- `src/ksp_planner/formatting.py` (dynamic aero label)
- `src/ksp_planner/cli.py` (`--return` flag)

Apply any safe simplifications directly. If the skill proposes a change that would affect test assertions, pause and ask.

- [ ] **Step 4.3: Update `docs/PROGRESS.md`**

In `docs/PROGRESS.md`:

1. Update the header (`Last updated:`, `Tests:`, `Coverage:`) at lines 5-6 to reflect the current session date, the new test total (should be 201), and current coverage.

2. Update the Phase 7 row in the Phases table (line 21) from:
   ```
   | 7 | Δv planner (tree model, margin, stops) | 🟡 in progress (7a ✅; 7b ✅; 7c ✅; 7d next) | ...
   ```
   to:
   ```
   | 7 | Δv planner (tree model, margin, stops) | 🟡 in progress (7a ✅; 7b ✅; 7c ✅; 7d ✅; 7e next) | ...
   ```

3. Update the Phase 7 breakdown sub-table (line 42) from `⬜ not started` to `✅ done` for row 7d, and add a note that 7d was re-scoped (stage-budget-check dropped in favor of round-trip + residual fix).

4. Add a new `### Phase 7d completion log` section after the 7c log, covering:
   - Scope decision: original stage-aware Tsiolkovsky check dropped as unnecessary; current per-edge output already supports in-game stage planning.
   - Residual flip from 20% → 0% (community-chart convention); 7c pins updated in lockstep.
   - `plan_round_trip` as thin `plan_trip` wrapper doubling the itinerary.
   - `--return` CLI flag; composes with `--via`.
   - Acceptance: `kerbin_surface → mun_surface --return` = 10,300 raw / 6,900 aerobraked / 7,245 @ 5%.
   - Dynamic aerobrake label in renderer (tracks `AEROBRAKE_RESIDUAL_PCT`).

5. Replace the `### 7d resume point — Stage-aware budget check` block at lines 103-118 with `### 7e resume point — Graph upgrade (Dijkstra + inter-moon shortcuts)`:
   - Spec reference: feature doc §7e.
   - Next step: research which inter-moon shortcuts the community chart actually publishes canonical values for (Mun↔Minmus, Laythe↔Vall, etc.). Enumerate candidate edges before touching code.
   - After that: swap LCA walk for Dijkstra, add shortcut adjacencies to the seed, confirm public API (`path_dv`, `plan_trip`, `plan_round_trip`) is unchanged.
   - Acceptance gate: `ksp dv laythe_low_orbit vall_low_orbit` picks the direct route instead of routing via Jool LO.
   - Flag the existing 7c double-credit quirk on pre-baked capture edges (Eve 80, Duna 360, Kerbin 0) as a candidate to address in 7e since the graph is being revisited.

6. Update the "Running the app" examples section (around line 210) to add:
   ```
   uv run ksp dv kerbin_surface mun_surface --return                        # Phase 7d
   uv run ksp dv kerbin_surface minmus_surface --via mun:orbit --return     # Phase 7d
   ```

7. Update "Key decisions" item 11 (AEROBRAKE_RESIDUAL_PCT at lines 180-181) to reflect the 7d change: the constant is now 0.0; 5% trip margin is the safety buffer; note the 20%-era value is preserved in git history. Keep the double-credit quirk note; it's now slightly smaller in absolute terms (all three edges round to 0 under full credit) but still deferred to 7e.

- [ ] **Step 4.4: Commit docs**

```bash
cd "/Users/aj/Development/KSP App"
git add docs/PROGRESS.md
git commit -m "$(cat <<'EOF'
docs(7d): complete phase — round-trip + residual 0%; add 7e resume notes

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 4.5: Announce reset**

Surface a short status to the user:
- What shipped (round-trip + residual).
- Test total.
- Where 7e picks up (graph upgrade, Dijkstra, inter-moon shortcuts) per the updated resume notes.
- Stop.

---

## Notes on type consistency and spec coverage

**Function/type names used across tasks:**
- `plan_round_trip(graph, stops, margin_pct, aerobrake) -> TripPlan` — defined Task 2, referenced Task 3.
- `AEROBRAKE_RESIDUAL_PCT` — constant, unchanged name; value 20.0 → 0.0 in Task 1.
- `TripPlan`, `Stop`, `Edge`, `DvGraph` — unchanged from 7a/7b/7c.
- `--return` is the CLI flag; the Python parameter is `return_` (Python keyword collision).

**Spec coverage check:**
- Residual 0% change (§1) → Task 1. ✓
- `plan_round_trip` doubling rule (§2) → Task 2. ✓
- `--return` CLI flag (§3) → Task 3. ✓
- Renderer unchanged — verified handled in Task 1 (dynamic label is a byproduct, not a new rendering mode). ✓
- Acceptance values (6,900 aerobraked round-trip) → Task 2.4 + Task 3.5 smoke check. ✓
- 7c pin updates (Duna, Eve, CLI) → Task 1.2–1.4. ✓
- Phase-close ritual → Task 4. ✓
