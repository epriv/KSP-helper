# Phase 7b — Intermediate Stops Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [docs/superpowers/specs/2026-04-21-dv-planner-7b-design.md](../specs/2026-04-21-dv-planner-7b-design.md)

**Goal:** Grow the Δv planner from two-point totals to N-stop itineraries. Each intermediate stop takes an `action` (`land` / `orbit` / `flyby`) that resolves to a concrete tree node. CLI gets repeatable `--via body[:action]`.

**Architecture:** Pure extension of 7a's `dv_map.py` — add an action→slug resolver and thread `stops` through `TripPlan`. CLI parses colon-paired `--via` values and hands a resolved `Stop` list to existing `plan_trip`. Renderer annotates intermediate stops. No schema, seed, or DB changes.

**Tech Stack:** Python 3.12, Typer, Rich, pytest, SQLite3 (stdlib), `uv` toolchain.

**Conventions baked into this plan (match existing code):**

- TDD throughout: every task writes the failing test first, runs it to see it fail, implements, runs it to see it pass.
- Tests in `tests/test_dv_map.py` use a hand-built `DvGraph` fixture (no DB). Tests in `tests/test_cli.py` invoke via `_invoke(seed_db, *args)` which uses Typer's `CliRunner` + the session-scoped RO seed.
- Commands run via `uv run` (e.g. `uv run pytest tests/test_dv_map.py -v`).
- Commit per task. One-line imperative subjects (`feat(7b): ...`, `refactor(7b): ...`, `test(7b): ...`); body explains *why* when non-obvious.
- Lint clean at end (`uv run ruff check`).

---

## File structure

| File | What changes |
|---|---|
| `src/ksp_planner/dv_map.py` | Add `ACTION_SUFFIXES` dict + `resolve_stop()` function; add `stops: list[Stop]` field to `TripPlan` and thread through `plan_trip()`. |
| `src/ksp_planner/cli.py` | Extend `dv()` command: add `--via` list option, parse colon-pair syntax, call `resolve_stop` for each via, build full `Stop` list before `plan_trip`. |
| `src/ksp_planner/formatting.py` | `dv_trip_panel` accepts the full `TripPlan` and emits one annotation row between legs for each intermediate stop; update title to include via chain. |
| `tests/test_dv_map.py` | New body-style fixture for resolver tests; 6 resolver unit tests; 1 `stops`-field assertion on existing `plan_trip` test. |
| `tests/test_cli.py` | 8 new `--via` / error-path tests. |
| `docs/PROGRESS.md` | 7b completion log + 7c resume notes (final task). |

**Files untouched:** `seeds/schema.sql`, `seeds/seed_stock.py`, `src/ksp_planner/db.py`, anything in `orbital.py` / `comms.py` / `plans.py`.

---

## Task 0: Commit pending 7a work as a baseline

> **Why:** There are uncommitted 7a artifacts in the repo (`seeds/schema.sql`, `seeds/seed_stock.py`, `src/ksp_planner/{cli,db,dv_map,formatting}.py`, `tests/test_{cli,dv_map}.py`, `docs/PROGRESS.md`). 7b changes must land on a clean 7a baseline so the diff is readable. **Pause here and confirm with the user before committing — these are files the user wrote.**

**Files:**
- Modify (commit): `docs/PROGRESS.md`, `seeds/schema.sql`, `seeds/seed_stock.py`, `src/ksp_planner/cli.py`, `src/ksp_planner/db.py`, `src/ksp_planner/formatting.py`, `tests/test_cli.py`
- Create (commit): `src/ksp_planner/dv_map.py`, `tests/test_dv_map.py`

- [ ] **Step 1: Confirm with user**

Ask: "Ready to commit the uncommitted 7a work as a baseline before starting 7b?" Wait for yes/no. If no, skip Task 0 and note that 7b commits will be on top of existing dirty tree.

- [ ] **Step 2: Verify tests pass on current tree**

```bash
uv run pytest
```

Expected: 155 passing (per PROGRESS.md).

- [ ] **Step 3: Commit**

