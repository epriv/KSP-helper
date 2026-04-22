# Phase 7c — Aerobrake credit (design spec)

**Phase:** 7c of the Δv planner.
**Builds on:** 7a (tree + `plan_trip` + `ksp dv`) and 7b (intermediate `--via` stops).
**Ships:** Aerobraking support on one-way trips.
**Defers:** Round-trip `--return` — moved to a later sub-phase.

## Why this scope

The feature doc's §7c originally bundled return trips with aerobraking. Decoupling them keeps this sub-phase small and unblocks a real-world-useful output: a player planning `kerbin_surface → duna_surface` wants to know what the descent actually costs with a heat shield. Return trips can stack on top later via a separate `plan_round_trip` helper — the API shape for that is already sketched in the feature doc.

## What "aerobrake credit" means here

For each edge in the planned trip:

- If `edge.can_aerobrake` is True **and** the caller asked for aerobrake, the edge's contribution to the total is reduced by a fixed percentage.
- Otherwise the edge contributes its full `dv_m_s`.

The credit is **not** free — aerobraking requires correction burns, safety margin, and a successful atmospheric pass. So aerobrake **leaves a residual** rather than zeroing the leg.

**`AEROBRAKE_RESIDUAL_PCT = 20.0`** — an aerobrake-credited edge contributes 20% of its ballistic `dv_m_s` to the total. This is tuned against well-executed KSP play (heat shield + chutes + small terminal burn). Configurable later via a CLI flag if 20% turns out too aggressive; for 7c it lives as a module constant.

### Which edges are creditable

The seed stores `can_aerobrake=True` **only on the parent→child (descent) direction** of each adjacency (see `seeds/seed_stock.py` comment: *"`aerobrake_on_descent` only annotates the parent→child direction."*). The reverse (ascent) edge is seeded with `can_aerobrake=False`. So "only credit descent" falls out for free — any edge where `can_aerobrake=True` is a descent edge by construction.

### Example: `kerbin_surface → duna_surface`

Outbound edges the path walks (from [seeds/seed_stock.py](../../seeds/seed_stock.py)):

| Edge | Δv | `can_aerobrake` | Credited? | Contribution @ 20% residual |
|---|---:|:---:|:---:|---:|
| kerbin_surface → kerbin_low_orbit | 3,400 | False (ascent) | — | 3,400 |
| kerbin_low_orbit → kerbin_capture | 0 | False | — | 0 |
| kerbin_capture → kerbin_transfer | 0 | False | — | 0 |
| kerbin_transfer → kerbol_orbit | 0 | False | — | 0 |
| kerbol_orbit → duna_transfer | 0 | False | — | 0 |
| duna_transfer → duna_capture | 1,060 | False | — | 1,060 |
| duna_capture → duna_low_orbit | 360 | True | ✓ | 72 |
| duna_low_orbit → duna_surface | 1,450 | True | ✓ | 290 |
| **Totals** | **6,270 (raw)** | | | **4,822 (aerobraked)** |

Savings: 1,448 m/s.

## API surface

### `src/ksp_planner/dv_map.py`

```python
AEROBRAKE_RESIDUAL_PCT = 20.0  # credit = 80% of ballistic dv on can_aerobrake edges

@dataclass(frozen=True)
class TripPlan:
    stops: list[Stop]
    legs: list[list[Edge]]
    total_raw: float                      # unchanged from 7a/7b
    total_aerobraked: float               # NEW
    aerobrake: bool                       # NEW — was aerobrake requested
    margin_pct: float
    total_planned: float                  # raw * (1 + margin) — unchanged
    total_aerobraked_planned: float       # NEW — aerobraked * (1 + margin)

def plan_trip(
    graph: DvGraph,
    stops: list[Stop],
    margin_pct: float = 5.0,
    aerobrake: bool = True,
) -> TripPlan: ...
```

Behavior:

