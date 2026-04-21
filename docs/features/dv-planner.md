# Δv Planner

**Phase:** 7 — ships after Phase 6 mission plan persistence.

A trip planner over the canonical KSP delta-v chart. Starts as a two-point total; grows to support intermediate stops, return trips, aerobraking, and a stage-aware budget check. The graph upgrade (Dijkstra) is the last step, not the first.

## Data model — tree of nodes + directed edges

Every reachable "state" of a body is a node in a tree. Edges are labelled with Δv cost.

```
kerbol_orbit
├── moho_transfer  → moho_capture  → moho_low_orbit  → moho_surface
├── eve_transfer   → eve_capture   → eve_low_orbit   → eve_surface
│                                                   └→ gilly_transfer → gilly_capture → gilly_low_orbit → gilly_surface
├── kerbin_transfer → kerbin_capture → kerbin_low_orbit ─── kerbin_surface
│                                                       ├→ mun_transfer    → mun_low_orbit    → mun_surface
│                                                       └→ minmus_transfer → minmus_low_orbit → minmus_surface
├── duna_transfer  → duna_capture  → duna_low_orbit  → duna_surface
│                                                   └→ ike_transfer → ike_capture → ike_low_orbit → ike_surface
├── dres_transfer  → ...
├── jool_transfer  → jool_capture  → jool_low_orbit
│                                   ├→ laythe_transfer → laythe_capture → laythe_low_orbit → laythe_surface
│                                   ├→ vall_transfer   → vall_capture   → vall_low_orbit   → vall_surface
│                                   ├→ tylo_transfer   → tylo_capture   → tylo_low_orbit   → tylo_surface
│                                   ├→ bop_transfer    → bop_capture    → bop_low_orbit    → bop_surface
│                                   └→ pol_transfer    → pol_capture    → pol_low_orbit    → pol_surface
└── eeloo_transfer → eeloo_capture → eeloo_low_orbit → eeloo_surface
```

**Why a tree?**

- Matches how KSP players think about trips
- Path between any two nodes is unambiguous (LCA walk)
- No path-finding algorithm required — just walk up, walk down
- Direct moon-to-moon transfers (Laythe → Vall without bouncing through Jool orbit) are rare and can be added via the Phase 7e graph upgrade

See [docs/03-schema.md](../03-schema.md) for the `dv_nodes` and `dv_edges` tables.

## Canonical values, not computed

Option A chosen: seed the canonical community chart values directly.

**Why not compute from `orbital.py`?** The community chart includes corrections for gravity losses, real ascent profiles, imperfect Hohmann execution, and plane-change costs. Pure-math Hohmann Δv diverges from the chart by 3-8% on most legs.

**Cross-check test:** Phase 7a includes a test that *does* compute Hohmann Δv and asserts it's within 5% of the seeded value. If the seeded chart is ever typo'd, or if the orbital math is ever buggy, the test fails loudly.

## Path-finding algorithm

```python
def path_dv(from_slug: str, to_slug: str) -> list[Edge]:
    lca = lowest_common_ancestor(from_slug, to_slug)
    up   = walk_up(from_slug, until=lca)     # list[Edge]
    down = walk_down(lca, until=to_slug)     # list[Edge]
    return up + down
```

The `walk_up` direction uses ascent/escape edges; `walk_down` uses transfer/capture/descent edges. Because edges are stored directed, this Just Works.

## Margin — flat multiplier, configurable

```python
def plan_trip(stops, margin_pct=5.0):
    legs = [path_dv(a.slug, b.slug) for a, b in pairwise(stops)]
    raw  = sum(edge.dv for leg in legs for edge in leg)
    return TripPlan(
        legs=legs,
        total_raw=raw,
        margin_pct=margin_pct,
        total_planned=raw * (1 + margin_pct / 100),
    )
```

Default **5%**. User can override per call (CLI `--margin`, web form field).

Per-edge granular margins (e.g. ascent +10%, orbital maneuver +2%) are **not** in the first cut. Start flat; upgrade if flat feels too coarse in practice. Upgrade path: add `edge_type` column to `dv_edges`, swap the single `margin_pct` for a dict keyed by edge type.