```bash
git add docs/PROGRESS.md seeds/schema.sql seeds/seed_stock.py \
        src/ksp_planner/cli.py src/ksp_planner/db.py \
        src/ksp_planner/dv_map.py src/ksp_planner/formatting.py \
        tests/test_cli.py tests/test_dv_map.py
git commit -m "$(cat <<'EOF'
feat(7a): seed Δv chart, add dv_map + plan_trip + ksp dv command

Phase 7a of the Δv planner: dv_nodes/dv_edges tables, seeded from the
community chart via DV_NODES + DV_ADJACENCIES in seeds/seed_stock.py.
New dv_map.py (pure path-finding, no DB import), DB loader
load_dv_graph, CLI ksp dv <from> <to> --margin, and dv_trip_panel
formatter. 28 new tests; Hohmann cross-check catches chart typos.

Acceptance: ksp dv kerbin_surface mun_surface = 5,150 m/s raw (chart ✅).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 4: Verify clean tree**

```bash
git status
```

Expected: `nothing to commit, working tree clean`.

---

## Task 1: `resolve_stop` — action → node-slug resolver

**Files:**
- Modify: `src/ksp_planner/dv_map.py` (add `ACTION_SUFFIXES` constant and `resolve_stop` function)
- Modify: `tests/test_dv_map.py` (add new body-style fixture + 6 resolver tests)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_dv_map.py` (after the existing `plan_trip` tests, before the "seed integration" section header):

```python
# ---------- resolve_stop ----------


@pytest.fixture
def body_tree() -> DvGraph:
    """Minimal body-style fixture: Minmus (full chain) + Kerbol (only _orbit)."""
    nodes = [
        DvNode(slug="kerbol_orbit", parent_slug=None, body_slug="kerbol", state="sun_orbit"),
        DvNode(slug="minmus_transfer", parent_slug="kerbol_orbit", body_slug="minmus", state="transfer"),
        DvNode(slug="minmus_low_orbit", parent_slug="minmus_transfer", body_slug="minmus", state="low_orbit"),
        DvNode(slug="minmus_surface", parent_slug="minmus_low_orbit", body_slug="minmus", state="surface"),
    ]
    return DvGraph(nodes=nodes, edges=[])


def test_resolve_stop_land(body_tree):
    from ksp_planner.dv_map import resolve_stop

    stop = resolve_stop(body_tree, "minmus", "land")
    assert stop == Stop(slug="minmus_surface", action="land")


def test_resolve_stop_orbit(body_tree):
    from ksp_planner.dv_map import resolve_stop

    stop = resolve_stop(body_tree, "minmus", "orbit")
    assert stop == Stop(slug="minmus_low_orbit", action="orbit")


def test_resolve_stop_flyby(body_tree):
    from ksp_planner.dv_map import resolve_stop

    stop = resolve_stop(body_tree, "minmus", "flyby")
    assert stop == Stop(slug="minmus_transfer", action="flyby")


def test_resolve_stop_unknown_action_raises(body_tree):
    from ksp_planner.dv_map import resolve_stop

    with pytest.raises(KeyError, match="unknown action"):
        resolve_stop(body_tree, "minmus", "fly")


def test_resolve_stop_body_missing_state_raises(body_tree):
    """Kerbol has only kerbol_orbit — any action that would need kerbol_surface/_low_orbit/_transfer errors."""
    from ksp_planner.dv_map import resolve_stop

    with pytest.raises(KeyError, match="kerbol_surface"):
        resolve_stop(body_tree, "kerbol", "land")


def test_resolve_stop_unknown_body_raises(body_tree):
    from ksp_planner.dv_map import resolve_stop

    with pytest.raises(KeyError, match="gorgon"):
        resolve_stop(body_tree, "gorgon", "orbit")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_dv_map.py -v -k resolve_stop
```

Expected: 6 failures, all `ImportError: cannot import name 'resolve_stop' from 'ksp_planner.dv_map'`.

- [ ] **Step 3: Implement `resolve_stop` in `dv_map.py`**

In `src/ksp_planner/dv_map.py`, add after the `TripPlan` dataclass (around line 42, before `class DvGraph`):

```python
ACTION_SUFFIXES = {
    "land": "_surface",
    "orbit": "_low_orbit",
    "flyby": "_transfer",
}
```

And add a new top-level function after the existing `plan_trip` (bottom of file):