- `aerobrake=True` (default): compute `total_aerobraked` by summing edge contributions where creditable edges use `edge.dv_m_s × (AEROBRAKE_RESIDUAL_PCT / 100)`.
- `aerobrake=False`: `total_aerobraked == total_raw` and `total_aerobraked_planned == total_planned` (no-op mode — caller gets the field but it's identical).
- `total_raw` **never changes** with the aerobrake flag — it's always the ballistic sum. This keeps 7a/7b tests stable and gives the renderer a clean "savings" delta.

### `src/ksp_planner/cli.py`

`ksp dv` gains one flag:

- `--no-aerobrake` (Typer boolean; default is aerobrake on).

Example invocations:

```
ksp dv kerbin_surface duna_surface                  # aerobrake on (default)
ksp dv kerbin_surface duna_surface --no-aerobrake   # full ballistic, no credit
ksp dv kerbin_surface mun_surface --via minmus      # 7b behavior unaffected
```

`--aerobrake-residual` (configurable residual pct) is **deferred** — not in 7c.

### `src/ksp_planner/formatting.py` — `dv_trip_panel`

Two changes:

1. **`aero` column** becomes tri-state:
   - `can_aerobrake=True, aerobrake=True` → `"✓ −80%"`
   - `can_aerobrake=True, aerobrake=False` → `"✓ off"`
   - `can_aerobrake=False` → blank

2. **Totals block** grows a third row when `aerobrake=True`:
   ```
   Raw total              6,270 m/s
   With aerobrake         4,822 m/s   (−1,448)
   Planned (+5% margin)   5,063 m/s
   ```
   When `aerobrake=False`, the panel shows only `Raw total` and `Planned` — matches 7b layout.

   The "Planned" row is the **aerobrake-adjusted** total + margin when aerobrake is on (i.e., `total_aerobraked_planned`). This is the number the player should fuel for. Ballistic `total_planned` isn't rendered — it's available on the dataclass if callers want it, but the panel wouldn't typically show both.

## CLI output — acceptance shape

```
$ uv run ksp dv kerbin_surface duna_surface
╭─ Δv trip — kerbin_surface → duna_surface ─────────────╮
│  From              →   To                  Δv   aero  │
│  ───────────────────────────────────────────────────  │
│  kerbin_surface    →   kerbin_low_orbit  3,400 m/s    │
│  …                                                    │
│  duna_capture      →   duna_low_orbit      360 m/s  ✓ −80% │
│  duna_low_orbit    →   duna_surface      1,450 m/s  ✓ −80% │
│                                                       │
│  Raw total                              6,270 m/s     │
│  With aerobrake                         4,822 m/s  (−1,448) │
│  Planned (+5% margin)                   5,063 m/s     │
╰───────────────────────────────────────────────────────╯
```

## Tests

### `tests/test_dv_map.py` — new unit tests (hand-built tree)

1. `plan_trip_with_aerobrake_credits_capable_edge` — tree with one `can_aerobrake=True` edge of 1,000 m/s; assert `total_aerobraked` == raw − 800.
2. `plan_trip_aerobrake_false_is_noop` — same tree; `aerobrake=False`; assert `total_aerobraked == total_raw`.
3. `plan_trip_mixed_edges_only_discounts_flagged` — tree with three flagged edges (500/1000/2000) and two unflagged edges (300/200); assert credit == 0.8 × (500+1000+2000) == 2800.
4. `plan_trip_aerobrake_field_echoes_input` — assert `TripPlan.aerobrake` matches the kwarg passed.
5. `plan_trip_aerobrake_planned_applies_margin` — assert `total_aerobraked_planned == total_aerobraked × 1.05` (with default margin).
6. `plan_trip_residual_constant_is_20` — sanity check the module constant so a future edit is caught.

### `tests/test_dv_map.py` — new integration tests (real seed)

7. `kerbin_to_duna_surface_aerobraked_totals` — `total_raw == 6270` (unchanged), `total_aerobraked == 4822 ±5`, `total_aerobraked_planned == 4822 × 1.05 ±10`.
8. `kerbin_to_mun_surface_aerobrake_is_noop` — no `can_aerobrake=True` edges on this path; `total_aerobraked == total_raw`.
9. `kerbin_to_eve_surface_aerobraked_shows_dramatic_savings` — raw ≈ 12,560; aerobraked ≈ 6,112 ±10. (Accepts the double-credit quirk on `eve_capture→eve_low_orbit` — documented limitation.)

### `tests/test_cli.py` — new CLI tests

10. `dv_aerobrake_on_by_default_shows_savings_row` — output contains `"With aerobrake"` for kerbin→duna; exit 0.
11. `dv_no_aerobrake_hides_savings_row` — `--no-aerobrake` run of the same trip: stdout does NOT contain `"With aerobrake"`.
12. `dv_no_aerobrake_matches_7b_totals` — `--no-aerobrake` numbers match 7a/7b expectations (e.g., kerbin→mun raw 5,150).
13. `dv_aerobrake_column_shows_credit_markers` — for kerbin→duna with aerobrake on, output contains `"−80%"` near a creditable edge.
14. Existing 7b tests kept green — any that assert exact panel text may need updating to allow for the new totals row.

### Acceptance gate for 7c

`uv run ksp dv kerbin_surface duna_surface` renders the panel above, with `Raw total = 6,270`, `With aerobrake = 4,822 (±5)`, and `Planned = 5,063 (±10)`. `uv run pytest` fully green; `uv run ruff check` clean.

## Known limitations (to be documented in PROGRESS.md)

1. **Double-credit on pre-baked capture edges.** Three edges store values that already reflect aerobrake in the community chart: `kerbin_capture→kerbin_low_orbit (0)`, `duna_capture→duna_low_orbit (360)`, `eve_capture→eve_low_orbit (80)`. They're also flagged `can_aerobrake=True`. Applying the 20%-residual credit on top of those edges over-discounts them by up to ~350 m/s across a full Kerbin+Duna+Eve outbound. Acceptable trade-off for 7c — dominant savings (Kerbin/Duna/Eve/Laythe descents) are modeled correctly. Fix deferred to 7e when the graph model is revisited.

2. **Round-trip + return-leg aerobrake** deferred. When added, the API is `plan_round_trip(stops, margin_pct, aerobrake)` per the feature-doc §API-surface sketch.

3. **Configurable residual** deferred. `AEROBRAKE_RESIDUAL_PCT` is a module constant; can be promoted to a CLI flag (`--aerobrake-residual`) later if 20% proves wrong.

## Non-goals

- Return trips / `--return` flag — deferred.
- `plan_round_trip` helper — deferred.
- Correcting the double-credit quirk on pre-baked capture edges — deferred to 7e.
- Configurable aerobrake residual via CLI — deferred.
- Per-body "has atmosphere" check — unnecessary, the `can_aerobrake` flag already encodes this.

## Files touched

| File | Change |
|---|---|
| `src/ksp_planner/dv_map.py` | `AEROBRAKE_RESIDUAL_PCT` constant; `TripPlan` gains `total_aerobraked`, `aerobrake`, `total_aerobraked_planned`; `plan_trip` gains `aerobrake=True` kwarg + credit computation. |
| `src/ksp_planner/cli.py` | `dv` gains `--no-aerobrake` boolean flag; passes through to `plan_trip`. |
| `src/ksp_planner/formatting.py` | `dv_trip_panel` updates `aero` column to tri-state; adds `"With aerobrake"` row to totals block when `trip.aerobrake`. |
| `tests/test_dv_map.py` | 6 unit tests + 3 integration tests (see above). |
| `tests/test_cli.py` | 4 new tests; updates to any existing panel-text assertions. |
| `docs/PROGRESS.md` | 7c completion log + 7d resume notes. |

## Acceptance summary

After 7c:

- `uv run pytest` green (expect ~192 passing, 179 + ~13 new).
- `uv run ruff check` clean.
- `uv run ksp dv kerbin_surface duna_surface` shows dual totals as above.
- `uv run ksp dv kerbin_surface mun_surface` — `Raw total = 5,150`; `With aerobrake` row present but identical (5,150) since path has no creditable edges. The savings delta is `(−0)`. (Design rule: always render the row when `aerobrake=True` — no special-casing for zero-savings paths. Keeps the renderer branch-free and output predictable.)
- `uv run ksp dv kerbin_surface duna_surface --no-aerobrake` — only `Raw total = 6,270` and `Planned`, no "With aerobrake" row.
- `uv run ksp dv kerbin_surface mun_surface --via minmus:orbit` — 7b behavior unaffected; new aerobrake totals present (all equal raw, since path is aerobrake-free).
