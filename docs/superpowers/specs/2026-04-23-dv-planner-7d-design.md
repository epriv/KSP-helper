# Δv Planner — Phase 7d Design

**Date:** 2026-04-23
**Status:** approved, ready for implementation plan
**Scope:** Round-trip itinerary support + revised aerobrake credit
**Follows:** [7c](2026-04-22-dv-planner-7c-design.md)
**Precedes:** 7e (graph upgrade: Dijkstra + inter-moon shortcuts)

## Goal

Ship `--return` as the canonical way to build round-trip itineraries over the Δv chart, and fix the Kerbin-descent aerobrake estimate that 7c's 20% residual made too pessimistic. The `--return` shape is the foundation for future multi-stop round trips (`A→B→C→A`).

## Non-goals

- **Stage-aware budget check.** The original 7d scope (Tsiolkovsky coverage over a staged ship) is dropped — current per-edge output is already sufficient for hand-building stages in KSP.
- **Per-edge aerobrake override.** Schema-level per-edge override (`aerobrake_dv_m_s REAL NULL`) is deferred. Global residual change is simpler and matches community-chart convention.
- **Graph upgrade / Dijkstra.** 7e concern.
- **Separate outbound/return total rendering.** Single grand total is sufficient for fuel planning; the turnaround stop is visible as an annotation row.

## Design decisions

### 1. Residual drops to 0%

`AEROBRAKE_RESIDUAL_PCT: 20.0 → 0.0` in `src/ksp_planner/dv_map.py`.

**Why 0.** Community Δv charts treat aerobrakable edges as ~0 on descent. The 20% was a 7c safety buffer; the 5% trip margin already covers "imperfect passes and correction burns." Zeroing matches convention and removes the special-case opacity.

**Consequence.** 7c acceptance numbers shift. The constant stays as a module-level lever so a future tune (say 5%) is still a one-line change.

### 2. Round-trip = doubled itinerary

New `plan_round_trip(graph, stops, margin_pct=5.0, aerobrake=True) -> TripPlan` in `dv_map.py`.

```python
def plan_round_trip(graph, stops, margin_pct=5.0, aerobrake=True):
    if len(stops) < 2:
        raise ValueError("round trip requires at least two stops")
    doubled = list(stops) + list(reversed(stops[:-1]))
    return plan_trip(graph, doubled, margin_pct=margin_pct, aerobrake=aerobrake)
```

- `[A, B]` → legs for `A → B → A`.
- `[A, B, C]` → legs for `A → B → C → B → A`.
- Composes cleanly with `--via`; no extra flag needed for multi-stop round trips.
- Returns the same `TripPlan` dataclass — no schema or renderer changes required.

### 3. CLI `--return`

`src/ksp_planner/cli.py` — add a `--return` boolean flag to `ksp dv`.

```
ksp dv FROM TO [--via body[:action] ...] [--margin PCT] [--aerobrake/--no-aerobrake] [--return]
```

When `--return` is set, the accumulated `stops` list is passed to `plan_round_trip` instead of `plan_trip`. All existing flags behave as-is.

**Typer note:** `return` is a Python keyword, so the parameter name is `return_` with explicit `--return` flag syntax.

### 4. Renderer — no changes

`dv_trip_panel` already annotates intermediate stops via `trip.stops[1:-1]`. On a round-trip `[A, B, A]`, the turnaround is at index 1 and renders as a normal `— stop: <action> (<slug>) —` row. On `[A, B, C, B, A]`, three annotation rows appear at B, C, B. No special "return" marker needed — the existing mechanism is sufficient.

## Acceptance

**Gate:** `ksp dv kerbin_surface mun_surface --return` with aerobrake produces the canonical Mun round-trip value within ±50 m/s of hand-walked totals.

Hand-walked:
- Outbound K_s → M_s: 3,400 + 860 + 310 + 580 = **5,150** (ballistic, no aerobrake credits on this path).
- Return M_s → K_s: 580 + 310 + 860 + 3,400 = **5,150** ballistic. Kerbin LO→surface is aerobrakable — drops to 0 under the new residual. Return aerobraked: 580 + 310 + 860 + 0 = **1,750**.
- Round-trip raw: **10,300 m/s**.
- Round-trip aerobraked: **6,900 m/s**.
- Planned @ 5%: **7,245 m/s**.

Sanity probes:
- `kerbin_surface → duna_surface --return`: must show substantial aerobrake savings on both outbound (Duna capture + descent) and return (Kerbin descent).
- `kerbin_surface → minmus_surface --via mun:orbit --return`: multi-stop round trip, verifies `plan_round_trip` composes with `--via`.

## Test fallout

Existing 7c tests that pin specific aerobraked totals will shift when residual → 0:

- `test_dv_map.py` — 7c acceptance pins (Duna capture 360 × 0.2 = 72 → 0; Duna LO→surface similar).
- `test_cli.py` — `ksp dv kerbin_surface duna_surface` output assertions.
- `test_dv_map.py` 7c Eve aerobrake check.

Strategy: recompute each pinned value against the seed, update in the same commit as the constant change so no intermediate state has broken tests.

## Files touched

| File | Change |
|------|--------|
| `src/ksp_planner/dv_map.py` | `AEROBRAKE_RESIDUAL_PCT = 0.0`; add `plan_round_trip` |
| `src/ksp_planner/cli.py` | Add `--return` flag to `dv` command; dispatch to `plan_round_trip` |
| `tests/test_dv_map.py` | New `plan_round_trip` tests (2-stop + 3-stop); update 7c aerobraked pins |
| `tests/test_cli.py` | New `--return` CLI test; update any shifted aerobrake pins |

## Build order (TDD)

1. **RED:** residual-change tests. Update 7c pinned assertions to new expected values; assert they currently fail. (Intentional failure — confirms the pins actually test what we think.)
2. **GREEN:** flip `AEROBRAKE_RESIDUAL_PCT = 0.0`. Full suite green.
3. **RED:** `test_plan_round_trip_mun` — 2-stop K_s→M_s→K_s, assert leg count and aerobraked total = 6,900 ± 1.
4. **GREEN:** implement `plan_round_trip`.
5. **RED:** `test_plan_round_trip_multi` — 3-stop, verify doubled stops and leg count = 4.
6. **GREEN:** already handled by step 4 — no-op or minor fix.
7. **RED:** `test_cli_dv_return_flag` — `ksp dv K_s M_s --return` shows round-trip total.
8. **GREEN:** add `--return` flag and dispatch.
9. **RED:** `test_cli_dv_return_with_via` — `ksp dv K_s Min_s --via mun:orbit --return`.
10. **GREEN:** verify (`plan_round_trip` already composes).
11. Phase-close ritual: `make test` + `make lint`, `/simplify`, PROGRESS.md update, commit, reset.

## Follow-ups / deferred

- **Per-edge aerobrake override.** If 0% global ever feels too optimistic for a specific edge, revisit the schema-column approach from this doc's Options Y.
- **Configurable residual CLI flag** (`--aerobrake-residual`). Not needed yet.
- **Known 7c limitations (double-credit on pre-baked capture edges, etc.)** unchanged by 7d — still 7e territory.