```python
def resolve_stop(graph: DvGraph, body_slug: str, action: str) -> Stop:
    """Map (body, action) → Stop with the corresponding tree-node slug.

    Raises KeyError if `action` is not one of {land, orbit, flyby}, or if the
    body has no node for that state (e.g. kerbol has only kerbol_orbit, so
    kerbol:land has no corresponding node).
    """
    if action not in ACTION_SUFFIXES:
        raise KeyError(f"unknown action: {action!r} — use land, orbit, or flyby")
    node_slug = f"{body_slug}{ACTION_SUFFIXES[action]}"
    graph.node(node_slug)  # surfaces KeyError on unknown body or missing state
    return Stop(slug=node_slug, action=action)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_dv_map.py -v -k resolve_stop
```

Expected: 6 passing.

- [ ] **Step 5: Run full suite to verify nothing else broke**

```bash
uv run pytest
```

Expected: 161 passing (155 + 6).

- [ ] **Step 6: Commit**

```bash
git add src/ksp_planner/dv_map.py tests/test_dv_map.py
git commit -m "$(cat <<'EOF'
feat(7b): add resolve_stop for body+action → node slug mapping

Maps land/orbit/flyby to _surface/_low_orbit/_transfer respectively.
Rejects unknown actions and bodies that lack the requested state (e.g.
kerbol:land has no kerbol_surface node). Pure function, no DB import.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: `TripPlan.stops` field — thread stops through `plan_trip`

**Files:**
- Modify: `src/ksp_planner/dv_map.py` (add `stops` field to `TripPlan`; thread through `plan_trip`)
- Modify: `tests/test_dv_map.py` (extend one plan_trip test to assert `stops` is populated)

- [ ] **Step 1: Write the failing test**

Replace the existing `test_plan_trip_two_stops_default_margin` in `tests/test_dv_map.py` (currently ~line 115) with this extended version that also asserts `stops`:

```python
def test_plan_trip_two_stops_default_margin(tree):
    stops_in = [Stop("c"), Stop("f")]
    plan = plan_trip(tree, stops_in)
    assert plan.total_raw == 27
    assert plan.margin_pct == 5.0
    assert plan.total_planned == pytest.approx(27 * 1.05)
    assert len(plan.legs) == 1
    assert len(plan.legs[0]) == 3
    assert plan.stops == stops_in
```

Also replace `test_plan_trip_three_stops` to assert `stops`:

```python
def test_plan_trip_three_stops(tree):
    # c -> f -> e
    # leg1: c -> f = 27 (c->a 1, a->d 12, d->f 14)
    # leg2: f -> e (LCA root): f->d 4, d->a 2, a->root 10, root->b 200, b->e 13 = 229
    stops_in = [Stop("c"), Stop("f"), Stop("e")]
    plan = plan_trip(tree, stops_in)
    assert plan.total_raw == 27 + 229
    assert len(plan.legs) == 2
    assert plan.stops == stops_in
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_dv_map.py::test_plan_trip_two_stops_default_margin tests/test_dv_map.py::test_plan_trip_three_stops -v
```

Expected: 2 failures, `AttributeError: 'TripPlan' object has no attribute 'stops'`.

- [ ] **Step 3: Add `stops` to `TripPlan` and thread through `plan_trip`**

In `src/ksp_planner/dv_map.py`, update the `TripPlan` dataclass (around line 36):

```python
@dataclass(frozen=True)
class TripPlan:
    stops: list[Stop]
    legs: list[list[Edge]]
    total_raw: float
    margin_pct: float
    total_planned: float