## Intermediate stops

Each stop carries an `action`:

- `land` — target is `<body>_surface`
- `orbit` — target is `<body>_low_orbit`
- `flyby` — target is `<body>_capture` (approach only, no capture burn)

The planner splits the itinerary into pairwise legs and computes each leg separately. Return trips are just the itinerary reversed, appended.

## Phase ladder

Each sub-phase ships on its own, gated by its acceptance test.

### 7a — Total Δv, two points

- Seed `dv_nodes` and `dv_edges` from the canonical chart
- Implement `path_dv` (LCA walk)
- Implement `plan_trip` with flat margin
- CLI: `ksp dv <from> <to> [--margin 5]`

**Done when:** `ksp dv kerbin_surface mun_surface` outputs the right total within ±50 m/s of the chart.

### 7b — Intermediate stops

- CLI: `ksp dv <from> <to> --via <slug> --action orbit|land|flyby` (repeatable)
- `plan_trip` handles a list of stops, not just two

**Done when:** `kerbin_surface → minmus (orbit) → mun_surface` totals correctly.

### 7c — Return trip + aerobraking

- `--return` flag doubles the itinerary (reverse)
- `can_aerobrake` edges zero-out the descent leg when landing at an atmosphere body on return
- Output shows both "no aerobrake" and "with aerobrake" totals

**Done when:** `kerbin_surface → duna_surface → kerbin_surface --return` shows ~3,400 m/s savings from Kerbin aerobrake on the return leg.

### 7d — Stage-aware budget check

- Inputs: staged ship (list of `(wet_kg, dry_kg, isp_s)`), target trip
- Use Tsiolkovsky to compute available Δv per stage
- Verify the ship has enough Δv; if not, report which leg it runs dry on
- Pairs with the Phase 5 TWR/Tsiolkovsky calculator — shared module

**Done when:** given a canned Mun lander stage sheet, the planner confirms it reaches Mun surface and back.

### 7e — Graph upgrade *(optional)*

- Swap tree walk for Dijkstra
- Add inter-moon edges (Laythe → Vall, Mun → Minmus) with canonical values where the community has them
- Public API (`path_dv`, `plan_trip`) unchanged — callers don't care

**Done when:** `ksp dv laythe_low_orbit vall_low_orbit` picks the direct route instead of going through Jool orbit.

## Example output (7b)

```
TRIP: Kerbin surface → Mun surface, via Minmus (orbit)
──────────────────────────────────────────────────────
  Kerbin surface  → LKO                   3,400 m/s  ↑
  LKO             → Minmus transfer         930 m/s  ↑
  Minmus transfer → Minmus LO               160 m/s  ↓    [stop: orbit]
  Minmus LO       → Kerbin LO (return)      160 m/s  ↑
  Kerbin LO       → Mun transfer            860 m/s  ↑
  Mun transfer    → Mun LO                   310 m/s  ↓
  Mun LO          → Mun surface              580 m/s  ↓
──────────────────────────────────────────────────────
  One-way total (raw)                     6,400 m/s
  One-way total (+5% margin)              6,720 m/s  ← fuel this
  Round-trip (aerobrake Kerbin, +5%)      9,870 m/s
```

## API surface

```python
# dv_map.py

@dataclass(frozen=True)
class Stop:
    slug: str                       # dv_nodes.slug
    action: Literal["land", "orbit", "flyby"] = "orbit"

@dataclass(frozen=True)
class Edge:
    from_slug: str
    to_slug: str
    dv_m_s: float
    can_aerobrake: bool
    direction: Literal["up", "down"]

@dataclass(frozen=True)
class TripPlan:
    legs: list[list[Edge]]          # one inner list per pairwise stop hop
    total_raw: float
    margin_pct: float
    total_planned: float

def plan_trip(stops: list[Stop], margin_pct: float = 5.0) -> TripPlan: ...

def plan_round_trip(
    stops: list[Stop], margin_pct: float = 5.0, aerobrake: bool = True,
) -> TripPlan: ...
```

Rendering (tables, colors, Unicode arrows) is the caller's job. CLI uses Rich; web uses JSON.
