# Phase 7c — Aerobrake credit implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [docs/superpowers/specs/2026-04-22-dv-planner-7c-design.md](../specs/2026-04-22-dv-planner-7c-design.md)

**Goal:** Add aerobraking support to one-way `plan_trip`. `TripPlan` grows three fields (`total_aerobraked`, `aerobrake`, `total_aerobraked_planned`); CLI gets `--no-aerobrake`; renderer shows dual totals and a tri-state `aero` column. Round-trip `--return` is explicitly out of scope.

**Architecture:** Pure extension of 7a/7b `dv_map.py` — add `AEROBRAKE_RESIDUAL_PCT=20.0` constant and thread an `aerobrake: bool` kwarg through `plan_trip`. Renderer reads `trip.aerobrake` and adds one totals row when True. CLI adds a Typer boolean flag that passes through. No schema, seed, or DB changes.

**Tech Stack:** Python 3.12, Typer, Rich, pytest, SQLite3 (stdlib), `uv` toolchain.

**Conventions baked into this plan (match existing code):**

- TDD throughout: every task writes the failing test first, runs it to see it fail, implements, runs it to see it pass.
- Unit tests in `tests/test_dv_map.py` use the existing hand-built `tree` fixture (no DB). Integration tests use the session-scoped `db` fixture (RO seeded copy). CLI tests in `tests/test_cli.py` use `_invoke(seed_db, *args)`.
- Commands run via `uv run` (e.g. `uv run pytest tests/test_dv_map.py -v`).
- Commit per task. One-line imperative subjects (`feat(7c): ...`, `refactor(7c): ...`, `test(7c): ...`); body explains *why* when non-obvious.
- Lint clean at end (`uv run ruff check`).

---

## File structure

| File | What changes |
|---|---|
| `src/ksp_planner/dv_map.py` | Add `AEROBRAKE_RESIDUAL_PCT = 20.0` constant; add `total_aerobraked`, `aerobrake`, `total_aerobraked_planned` fields to `TripPlan`; add `aerobrake: bool = True` kwarg to `plan_trip` and compute credit. |
| `src/ksp_planner/formatting.py` | Update `dv_trip_panel` — `aero` column becomes tri-state; totals block adds a `"With aerobrake"` row when `trip.aerobrake`. |
| `src/ksp_planner/cli.py` | Extend `dv()` command: add `--no-aerobrake` boolean option; pass through to `plan_trip`. |
| `tests/test_dv_map.py` | 6 unit tests against the hand-built `tree` fixture + 3 integration tests against the real seed. |
| `tests/test_cli.py` | 4 new CLI tests; possibly tweak 1 existing assertion if the new totals row shifts something. |
| `docs/PROGRESS.md` | 7c completion log + 7d resume notes (final task). |

**Files untouched:** `seeds/schema.sql`, `seeds/seed_stock.py`, `src/ksp_planner/db.py`, `src/ksp_planner/orbital.py`, `src/ksp_planner/comms.py`, `src/ksp_planner/plans.py`.

---

## Task 0: Baseline check

> **Why:** 7c branches from the 7b baseline (`main` at `b0edd41`, 179 tests, clean tree). Before starting, verify the baseline is healthy.

- [ ] **Step 1: Verify clean tree + green tests**

```bash
git status
uv run pytest
uv run ruff check
```

Expected: `nothing to commit, working tree clean`; 179 passing; ruff clean. If anything fails, stop and investigate — do not proceed onto a dirty or failing baseline.

---

## Task 1: Core — `AEROBRAKE_RESIDUAL_PCT`, `TripPlan` fields, `plan_trip(aerobrake=...)` credit math

**Files:**
- Modify: `src/ksp_planner/dv_map.py` (add constant, extend dataclass, extend function)
- Modify: `tests/test_dv_map.py` (6 hand-built unit tests + 3 real-seed integration tests)

- [ ] **Step 1: Write the failing unit tests**

Append to `tests/test_dv_map.py` (after `test_plan_trip_requires_two_stops`, before the `# ---------- seed integration:` section header around line 153):