```

Update `plan_trip` return (around line 121) to pass `stops=stops`:

```python
    return TripPlan(
        stops=stops,
        legs=legs,
        total_raw=raw,
        margin_pct=margin_pct,
        total_planned=raw * (1 + margin_pct / 100),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_dv_map.py -v
```

Expected: all `test_dv_map.py` tests pass (21 original + 6 resolver + 0 new = 27 — the two modifications are in-place).

- [ ] **Step 5: Run full suite**

```bash
uv run pytest
```

Expected: 161 passing (no regressions — TripPlan is only constructed in `plan_trip`, and the renderer doesn't read `stops` yet).

- [ ] **Step 6: Commit**

```bash
git add src/ksp_planner/dv_map.py tests/test_dv_map.py
git commit -m "$(cat <<'EOF'
refactor(7b): add stops field to TripPlan

Threads the Stop list through plan_trip so the renderer can annotate
per-stop actions between legs. No behavior change to path-finding or
totals; purely additive.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: CLI `--via body[:action]` parsing + resolver wiring

**Files:**
- Modify: `src/ksp_planner/cli.py` (extend `dv` command: `--via` option + parse helper + resolver calls)
- Modify: `tests/test_cli.py` (8 new tests)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cli.py` (after the existing `test_dv_*` tests, around line 390):

```python
# ---------- 7b: --via + actions ----------


def test_dv_via_orbit_totals_match_chart(seed_db):
    """Acceptance: kerbin_surface → minmus(orbit) → mun_surface ≈ 7,330 m/s raw."""
    r = _invoke(seed_db, "dv", "kerbin_surface", "mun_surface", "--via", "minmus:orbit")
    assert r.exit_code == 0, r.stdout
    # Rich panel prints the raw total with thousands separator
    assert "7,330 m/s" in r.stdout


def test_dv_via_default_action_is_orbit(seed_db):
    """--via minmus (no :action) should behave like --via minmus:orbit."""
    r_default = _invoke(seed_db, "dv", "kerbin_surface", "mun_surface", "--via", "minmus")
    r_explicit = _invoke(seed_db, "dv", "kerbin_surface", "mun_surface", "--via", "minmus:orbit")
    assert r_default.exit_code == 0
    assert r_explicit.exit_code == 0
    # Both should print the same raw total
    assert "7,330 m/s" in r_default.stdout
    assert "7,330 m/s" in r_explicit.stdout


def test_dv_via_land_routes_through_surface(seed_db):
    r = _invoke(seed_db, "dv", "kerbin_surface", "mun_surface", "--via", "minmus:land")
    assert r.exit_code == 0, r.stdout
    # Landing on Minmus means the intermediate stop is minmus_surface
    assert "minmus_surface" in r.stdout


def test_dv_via_flyby_routes_through_transfer(seed_db):
    r = _invoke(seed_db, "dv", "kerbin_surface", "mun_surface", "--via", "minmus:flyby")
    assert r.exit_code == 0, r.stdout
    # Flyby resolves to minmus_transfer
    assert "minmus_transfer" in r.stdout


def test_dv_multiple_via_preserves_order(seed_db):
    """--via mun:flyby --via minmus:land: legs should traverse mun_transfer first, then minmus_surface."""
    r = _invoke(seed_db, "dv", "kerbin_surface", "kerbin_surface",
                "--via", "mun:flyby", "--via", "minmus:land")
    assert r.exit_code == 0, r.stdout
    # Both intermediate slugs should appear; mun before minmus in the printed legs
    out = r.stdout
    assert out.index("mun_transfer") < out.index("minmus_surface")


def test_dv_via_unknown_action_errors(seed_db):
    r = _invoke(seed_db, "dv", "kerbin_surface", "mun_surface", "--via", "minmus:fly")
    assert r.exit_code == 1
    assert "unknown action" in r.stdout


def test_dv_via_unknown_body_errors(seed_db):
    r = _invoke(seed_db, "dv", "kerbin_surface", "mun_surface", "--via", "gorgon:orbit")
    assert r.exit_code == 1
    # surfaces as KeyError from graph.node() on gorgon_low_orbit
    assert "gorgon_low_orbit" in r.stdout


def test_dv_via_malformed_syntax_errors(seed_db):
    """--via a:b:c is invalid (too many colons), as is --via :orbit (empty body)."""
    r_extra = _invoke(seed_db, "dv", "kerbin_surface", "mun_surface", "--via", "a:b:c")
    assert r_extra.exit_code == 1
    assert "expected body[:action]" in r_extra.stdout

    r_empty = _invoke(seed_db, "dv", "kerbin_surface", "mun_surface", "--via", ":orbit")
    assert r_empty.exit_code == 1
    assert "expected body[:action]" in r_empty.stdout
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_cli.py -v -k "dv_via or dv_multiple_via"
```

Expected: 8 failures — `--via` option not recognized by Typer (`No such option: --via`).

- [ ] **Step 3: Extend the `dv` command in `cli.py`**

In `src/ksp_planner/cli.py`, update the import at line 14 to include `resolve_stop`:

```python
from ksp_planner.dv_map import Stop, plan_trip, resolve_stop
```

Add a parse helper above the `dv` command (just above `@app.command()` at line 298):

```python
def _parse_via(raw: str) -> tuple[str, str]:
    """Parse a --via value of the form 'body' or 'body:action'. Returns (body, action)."""
    parts = raw.split(":")
    if len(parts) == 1:
        body, action = parts[0], "orbit"
    elif len(parts) == 2:
        body, action = parts
    else:
        raise ValueError(f"expected body[:action], got {raw!r}")
    if not body:
        raise ValueError(f"expected body[:action], got {raw!r}")
    return body, action
```

Replace the `dv` command body (currently lines 298-316) with:

```python
@app.command()
def dv(
    from_slug: Annotated[str, typer.Argument(help="Departure node slug, e.g. kerbin_surface")],
    to_slug: Annotated[str, typer.Argument(help="Arrival node slug, e.g. mun_surface")],
    via: Annotated[
        list[str] | None,
        typer.Option(
            "--via",
            help="Intermediate stop as body[:action]. Repeatable. action ∈ land|orbit|flyby, default orbit.",
        ),
    ] = None,
    margin: Annotated[
        float,
        typer.Option("--margin", "-m", help="Margin percentage on the raw total"),
    ] = 5.0,
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
        trip = plan_trip(graph, stops, margin_pct=margin)
    except KeyError as e:
        console.print(f"[red]{e}[/]")
        raise typer.Exit(1) from None
    console.print(dv_trip_panel(trip, from_slug.lower(), to_slug.lower()))
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_cli.py -v -k "dv_via or dv_multiple_via"
```

Expected: 8 passing. If `test_dv_via_orbit_totals_match_chart` fails with a number off by more than 50 from 7,330, stop and investigate — the acceptance number may need updating (see spec §Open questions).

- [ ] **Step 5: Run full suite**

```bash
uv run pytest
```

Expected: 169 passing (161 + 8).

- [ ] **Step 6: Commit**

```bash
git add src/ksp_planner/cli.py tests/test_cli.py
git commit -m "$(cat <<'EOF'
feat(7b): add --via body[:action] to ksp dv command

Repeatable --via option, colon-paired body+action syntax. Default
action is 'orbit' when omitted. Resolver errors (unknown action/body,
malformed syntax) exit 1 with a red message. Preserves 7a behavior
when no --via is given.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Renderer — per-stop annotations in `dv_trip_panel`

**Files:**
- Modify: `src/ksp_planner/formatting.py` (walk intermediate stops and emit annotation rows)
- Modify: `tests/test_cli.py` (1 new test asserting the annotation appears)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cli.py` (just below the tests from Task 3):

```python
def test_dv_via_annotation_shows_action_in_output(seed_db):
    """A --via stop should print its action as an annotation between the two legs."""
    r = _invoke(seed_db, "dv", "kerbin_surface", "mun_surface", "--via", "minmus:orbit")
    assert r.exit_code == 0, r.stdout
    # Annotation row — "stop: orbit" appears with the resolved slug
    assert "stop: orbit" in r.stdout
    assert "minmus_low_orbit" in r.stdout
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_cli.py::test_dv_via_annotation_shows_action_in_output -v
```

Expected: FAIL — "`stop: orbit` not in stdout" (the string isn't emitted yet).

- [ ] **Step 3: Update `dv_trip_panel` to emit stop annotations**

In `src/ksp_planner/formatting.py`, replace the `dv_trip_panel` function (around lines 168-199) with:

```python
def dv_trip_panel(trip, from_slug: str, to_slug: str) -> Panel:
    """Render a `TripPlan` as a per-leg table + raw and margin-padded totals.

    When the trip has intermediate stops, a `stop: <action> (<slug>)` row is
    inserted between legs for each intermediate stop.
    """
    legs_table = Table(box=box.SIMPLE_HEAVY, show_header=True, header_style="dim")
    legs_table.add_column("From")
    legs_table.add_column("→")
    legs_table.add_column("To")
    legs_table.add_column("Δv", justify="right")
    legs_table.add_column("aero", justify="center")

    intermediate_stops = trip.stops[1:-1]

    for leg_idx, leg in enumerate(trip.legs):
        for edge in leg:
            legs_table.add_row(
                edge.from_slug,
                "→",
                edge.to_slug,
                f"{edge.dv_m_s:>7,.0f} m/s",
                "✓" if edge.can_aerobrake else "",
            )
        # Emit stop annotation after each leg except the last
        if leg_idx < len(intermediate_stops):
            stop = intermediate_stops[leg_idx]
            legs_table.add_row(
                "",
                "",
                f"[dim italic]stop: {stop.action} ({stop.slug})[/]",
                "",
                "",
            )

    totals = Table.grid(padding=(0, 2))
    totals.add_column(style="dim")
    totals.add_column(justify="right")
    totals.add_row("Raw total", f"[bold]{trip.total_raw:,.0f} m/s[/]")
    totals.add_row(
        f"Planned (+{trip.margin_pct:g}% margin)",
        f"[bold green]{trip.total_planned:,.0f} m/s[/]",
    )

    # Title includes the via chain when present
    if intermediate_stops:
        via_chain = " → ".join(s.slug for s in intermediate_stops)
        title = f"[bold]Δv trip — {from_slug} → {via_chain} → {to_slug}[/]"
    else:
        title = f"[bold]Δv trip — {from_slug} → {to_slug}[/]"

    return Panel(
        Group(legs_table, Text(""), totals),
        title=title,
        box=box.ROUNDED,
    )
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_cli.py::test_dv_via_annotation_shows_action_in_output -v
```

Expected: PASS.

- [ ] **Step 5: Run full suite**

```bash
uv run pytest
```

Expected: 170 passing (169 + 1). If any existing `test_dv_*` test fails because its assertion string is now wrapped in Rich markup, adjust the test's substring assertion to use a markup-agnostic fragment.

- [ ] **Step 6: Visual spot-check**

Run a real invocation to eyeball the output shape:

```bash
uv run ksp dv kerbin_surface mun_surface --via minmus:orbit
```

Expected output (exact formatting may vary slightly):

```
╭─ Δv trip — kerbin_surface → minmus_low_orbit → mun_surface ─╮
│  From               →   To                   Δv   aero      │
│  ─────────────────────────────────────────────────────────  │
│  kerbin_surface     →   kerbin_low_orbit   3,400 m/s        │
│  kerbin_low_orbit   →   minmus_transfer      930 m/s        │
│  minmus_transfer    →   minmus_low_orbit     160 m/s        │
│                         stop: orbit (minmus_low_orbit)      │
│  minmus_low_orbit   →   minmus_transfer      160 m/s        │
│  minmus_transfer    →   kerbin_low_orbit     930 m/s        │
│  kerbin_low_orbit   →   mun_transfer         860 m/s        │
│  mun_transfer       →   mun_low_orbit        310 m/s        │
│  mun_low_orbit      →   mun_surface          580 m/s        │
│                                                             │
│  Raw total                              7,330 m/s           │
│  Planned (+5% margin)                   7,697 m/s           │
╰─────────────────────────────────────────────────────────────╯
```

If the annotation row looks wrong (e.g. the `stop:` text runs into the Δv column awkwardly), fall back to `legs_table.add_row(f"[dim]— stop: {stop.action} ({stop.slug}) —[/]", "", "", "", "")` (full-row italic marker in the leftmost column).

- [ ] **Step 7: Commit**

```bash
git add src/ksp_planner/formatting.py tests/test_cli.py
git commit -m "$(cat <<'EOF'
feat(7b): render per-stop action annotations in dv_trip_panel

After each intermediate leg, emit a dim italic row showing the stop's
action + resolved slug. Title now includes the via chain when present.
Two-point trips (no --via) render identically to 7a.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Acceptance probe — additional chart sanity checks

> Task 3 already pinned the 7b acceptance gate (`kerbin_surface → minmus(orbit) → mun_surface == 7,330 raw`). This task adds two additional parametric sanity checks and the "orbit = low_orbit" alias behavior across several bodies, to guard against resolver bugs that happen to pass the single acceptance test.

**Files:**
- Modify: `tests/test_dv_map.py` (parametric integration tests against the real seed)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_dv_map.py` at the very bottom:

```python
# ---------- 7b: integration — resolver against real seed ----------


@pytest.mark.parametrize(
    ("body_slug", "action", "expected_node"),
    [
        ("minmus", "land",  "minmus_surface"),
        ("minmus", "orbit", "minmus_low_orbit"),
        ("minmus", "flyby", "minmus_transfer"),
        ("duna",   "land",  "duna_surface"),
        ("duna",   "orbit", "duna_low_orbit"),
        ("duna",   "flyby", "duna_transfer"),
        ("jool",   "orbit", "jool_low_orbit"),
        ("mun",    "flyby", "mun_transfer"),
    ],
)
def test_resolve_stop_against_real_seed(db, body_slug, action, expected_node):
    from ksp_planner.db import load_dv_graph
    from ksp_planner.dv_map import resolve_stop

    g = load_dv_graph(db)
    stop = resolve_stop(g, body_slug, action)
    assert stop.slug == expected_node
    assert stop.action == action


def test_kerbin_via_minmus_orbit_to_mun_surface_acceptance(db):
    """7b acceptance gate: totals match the chart walk within ±50 m/s of 7,330."""
    from ksp_planner.db import load_dv_graph
    from ksp_planner.dv_map import plan_trip, resolve_stop

    g = load_dv_graph(db)
    stops = [
        Stop("kerbin_surface"),
        resolve_stop(g, "minmus", "orbit"),
        Stop("mun_surface"),
    ]
    plan = plan_trip(g, stops, margin_pct=5.0)
    assert plan.total_raw == pytest.approx(7330, abs=50)
    assert plan.total_planned == pytest.approx(7330 * 1.05, rel=0.01)
    assert len(plan.legs) == 2
    assert plan.stops[1].slug == "minmus_low_orbit"
    assert plan.stops[1].action == "orbit"
```

- [ ] **Step 2: Run tests to verify they pass immediately**

These tests should pass because `resolve_stop` and `plan_trip` are already done. This task adds the safety net, not new behavior.

```bash
uv run pytest tests/test_dv_map.py -v -k "resolve_stop_against_real_seed or test_kerbin_via_minmus"
```

Expected: 9 passing (8 parametric + 1 acceptance).

- [ ] **Step 3: Run full suite**

```bash
uv run pytest
```

Expected: 179 passing (170 + 9).

- [ ] **Step 4: Run lint**

```bash
uv run ruff check
```

Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add tests/test_dv_map.py
git commit -m "$(cat <<'EOF'
test(7b): parametric resolver checks + integration acceptance

Parametrised (body, action) → node mapping across planets and moons
catches resolver regressions a single acceptance test would miss.
Adds the plan-level acceptance test (raw == 7,330 ±50, stops[1]
resolves to minmus_low_orbit).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Phase close-out — update PROGRESS.md with 7b log + 7c resume notes

**Files:**
- Modify: `docs/PROGRESS.md` (update header counts, flip 7b row to done, add 7b completion log, add 7c resume notes)

- [ ] **Step 1: Update header line**

At the top of `docs/PROGRESS.md`, update the "Last updated" and "Tests" line:

```markdown
**Last updated:** 2026-04-21
**Tests:** 179 passing · **Lint:** clean · **Coverage:** 98% overall, 100% on `orbital.py` and `db.py`.
```

(Adjust numbers to what the final `uv run pytest` actually shows if different.)

- [ ] **Step 2: Flip the 7b row in the Phase ladder**

In the sub-phase table (around line 37), change the 7b row to:

```markdown
| 7b | Intermediate stops with per-stop `action` (`land` / `orbit` / `flyby`); `--via body[:action]` repeatable on CLI | ✅ done | `kerbin_surface → minmus (orbit) → mun_surface` = 7,330 m/s raw / 7,697 @ 5% |
```

And update the Phase 7 row (around line 21):

```markdown
| 7 | Δv planner (tree model, margin, stops) | 🟡 in progress (7a ✅; 7b ✅; 7c next) | Design locked in [features/dv-planner.md](features/dv-planner.md); sub-phase ladder below |
```

- [ ] **Step 3: Add a "Phase 7b completion log" section**

Insert after the existing "Phase 7a completion log" section, before the "7b resume point" section:

```markdown
### Phase 7b completion log

Shipped with TDD throughout. 24 new tests; 155 → 179 total. Lint clean.

- **Action resolver.** `src/ksp_planner/dv_map.py` gained `ACTION_SUFFIXES = {land→_surface, orbit→_low_orbit, flyby→_transfer}` and `resolve_stop(graph, body, action) → Stop`. Pure function, no DB import. Flyby resolves to `_transfer` for all bodies (revised from the feature doc's `_capture` mapping, which was contradictory — `_capture` is the state *after* the capture burn).
- **TripPlan.stops.** Added `stops: list[Stop]` field to `TripPlan`; `plan_trip` threads the input list through. Existing tests updated to assert the field round-trips.
- **CLI.** `dv` command gained `--via body[:action]` (repeatable). `_parse_via` helper splits on `:`, defaults action to `orbit` when omitted. Resolver errors (unknown action/body, malformed syntax) exit 1 with red messages — same pattern as existing `dv_budget` error paths.
- **Renderer.** `dv_trip_panel` walks `trip.stops[1:-1]` and emits a dim-italic annotation row between legs at each intermediate stop. Title includes the via chain when present. Two-point trips render unchanged.
- **Acceptance.** `kerbin_surface → minmus (orbit) → mun_surface` = 7,330 raw / 7,697 @ 5% (traced by hand through the seed: leg1 4,490 + leg2 2,840). Also verified Minmus land/flyby variants and the `--via minmus` default-action alias.

**Spec reference:** [docs/superpowers/specs/2026-04-21-dv-planner-7b-design.md](superpowers/specs/2026-04-21-dv-planner-7b-design.md).
```

- [ ] **Step 4: Replace the old "7b resume point" with a "7c resume point"**

Replace the existing "### 7b resume point — Intermediate stops" section (around lines 72-91) with:

```markdown
### 7c resume point — Return trip + aerobraking

Spec: [features/dv-planner.md §7c](features/dv-planner.md#7c--return-trip--aerobraking). `--return` flag doubles + reverses the itinerary; `can_aerobrake` edges zero out the descent leg when returning to an atmosphere body (Kerbin, Eve, Duna, Jool, Laythe). Output shows both "no aerobrake" and "with aerobrake" totals.

**First concrete next step** for a fresh session:

1. RED: extend `tests/test_dv_map.py` with a `plan_trip(..., return_trip=True, aerobrake=True)` test using a hand-built tree where one edge has `can_aerobrake=True`.
2. Decide whether `--return` lives on `plan_trip` (new kwarg) or a new `plan_round_trip` helper. The feature doc's API surface suggests the latter.
3. `can_aerobrake` is already seeded on `dv_edges` (check `test_eve_capture_claims_aerobrake_credit` for how it surfaces). Just need to know *when* to credit it — on return legs landing at an atmosphere body.
4. CLI: `--return` boolean flag, `--no-aerobrake` to disable the credit.
5. Acceptance: `ksp dv kerbin_surface duna_surface --return` shows ~3,400 m/s savings from Kerbin aerobrake on the return leg (per feature doc §7c).
6. Stop & doc-update before 7d.

Files likely to change: `src/ksp_planner/dv_map.py`, `src/ksp_planner/cli.py`, `src/ksp_planner/formatting.py` (dual-total rendering), plus tests.
```

- [ ] **Step 5: Verify the file renders correctly**

Skim the file — section ordering should be: Phase table → Phase 6 log → Phase 7 breakdown → Phase 7a log → **Phase 7b log (new)** → 7c resume point (new) → Repo map → Key decisions → …

- [ ] **Step 6: Commit**

```bash
git add docs/PROGRESS.md
git commit -m "$(cat <<'EOF'
docs(7b): complete phase, add 7c resume notes

Phase 7b shipped: resolve_stop, TripPlan.stops, --via body[:action]
CLI, and per-stop render annotations. 24 new tests (155 → 179).
Acceptance probe kerbin_surface → minmus(orbit) → mun_surface =
7,330 m/s raw / 7,697 @ 5%. 7c resume notes document the return-trip
+ aerobraking spec for the next session.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 7: Announce reset point**

Tell the user: "Phase 7b shipped. `PROGRESS.md` has the completion log + 7c resume notes. This is a clean stop point — ready for context reset."

---

## Non-goals (out of this plan)

- Return trips (`--return`) — 7c
- Aerobraking credit — 7c
- Stage-aware budget check — 7d
- Direct moon-to-moon edges / Dijkstra — 7e
- `high_orbit` action — deferred indefinitely
- `--via` accepting raw node slugs — body-only for now

## Acceptance summary

After Task 6, the following should all be true:

- `uv run pytest` → 179 passing (exact count may shift ±2 if ruff/Typer version pins change).
- `uv run ruff check` → clean.
- `uv run ksp dv kerbin_surface mun_surface` → 5,150 m/s raw (unchanged from 7a).
- `uv run ksp dv kerbin_surface mun_surface --via minmus:orbit` → 7,330 m/s raw / 7,697 @ 5%.
- `uv run ksp dv kerbin_surface mun_surface --via minmus` → identical to `--via minmus:orbit`.
- `uv run ksp dv kerbin_surface mun_surface --via minmus:land` → routes through `minmus_surface`.
- Malformed `--via` values exit 1 with a red message.
- `docs/PROGRESS.md` 7b row = ✅; 7c resume notes present.
