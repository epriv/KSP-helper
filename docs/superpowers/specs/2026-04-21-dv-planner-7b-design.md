# Phase 7b — Intermediate Stops (Δv Planner)

**Status:** spec approved 2026-04-21 · **Supersedes:** [features/dv-planner.md §7b](../../features/dv-planner.md#7b--intermediate-stops) where they differ

## Goal

Extend the Δv planner from two-point totals to N-stop itineraries, with each intermediate stop tagged by an `action` that resolves to a concrete tree node. CLI gets a repeatable `--via body[:action]` option. Return trips, aerobraking, and stage-aware budget checks remain out of scope (7c / 7d).

**Acceptance gate:** `ksp dv kerbin_surface mun_surface --via minmus:orbit` totals match the chart within ±50 m/s. Expected raw ≈ 7,300 m/s (confirmed against seeded data during RED step, *not* the 6,400 from the original feature doc — that figure was eyeballed and does not account for the bounce through LKO).

## Decisions (locked)

1. **`action` resolves the stop slug.** User supplies body-level `--via` (`minmus`, `mun`, `eve`); action picks the tree node. Alternative — raw node slugs with `action` as render-only metadata — was rejected: it leaks the tree's internal vocabulary into the CLI.
2. **Three actions: `land` / `orbit` / `flyby`.** `high_orbit` is deferred — the canonical chart doesn't tabulate it and adding it requires new `_high_orbit` tree nodes + data source. Revisit later if needed.
3. **Action → suffix mapping:**
   - `land` → `_surface`
   - `orbit` → `_low_orbit`
   - `flyby` → `_transfer`
4. **`flyby → _transfer` for all bodies** (planets and moons). The original feature-doc mapping `flyby → _capture` was self-contradictory: `_capture` is the state *after* the capture burn, which is by definition not a flyby. `_transfer` means "reached the approach trajectory, did not burn to stay" — consistent across body types, no moon edge case.
5. **CLI: `--via body[:action]`, repeatable, colon-paired.** `--via minmus:land`. Missing action defaults to `orbit`: `--via minmus` ≡ `--via minmus:orbit`. Parallel-list alternative (`--via minmus --action orbit`) was rejected — Typer can't enforce positional coupling, and mis-ordering silently produces wrong plans.
6. **From/to stay as raw node slugs.** 7a's `ksp dv kerbin_surface mun_surface` behavior is preserved unchanged. Only intermediate `--via` takes the body+action form.
7. **No schema, seed, or DB changes.** 7a data is sufficient.

## Implementation surface

### `src/ksp_planner/dv_map.py`

```python
ACTION_SUFFIXES = {
    "land":  "_surface",
    "orbit": "_low_orbit",
    "flyby": "_transfer",
}

def resolve_stop(graph: DvGraph, body_slug: str, action: str) -> Stop:
    """(body, action) → Stop(resolved_node_slug, action).

    KeyError on unknown action OR if the body has no node for that state
    (e.g. Kerbol has only kerbol_orbit — any kerbol:* fails at graph.node()).
    """
    if action not in ACTION_SUFFIXES:
        raise KeyError(f"unknown action: {action!r} — use land, orbit, or flyby")
    node_slug = f"{body_slug}{ACTION_SUFFIXES[action]}"
    graph.node(node_slug)  # surfaces KeyError on unknown body or missing state
    return Stop(slug=node_slug, action=action)
```

`TripPlan` gains a `stops` field so the renderer can emit per-stop annotations:

```python
@dataclass(frozen=True)
class TripPlan:
    stops: list[Stop]              # NEW — the stop list passed into plan_trip
    legs: list[list[Edge]]
    total_raw: float
    margin_pct: float
    total_planned: float
```

`plan_trip` body is unchanged except for threading `stops=stops` into the returned `TripPlan`. Existing call sites (6 test assertions) update mechanically.

### `src/ksp_planner/cli.py`

Extend the `dv` command:

```python
@app.command()
def dv(
    from_slug: Annotated[str, typer.Argument(help="Departure node slug, e.g. kerbin_surface")],
    to_slug:   Annotated[str, typer.Argument(help="Arrival node slug, e.g. mun_surface")],
    via: Annotated[
        list[str] | None,
        typer.Option("--via", help="body[:action], repeatable. action ∈ land|orbit|flyby, default orbit"),
    ] = None,
    margin: Annotated[float, typer.Option("--margin", "-m")] = 5.0,
    db: DbOption = Path("ksp.db"),
):
    ...
```

Parse each `--via` value:

- Split on `:` — 1 or 2 parts accepted
- Empty body or 3+ parts → exit 1 with `"expected body[:action], got {value!r}"`
- Missing action → default `"orbit"`
- Action not in {land, orbit, flyby} → exit 1 with the resolver's error

Build stop list: `[Stop(from_slug.lower())] + [resolve_stop(graph, body, action) for each] + [Stop(to_slug.lower())]`. Hand to `plan_trip`. Existing error-handling pattern (KeyError → red print + `typer.Exit(1)`) covers all resolver failures.

### `src/ksp_planner/formatting.py`

`dv_trip_panel` walks `zip(trip.stops[1:-1], trip.legs[:-1])` to emit a one-line annotation row between legs at each intermediate stop:

```
─ stop: orbit (minmus_low_orbit) ─
```

Title updates when vias are present: `Δv trip — kerbin_surface → minmus(orbit) → mun_surface`. Totals block unchanged.

### Tests

**`tests/test_dv_map.py`** — unit + integration:

- `resolve_stop` happy paths: `land` → `_surface`, `orbit` → `_low_orbit`, `flyby` → `_transfer` on hand-built tree
- `resolve_stop` unknown action → KeyError with actionable message
- `resolve_stop` body lacks that state → KeyError (via `graph.node()`)
- `resolve_stop` unknown body → KeyError
- `plan_trip` return value exposes `stops` field correctly
- `plan_trip` with 3+ stops preserves leg count and per-leg structure (existing test covers leg count; extend to assert `stops` round-trip)
- Integration: `resolve_stop(real_graph, "minmus", "flyby")` → `Stop("minmus_transfer", "flyby")`

**`tests/test_cli.py`** — CLI:

- `--via minmus:orbit` single stop, totals correct
- `--via minmus` defaults action to orbit
- `--via mun:flyby --via minmus:land` two stops, ordering preserved in legs and stops output
- Bad action (`--via mun:fly`) → exit 1, red message
- Unknown body (`--via gorgon:orbit`) → exit 1
- Malformed via (`--via ::`, `--via a:b:c`, `--via :orbit`) → exit 1

**Acceptance (the 7b gate):**

- `ksp dv kerbin_surface mun_surface --via minmus:orbit` raw total matches chart ±50 m/s. Confirm expected number during RED — napkin math suggests ≈ 7,300 m/s raw / ≈ 7,670 @ 5%. If the actual is substantially different, investigate before accepting the test.

## Non-goals (out of 7b)

- Return trips (`--return`) — 7c
- Aerobraking credit — 7c
- Stage-aware budget check — 7d
- Direct moon-to-moon edges / Dijkstra — 7e
- Gravity-assist Δv savings — the tree chart does not model these; out of scope for the entire 7 series
- `high_orbit` action — deferred indefinitely unless a concrete use case appears
- `--via` accepting raw node slugs — body-only for now; can extend later without breaking this API

## Files touched

| Path | Change |
|---|---|
| `src/ksp_planner/dv_map.py` | `ACTION_SUFFIXES`, `resolve_stop`, `stops` field on `TripPlan` |
| `src/ksp_planner/cli.py` | `dv` command gains `--via` parse + resolver wiring |
| `src/ksp_planner/formatting.py` | `dv_trip_panel` stop annotations + title |
| `tests/test_dv_map.py` | resolver tests + `stops`-field assertions |
| `tests/test_cli.py` | `--via` CLI coverage |
| `docs/PROGRESS.md` | 7b completion log + 7c resume notes (end-of-phase) |

No schema, seed, or DB loader changes.

## Open questions (to resolve during RED)

1. **Exact chart acceptance number for the Minmus-via-orbit acceptance test.** Pull the actual sum from the seeded data (not the feature doc's eyeballed 6,400) and pin the test to it.
2. **Stop annotation styling.** The proposed `─ stop: orbit (minmus_low_orbit) ─` divider is a first cut. If Rich renders it awkwardly next to the table, fall back to a plain `[dim]stop: orbit[/]` row inside the table.