```python
# ---------- 7c: aerobrake credit ----------


@pytest.fixture
def aero_tree() -> DvGraph:
    """Minimal tree where one descent edge (a→d) is flagged can_aerobrake=True.

           root
            |
            a
          (a↔d: up=2, down=1000, aerobrake_on_descent)
            |
            d
    """
    nodes = [
        DvNode(slug="root", parent_slug=None, body_slug=None, state="sun_orbit"),
        DvNode(slug="a",    parent_slug="root", body_slug=None, state="transfer"),
        DvNode(slug="d",    parent_slug="a",    body_slug=None, state="low_orbit"),
    ]
    edges = [
        # parent→child=down has can_aerobrake=True; child→parent=up has False
        Edge(from_slug="root", to_slug="a", dv_m_s=100, can_aerobrake=False),
        Edge(from_slug="a", to_slug="root", dv_m_s=10,  can_aerobrake=False),
        Edge(from_slug="a", to_slug="d",    dv_m_s=1000, can_aerobrake=True),
        Edge(from_slug="d", to_slug="a",    dv_m_s=2,    can_aerobrake=False),
    ]
    return DvGraph(nodes=nodes, edges=edges)


def test_plan_trip_aerobrake_credits_capable_edge(aero_tree):
    """1000 m/s descent with can_aerobrake=True → credited to 200 at 20% residual."""
    plan = plan_trip(aero_tree, [Stop("a"), Stop("d")])
    # raw = 1000 (single descent edge)
    assert plan.total_raw == 1000
    # aerobraked = 1000 * 0.20 = 200
    assert plan.total_aerobraked == pytest.approx(200.0)
    assert plan.aerobrake is True


def test_plan_trip_aerobrake_false_is_noop(aero_tree):
    """aerobrake=False: total_aerobraked == total_raw (no credit applied)."""
    plan = plan_trip(aero_tree, [Stop("a"), Stop("d")], aerobrake=False)
    assert plan.total_raw == 1000
    assert plan.total_aerobraked == 1000
    assert plan.aerobrake is False


def test_plan_trip_mixed_edges_only_discounts_flagged(tree):
    """The existing `tree` fixture has can_aerobrake=False on every edge — no credit."""
    plan = plan_trip(tree, [Stop("c"), Stop("f")])  # raw 27 via c→a→d→f
    assert plan.total_raw == 27
    assert plan.total_aerobraked == 27  # no flagged edges in the tree fixture


def test_plan_trip_aerobrake_planned_applies_margin(aero_tree):
    """total_aerobraked_planned == total_aerobraked * (1 + margin/100)."""
    plan = plan_trip(aero_tree, [Stop("a"), Stop("d")])  # default 5%
    assert plan.total_aerobraked == pytest.approx(200.0)
    assert plan.total_aerobraked_planned == pytest.approx(200.0 * 1.05)


def test_plan_trip_aerobrake_planned_scales_with_custom_margin(aero_tree):
    plan = plan_trip(aero_tree, [Stop("a"), Stop("d")], margin_pct=10.0)
    assert plan.total_aerobraked_planned == pytest.approx(200.0 * 1.10)


def test_plan_trip_aerobrake_residual_constant_is_20():
    """Sanity-pin the module constant so a future edit is caught by CI."""
    from ksp_planner.dv_map import AEROBRAKE_RESIDUAL_PCT

    assert AEROBRAKE_RESIDUAL_PCT == 20.0
```

- [ ] **Step 2: Run unit tests to verify they fail**

```bash
uv run pytest tests/test_dv_map.py -v -k "aerobrake or RESIDUAL"
```

Expected: 6 failures — all variations of `AttributeError: 'TripPlan' object has no attribute 'total_aerobraked'` or `ImportError: cannot import name 'AEROBRAKE_RESIDUAL_PCT'`.

- [ ] **Step 3: Implement the core changes in `dv_map.py`**

In `src/ksp_planner/dv_map.py`, make three changes:

**3a.** Add the module constant just after `ACTION_SUFFIXES` (around line 49):

```python
# 20% residual = aerobrake credits 80% of a can_aerobrake edge's ballistic dv.
# Residual covers correction burns, safety margin, and imperfect atmospheric passes.
AEROBRAKE_RESIDUAL_PCT = 20.0
```

**3b.** Extend the `TripPlan` dataclass (around lines 36-42):

```python
@dataclass(frozen=True)
class TripPlan:
    stops: list[Stop]
    legs: list[list[Edge]]
    total_raw: float
    total_aerobraked: float
    aerobrake: bool
    margin_pct: float
    total_planned: float
    total_aerobraked_planned: float
```

**3c.** Replace the `plan_trip` function (around lines 120-135) with:

```python
def plan_trip(
    graph: DvGraph,
    stops: list[Stop],
    margin_pct: float = 5.0,
    aerobrake: bool = True,
) -> TripPlan:
    if len(stops) < 2:
        raise ValueError("trip requires at least two stops")
    legs = [path_dv(graph, a.slug, b.slug) for a, b in pairwise(stops)]
    raw = sum(e.dv_m_s for leg in legs for e in leg)

    residual_factor = AEROBRAKE_RESIDUAL_PCT / 100
    if aerobrake:
        aerobraked = sum(
            e.dv_m_s * residual_factor if e.can_aerobrake else e.dv_m_s
            for leg in legs
            for e in leg
        )
    else:
        aerobraked = raw

    margin_factor = 1 + margin_pct / 100
    return TripPlan(
        stops=stops,
        legs=legs,
        total_raw=raw,
        total_aerobraked=aerobraked,
        aerobrake=aerobrake,
        margin_pct=margin_pct,
        total_planned=raw * margin_factor,
        total_aerobraked_planned=aerobraked * margin_factor,
    )
```

- [ ] **Step 4: Run unit tests to verify they pass**

```bash
uv run pytest tests/test_dv_map.py -v -k "aerobrake or RESIDUAL"
```

Expected: 6 passing.

- [ ] **Step 5: Write the failing integration tests (real seed)**

Append to `tests/test_dv_map.py` at the very bottom:

```python
# ---------- 7c: integration — real-seed aerobrake ----------


def test_kerbin_to_duna_surface_aerobraked_totals(db):
    """kerbin→duna: raw 6,270 (unchanged); aerobraked ≈ 4,822 (duna capture 360→72, duna descent 1450→290)."""
    from ksp_planner.db import load_dv_graph

    g = load_dv_graph(db)
    plan = plan_trip(g, [Stop("kerbin_surface"), Stop("duna_surface")])
    assert plan.total_raw == pytest.approx(6270, abs=5)
    assert plan.total_aerobraked == pytest.approx(4822, abs=5)
    assert plan.total_aerobraked_planned == pytest.approx(4822 * 1.05, abs=10)
    assert plan.aerobrake is True


def test_kerbin_to_mun_surface_aerobrake_is_noop(db):
    """kerbin→mun: path has no can_aerobrake=True edges, so aerobraked == raw."""
    from ksp_planner.db import load_dv_graph

    g = load_dv_graph(db)
    plan = plan_trip(g, [Stop("kerbin_surface"), Stop("mun_surface")])
    assert plan.total_raw == pytest.approx(5150, abs=5)
    assert plan.total_aerobraked == plan.total_raw


def test_kerbin_to_eve_surface_aerobraked_shows_dramatic_savings(db):
    """Eve descent (8000 ballistic) credited at 80% → ~1,600 + small double-credit quirk on capture."""
    from ksp_planner.db import load_dv_graph

    g = load_dv_graph(db)
    plan = plan_trip(g, [Stop("kerbin_surface"), Stop("eve_surface")])
    # Outbound: 3400 + 0 + 0 + 0 + 0 + 1080 + 80 + 8000 = 12,560
    # With aerobrake: 3400 + 0 + 0 + 0 + 0 + 1080 + 16 + 1600 = 6,096
    # (the eve_capture→eve_low_orbit 80 is already chart-baked; double-credit → 16 residual, accepted per spec)
    assert plan.total_raw == pytest.approx(12560, abs=10)
    assert plan.total_aerobraked == pytest.approx(6096, abs=10)
    # savings should be large (> 6000 m/s)
    assert plan.total_raw - plan.total_aerobraked > 6000
```

- [ ] **Step 6: Run integration tests to verify they pass**

```bash
uv run pytest tests/test_dv_map.py -v -k "kerbin_to_duna_surface_aerobraked or kerbin_to_mun_surface_aerobrake or kerbin_to_eve_surface_aerobraked"
```

Expected: 3 passing. If the kerbin→duna number is off by more than 5 from 4,822 or the Eve number is off by more than 10 from 6,096, stop and trace the seed edges by hand (see spec §Example) — the acceptance number may need updating.

- [ ] **Step 7: Run full suite**

```bash
uv run pytest
```

Expected: 188 passing (179 + 6 unit + 3 integration). All existing tests still pass because `total_raw` is unchanged and no caller reads the new fields yet.

- [ ] **Step 8: Commit**

```bash
git add src/ksp_planner/dv_map.py tests/test_dv_map.py
git commit -m "$(cat <<'EOF'
feat(7c): add aerobrake credit to plan_trip

TripPlan gains total_aerobraked, aerobrake, total_aerobraked_planned
fields. plan_trip accepts aerobrake=True; when on, can_aerobrake=True
edges contribute only AEROBRAKE_RESIDUAL_PCT (20%) of their ballistic
dv_m_s. total_raw is unchanged — always the ballistic sum.

Seed quirk: edges like eve_capture→eve_low_orbit (80 m/s) already have
chart-baked aerobrake; applying the 20% residual double-discounts them.
Error bounded, accepted per spec; fix deferred to 7e.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Renderer — `dv_trip_panel` dual totals + tri-state `aero` column

**Files:**
- Modify: `src/ksp_planner/formatting.py` (update `dv_trip_panel` around lines 170-234)
- Modify: `tests/test_cli.py` (2 new CLI-rendered tests; no-CLI render unit tests not needed since CLI tests exercise the renderer end-to-end)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cli.py` at the very bottom:

```python
# ---------- 7c: aerobrake rendering ----------


def test_dv_kerbin_to_duna_shows_with_aerobrake_row(seed_db):
    """Default (aerobrake on): panel shows 'With aerobrake' totals row."""
    r = _invoke(seed_db, "dv", "kerbin_surface", "duna_surface")
    assert r.exit_code == 0, r.stdout
    assert "Raw total" in r.stdout
    assert "With aerobrake" in r.stdout
    # raw 6,270; aerobraked 4,822; planned aerobraked 5,063
    assert "6,270" in r.stdout
    assert "4,822" in r.stdout


def test_dv_aerobrake_column_marks_credited_edges(seed_db):
    """The aero column shows '−80%' on can_aerobrake=True edges when aerobrake is on."""
    r = _invoke(seed_db, "dv", "kerbin_surface", "duna_surface")
    assert r.exit_code == 0, r.stdout
    # Duna descent and duna_capture→duna_low_orbit are both creditable
    assert "−80%" in r.stdout or "-80%" in r.stdout  # accept either hyphen shape
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_cli.py -v -k "dv_kerbin_to_duna_shows_with_aerobrake or dv_aerobrake_column_marks"
```

Expected: 2 failures — `"With aerobrake" not in stdout`, `"−80%" not in stdout`.

- [ ] **Step 3: Update `dv_trip_panel` in `formatting.py`**

Replace the `dv_trip_panel` function (currently around lines 170-234) with:

```python
def dv_trip_panel(trip, from_slug: str, to_slug: str) -> Panel:
    """Render a `TripPlan` as a per-leg table + raw, aerobrake, and margin totals.

    When the trip has intermediate stops, a `stop: <action> (<slug>)` row is
    inserted between legs for each intermediate stop.

    The `aero` column is tri-state:
        - "✓ −80%"  : edge is can_aerobrake=True and trip.aerobrake is True
        - "✓ off"   : edge is can_aerobrake=True but trip.aerobrake is False
        - ""        : edge cannot be aerobraked

    The totals block renders an extra "With aerobrake" row when trip.aerobrake
    is True, even if the savings are zero (keeps output shape predictable).
    """
    intermediate_stops = trip.stops[1:-1]

    # Ensure the From column is wide enough to show the annotation on one line
    annotation_width = max(
        (len(f"— stop: {s.action} ({s.slug}) —") for s in intermediate_stops),
        default=0,
    )

    legs_table = Table(box=box.SIMPLE_HEAVY, show_header=True, header_style="dim")
    legs_table.add_column("From", min_width=annotation_width if annotation_width else None)
    legs_table.add_column("→")
    legs_table.add_column("To")
    legs_table.add_column("Δv", justify="right")
    legs_table.add_column("aero", justify="center")

    def _aero_cell(edge) -> str:
        if not edge.can_aerobrake:
            return ""
        return "✓ −80%" if trip.aerobrake else "✓ off"

    for leg_idx, leg in enumerate(trip.legs):
        for edge in leg:
            legs_table.add_row(
                edge.from_slug,
                "→",
                edge.to_slug,
                f"{edge.dv_m_s:>7,.0f} m/s",
                _aero_cell(edge),
            )
        # Emit stop annotation after each leg except the last
        if leg_idx < len(intermediate_stops):
            stop = intermediate_stops[leg_idx]
            legs_table.add_row(
                f"[dim italic]— stop: {stop.action} ({stop.slug}) —[/]",
                "",
                "",
                "",
                "",
            )

    totals = Table.grid(padding=(0, 2))
    totals.add_column(style="dim")
    totals.add_column(justify="right")
    totals.add_row("Raw total", f"[bold]{trip.total_raw:,.0f} m/s[/]")
    if trip.aerobrake:
        savings = trip.total_raw - trip.total_aerobraked
        totals.add_row(
            "With aerobrake",
            f"[bold]{trip.total_aerobraked:,.0f} m/s[/]  [dim](−{savings:,.0f})[/]",
        )
        planned = trip.total_aerobraked_planned
    else:
        planned = trip.total_planned
    totals.add_row(
        f"Planned (+{trip.margin_pct:g}% margin)",
        f"[bold green]{planned:,.0f} m/s[/]",
    )

    # Title includes the via chain in body(action) form when present
    if intermediate_stops:
        via_chain = " → ".join(
            f"{s.slug.removesuffix(ACTION_SUFFIXES[s.action])}({s.action})"
            for s in intermediate_stops
        )
        title = f"[bold]Δv trip — {from_slug} → {via_chain} → {to_slug}[/]"
    else:
        title = f"[bold]Δv trip — {from_slug} → {to_slug}[/]"

    return Panel(
        Group(legs_table, Text(""), totals),
        title=title,
        box=box.ROUNDED,
    )
```

> **Note:** The `_aero_cell` helper uses U+2212 (−, "minus sign") for the "−80%" label to match Rich's typographic conventions. The test accepts either U+2212 or ASCII hyphen-minus so the assertion doesn't become brittle.

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_cli.py -v -k "dv_kerbin_to_duna_shows_with_aerobrake or dv_aerobrake_column_marks"
```

Expected: 2 passing. The acceptance probe will now show `"Raw total"` + `"With aerobrake"` + `"Planned (+5% margin)"` for aerobrake-capable trips.

- [ ] **Step 5: Run full suite**

```bash
uv run pytest
```

Expected: 190 passing (188 + 2). If any existing `test_dv_*` test fails because its assertion string landed on a now-slightly-different line, update the substring assertion to use a markup-agnostic, position-agnostic fragment (e.g. `"5,150" in stdout` is still fine; do not assert on exact line ordering).

Specifically check:
- `test_dv_kerbin_to_mun_acceptance` — expects `"5,408"` (planned total). With aerobrake on by default and no creditable edges on kerbin→mun, `total_aerobraked_planned == 5150 * 1.05 == 5,408`, so this still passes.
- `test_dv_via_orbit_totals_match_chart` — expects `"7,330 m/s"` (raw). Still appears in the `Raw total` row.

- [ ] **Step 6: Visual spot-check**

```bash
uv run ksp dv kerbin_surface duna_surface
uv run ksp dv kerbin_surface mun_surface
uv run ksp dv kerbin_surface mun_surface --via minmus:orbit
```

Eyeball-check that:
- Duna trip shows the `With aerobrake` row with savings in parentheses.
- Mun trip shows the `With aerobrake` row but with savings `(−0)` (or the savings column reads zero — that's by design).
- Via-Minmus trip still annotates `stop: orbit (minmus_low_orbit)` between legs, and shows the `With aerobrake` row (even though savings are 0 — no creditable edges on this path).

- [ ] **Step 7: Commit**

```bash
git add src/ksp_planner/formatting.py tests/test_cli.py
git commit -m "$(cat <<'EOF'
feat(7c): render aerobrake credit in dv_trip_panel

Aero column is tri-state: "✓ −80%" on credited edges with aerobrake on,
"✓ off" when aerobrake is disabled, blank otherwise. Totals block gains
a "With aerobrake" row when trip.aerobrake is True; the Planned row
then uses total_aerobraked_planned. Two-point aerobrake-free trips
(e.g., kerbin→mun) still render the With-aerobrake row with (−0), by
design — consistent output shape, no special-casing.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: CLI — `--no-aerobrake` flag

**Files:**
- Modify: `src/ksp_planner/cli.py` (extend `dv()` command — add flag and pass to `plan_trip`)
- Modify: `tests/test_cli.py` (2 new tests covering the flag behavior)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cli.py` at the bottom:

```python
def test_dv_no_aerobrake_hides_with_aerobrake_row(seed_db):
    """--no-aerobrake: only Raw total + Planned, no 'With aerobrake' row."""
    r = _invoke(seed_db, "dv", "kerbin_surface", "duna_surface", "--no-aerobrake")
    assert r.exit_code == 0, r.stdout
    assert "Raw total" in r.stdout
    assert "With aerobrake" not in r.stdout
    # raw still 6,270
    assert "6,270" in r.stdout


def test_dv_no_aerobrake_aero_column_shows_off(seed_db):
    """--no-aerobrake: aero column on creditable edges shows '✓ off' not '−80%'."""
    r = _invoke(seed_db, "dv", "kerbin_surface", "duna_surface", "--no-aerobrake")
    assert r.exit_code == 0, r.stdout
    assert "off" in r.stdout
    assert "−80%" not in r.stdout and "-80%" not in r.stdout
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_cli.py -v -k "dv_no_aerobrake"
```

Expected: 2 failures — Typer reports `No such option: --no-aerobrake`.

- [ ] **Step 3: Extend the `dv` command in `cli.py`**

In `src/ksp_planner/cli.py`, replace the `dv` command (currently lines 312-348) with:

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
            help="Credit can_aerobrake=True descent edges at 80% savings. Default on.",
        ),
    ] = True,
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

    try:
        trip = plan_trip(graph, stops, margin_pct=margin, aerobrake=aerobrake)
    except KeyError as e:
        console.print(f"[red]{e}[/]")
        raise typer.Exit(1) from None
    console.print(dv_trip_panel(trip, from_slug.lower(), to_slug.lower()))
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_cli.py -v -k "dv_no_aerobrake"
```

Expected: 2 passing.

- [ ] **Step 5: Run full suite**

```bash
uv run pytest
```

Expected: 192 passing (190 + 2).

- [ ] **Step 6: Visual spot-check**

```bash
uv run ksp dv kerbin_surface duna_surface --no-aerobrake
```

Eyeball-check: no `With aerobrake` row, aero column shows `✓ off` on Duna capture + descent rows, `Raw total` and `Planned` are the only totals rows.

- [ ] **Step 7: Commit**

```bash
git add src/ksp_planner/cli.py tests/test_cli.py
git commit -m "$(cat <<'EOF'
feat(7c): add --no-aerobrake flag to ksp dv

Default is --aerobrake on; --no-aerobrake disables the credit and
hides the 'With aerobrake' totals row. Aero column flips to '✓ off'
when the flag is off, so the user can still see which edges would
have been creditable.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Acceptance sweep + lint

**Files:**
- None to edit in this task (sanity checks only).

- [ ] **Step 1: Run the acceptance gate invocations**

```bash
uv run ksp dv kerbin_surface duna_surface
uv run ksp dv kerbin_surface duna_surface --no-aerobrake
uv run ksp dv kerbin_surface mun_surface
uv run ksp dv kerbin_surface mun_surface --via minmus:orbit
uv run ksp dv kerbin_surface eve_surface
```

Expected observations:
- `kerbin→duna` default: `Raw total 6,270` · `With aerobrake 4,822 (−1,448)` · `Planned (+5%) 5,063`.
- `kerbin→duna --no-aerobrake`: `Raw total 6,270` · `Planned (+5%) 6,584` (= 6270 × 1.05).
- `kerbin→mun` default: `Raw total 5,150` · `With aerobrake 5,150 (−0)` · `Planned 5,408`.
- `kerbin→mun --via minmus:orbit` default: `Raw total 7,330` · `With aerobrake 7,330 (−0)` · `Planned 7,697`.
- `kerbin→eve` default: `Raw total 12,560` · `With aerobrake 6,096 (−6,464)` · `Planned ~6,401`.

If any row is off by more than ±10 from these targets, stop and trace the seed walk — likely a bug in the credit sum or a renderer row mismatch.

- [ ] **Step 2: Run full suite**

```bash
uv run pytest
```

Expected: 192 passing.

- [ ] **Step 3: Run lint**

```bash
uv run ruff check
```

Expected: clean.

- [ ] **Step 4: (If any of Steps 1-3 failed) fix + commit**

If ruff flags something, fix it inline and commit with `style(7c): ruff cleanup`. If the acceptance invocations showed a discrepancy, diagnose (likely in `dv_trip_panel` or `plan_trip`), fix, and commit with `fix(7c): ...`.

If everything is clean, skip to Task 5 — no commit in this task.

---

## Task 5: Phase close-out — update `PROGRESS.md`

**Files:**
- Modify: `docs/PROGRESS.md` (update header, flip 7c row, add 7c completion log, replace 7c resume notes with 7d resume notes).

- [ ] **Step 1: Update the header line**

At the top of `docs/PROGRESS.md`, update "Last updated" and "Tests":

```markdown
**Last updated:** 2026-04-22
**Tests:** 192 passing · **Lint:** clean · **Coverage:** 98% overall, 100% on `orbital.py` and `db.py`.
```

(Adjust the test count to match the actual `uv run pytest` output if different.)

- [ ] **Step 2: Flip the 7c row and update the Phase 7 summary**

In the sub-phase table (around line 37-43), change the 7c row to:

```markdown
| 7c | Aerobraking credit on one-way trips: `aerobrake` kwarg on `plan_trip`, `--no-aerobrake` CLI flag, tri-state aero column + dual totals. Round-trip `--return` deferred. | ✅ done | `ksp dv kerbin_surface duna_surface` shows raw 6,270 · with aerobrake 4,822 (−1,448 m/s Duna savings) |
```

And update the Phase 7 row (around line 21):

```markdown
| 7 | Δv planner (tree model, margin, stops) | 🟡 in progress (7a ✅; 7b ✅; 7c ✅; 7d next) | Design locked in [features/dv-planner.md](features/dv-planner.md); sub-phase ladder below |
```

- [ ] **Step 3: Add "Phase 7c completion log" section**

Insert after the existing `### Phase 7b completion log` section and before the (now-stale) `### 7c resume point` section:

```markdown
### Phase 7c completion log

Shipped with TDD throughout. 13 new tests; 179 → 192 total. Lint clean. Spec at [docs/superpowers/specs/2026-04-22-dv-planner-7c-design.md](superpowers/specs/2026-04-22-dv-planner-7c-design.md); executed per the plan at [docs/superpowers/plans/2026-04-22-dv-planner-7c.md](superpowers/plans/2026-04-22-dv-planner-7c.md).

- **Scope decision.** Dropped round-trip `--return` from 7c at the design step. Aerobrake on one-way trips ships as 7c; round-trip + return-leg aerobrake is deferred to a later sub-phase (`plan_round_trip` helper per feature-doc §API).
- **Core.** `dv_map.py` gained `AEROBRAKE_RESIDUAL_PCT = 20.0`. `TripPlan` grew three fields: `total_aerobraked`, `aerobrake`, `total_aerobraked_planned`. `plan_trip(..., aerobrake=True)` computes `total_aerobraked` by summing each edge's contribution — `can_aerobrake=True` edges contribute 20% of their `dv_m_s`, others contribute full. `total_raw` never changes with the flag — it's always the ballistic sum.
- **CLI.** `ksp dv` gained `--aerobrake/--no-aerobrake` (Typer boolean, default on). No change to `--via` / `--margin` behavior.
- **Renderer.** `dv_trip_panel` aero column is tri-state: `✓ −80%` when credited, `✓ off` when aerobrake is disabled, blank otherwise. Totals block adds a `With aerobrake` row with savings delta when `trip.aerobrake` is True, even if savings are zero (consistent output shape).
- **Acceptance.** `kerbin_surface → duna_surface` shows raw 6,270, aerobraked 4,822 (−1,448 Duna savings), planned 5,063 @ 5%. `kerbin→eve_surface` shows raw 12,560, aerobraked 6,096 (−6,464). `kerbin→mun_surface` is correctly a no-op (no creditable edges on the path).

**Known limitations** (documented as follow-ups, not blocking 7c):

- **Double-credit on pre-baked capture edges.** `eve_capture→eve_low_orbit` (80), `duna_capture→duna_low_orbit` (360), and `kerbin_capture→kerbin_low_orbit` (0) store chart values that already reflect aerobraking; crediting them again over-discounts by ≤ ~350 m/s across a full Eve+Duna+Kerbin outbound. Dominant savings (Kerbin/Duna/Eve/Laythe descents) are modeled correctly. Fix deferred to 7e when the graph model is revisited.
- **Configurable residual.** 20% is a module constant (`AEROBRAKE_RESIDUAL_PCT`). Can be promoted to a CLI flag (`--aerobrake-residual`) later if real usage shows the value should vary.
- **Round-trip / return-leg aerobrake** deferred. API sketched in feature doc: `plan_round_trip(stops, margin_pct, aerobrake)`.
```

- [ ] **Step 4: Replace the old "7c resume point" section with a "7d resume point"**

Replace the existing `### 7c resume point — Return trips + aerobraking` section (lines ~87-100) with:

```markdown
### 7d resume point — Stage-aware budget check

Spec lives in [features/dv-planner.md §7d](features/dv-planner.md#7d--stage-aware-budget-check). Inputs: staged ship as `list[(wet_kg, dry_kg, isp_s)]` + target trip. Use Tsiolkovsky (already in `orbital.py`) to compute available Δv per stage; verify coverage against planned legs; report which leg runs dry. Pairs with the Phase 5 TWR/Tsiolkovsky calculator — shared module.

**First concrete next step** for a fresh session:

1. Decide the data model: a new `Stage` dataclass in `dv_map.py` (or a new `budget.py` module), `list[Stage]` as the ship.
2. RED: `test_budget_covers_kerbin_to_mun_round_trip` — canned 3-stage Mun lander (ascent + transfer + lander) against a kerbin_surface → mun_surface → kerbin_surface trip; assert the budget report confirms coverage.
3. Decide the budget report shape. Suggested: `BudgetReport(legs: list[LegBudget], ok: bool, runs_dry_on: int | None)` where `LegBudget` tracks `required_dv`, `available_dv`, `remaining_after`.
4. Wire stage accounting: which stage serves which leg? Simplest v1 is "consume stages in order; a stage is used until exhausted, then drop to next". Per-leg stage assignment is a v2 concern.
5. CLI: `ksp dv-check <from> <to> --stage 9000,3000,345 --stage ... [--via ...] [--margin ...] [--no-aerobrake]`. Repeatable `--stage` with `wet,dry,isp` triple.
6. Acceptance gate: feature-doc §7d — canned Mun lander sheet confirms reach-and-return.

Files likely to change: `src/ksp_planner/dv_map.py` (or a new `budget.py`), `src/ksp_planner/cli.py`, plus tests.

Round-trip `--return` and `plan_round_trip` are still deferred — consider threading them in alongside 7d if the Mun-lander acceptance test needs round-trip semantics, otherwise defer further.
```

- [ ] **Step 5: Update the "Running the app" block**

Around line 168 of PROGRESS.md, add one or two 7c example invocations after the existing `ksp dv ...` lines:

```markdown
uv run ksp dv kerbin_surface duna_surface                                # Phase 7c (default: aerobrake on)
uv run ksp dv kerbin_surface duna_surface --no-aerobrake                 # Phase 7c (disable credit)
```

- [ ] **Step 6: Update the "Key decisions (non-obvious)" section**

Append a new numbered entry at the end of the list (the list currently ends at item 10 around line 162):

```markdown
11. **`can_aerobrake` credits 80% of ballistic dv** *(Phase 7c)*: `AEROBRAKE_RESIDUAL_PCT = 20.0` leaves a 20% residual rather than zeroing, covering correction burns, safety margin, and imperfect atmospheric passes. `total_raw` stays ballistic regardless of the flag — aerobrake only affects `total_aerobraked` and `total_aerobraked_planned`. Known quirk: the three pre-baked capture edges (Eve 80, Duna 360, Kerbin 0) are double-credited; error bounded to ≤ ~350 m/s; fix deferred to 7e.
```

- [ ] **Step 7: Verify the file renders correctly**

Skim PROGRESS.md. Expected section order: Phase table → Phase 6 log → Phase 7 breakdown → Phase 7a log → Phase 7b log → **Phase 7c log (new)** → 7d resume point (new) → Repo map → Key decisions → Running the app → Known gotchas → Memory files.

- [ ] **Step 8: Commit**

```bash
git add docs/PROGRESS.md
git commit -m "$(cat <<'EOF'
docs(7c): complete phase, add 7d resume notes

Phase 7c shipped: aerobrake credit on one-way trips via plan_trip's
aerobrake kwarg, --no-aerobrake CLI flag, tri-state aero column +
dual totals in dv_trip_panel. 13 new tests (179 → 192). Acceptance
probe kerbin_surface → duna_surface = 6,270 raw / 4,822 aerobraked
(−1,448 Duna savings) / 5,063 planned @ 5%. 7d resume notes document
the stage-aware budget check spec for the next session.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 9: Announce reset point**

Tell the user: "Phase 7c shipped. `PROGRESS.md` has the completion log + 7d resume notes. This is a clean stop point — ready for context reset."

---

## Non-goals (out of this plan)

- Return trips (`--return`) and `plan_round_trip` — deferred to a later sub-phase.
- Correcting double-credit on pre-baked capture edges — deferred to 7e.
- Configurable aerobrake residual via CLI (`--aerobrake-residual`) — deferred.
- Stage-aware budget check — 7d.
- Direct moon-to-moon edges / Dijkstra — 7e.

## Acceptance summary

After Task 5, the following should all be true:

- `uv run pytest` → 192 passing (exact count may shift ±2 if ruff/Typer version pins change).
- `uv run ruff check` → clean.
- `uv run ksp dv kerbin_surface duna_surface` → `Raw total 6,270` · `With aerobrake 4,822 (−1,448)` · `Planned (+5%) 5,063`.
- `uv run ksp dv kerbin_surface duna_surface --no-aerobrake` → `Raw total 6,270` · `Planned (+5%) 6,584`; no `With aerobrake` row; aero column on creditable edges shows `✓ off`.
- `uv run ksp dv kerbin_surface mun_surface` → `Raw total 5,150` · `With aerobrake 5,150 (−0)` · `Planned (+5%) 5,408`.
- `uv run ksp dv kerbin_surface mun_surface --via minmus:orbit` → 7b behavior unaffected; `With aerobrake` row present showing (−0).
- `docs/PROGRESS.md`: 7c row = ✅; 7c completion log present; 7d resume notes present.
