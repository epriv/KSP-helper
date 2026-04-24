# Δv Planner — Phase 7e Design

**Date:** 2026-04-23
**Status:** approved, ready for implementation plan
**Scope:** Graph algorithm upgrade (Dijkstra) + double-credit fix on pre-baked capture edges
**Follows:** [7d](2026-04-23-dv-planner-7d-design.md)
**Precedes:** Phase 8 (web UI)

## Goal

Generalise the path-finder in `dv_map.py` from a tree-only LCA walk to a Dijkstra shortest-path search, so the graph can accept non-tree edges in the future without another algorithm swap. Bundle the long-deferred fix for three pre-baked capture edges (Eve 80, Duna 360, Kerbin 0) whose chart values already encode aerobrake — reclassify as `can_aerobrake=False` to prevent double-credit when `aerobrake=True`.

## Scope decision — no new chart edges

The 7e plan originally called for adding chart-published inter-moon shortcuts (Mun↔Minmus, Laythe↔Vall, etc.). Research (SVG extraction from Kowgan/Cuky's canonical community subway chart, cross-checked against the KSP forum thread and SpaceDock) confirmed the chart publishes **zero** direct inter-moon or cross-branch edges. Every number on the chart matches our existing tree seed. Per the project rule "leave a pair out rather than guess," no new edges are added from the chart; no second numerical source is introduced in this phase.

Acceptance gate from the resume notes (`ksp dv laythe_low_orbit vall_low_orbit picks the direct route`) is **reframed** because no shortcut exists to route through. The new gate is the invariant the Dijkstra swap must preserve: every existing test stays green. The algorithm generalisation is still worthwhile as a future-proofing step.

## Non-goals

- **New inter-moon or cross-branch edges from any source.** See scope decision above.
- **Schema changes.** `dv_nodes` and `dv_edges` stay as-is; the double-credit fix is a flag change in `seeds/seed_stock.py`.
- **Configurable-residual CLI flag.** Deferred; `AEROBRAKE_RESIDUAL_PCT` stays a module constant.
- **Per-edge aerobrake override column.** The simple reclassification of three edges covers every known double-credit case.
- **Round-trip optimisation.** `plan_round_trip` still recomputes outbound edge lookups on the return leg. Negligible at ~60 edges.

## Design decisions

### 1. Dijkstra over LCA walk

Replace `path_dv`'s LCA-based tree walk with a Dijkstra shortest-path search over `DvGraph`. Implementation uses `heapq` from stdlib — no new dependency.

**API preserved.** `path_dv(graph, from_slug, to_slug) -> list[Edge]` signature unchanged. `plan_trip` and `plan_round_trip` compose through unchanged.

**Helper.** Add `DvGraph.neighbors_of(slug) -> list[Edge]` so Dijkstra can iterate outgoing edges in O(deg(u)) per relaxation step. Build the adjacency list once at `__init__`. The existing `(from, to) → Edge` dict stays for O(1) edge lookup by explicit endpoints.

**Behavioural equivalence on the current seed.** The seed is a strict tree (every edge is a parent-child link). In a tree, Dijkstra between two nodes produces exactly the unique simple path, which is what the LCA walk returns. All existing tests stay green as the regression guard.

**Unreachable-node semantics.** If `to_slug` is not reachable from `from_slug`, raise `ValueError` (same exception type the LCA walk raised). The LCA walk raised on a missing common ancestor; Dijkstra raises on exhausted search. Message format preserved to avoid breaking CLI error-path tests.

**Self-loop.** `from_slug == to_slug` still returns `[]` without searching, matching current behaviour.

### 2. Reclassify pre-baked capture edges as `can_aerobrake=False`

Three edges in `seeds/seed_stock.py` currently ship with `aerobrake=True` but whose Δv already encodes aerobrake (chart values of 0–360 m/s):

| edge | current | new | rationale |
|---|---|---|---|
| `eve_capture → eve_low_orbit` | `(80, 80, True)` | `(80, 80, False)` | 80 m/s only makes sense *because* aerobraking; chart value is the aerobraked version |
| `duna_capture → duna_low_orbit` | `(360, 360, True)` | `(360, 360, False)` | same rationale — 360 m/s is the chart's aerobraked Duna insertion |
| `kerbin_capture → kerbin_low_orbit` | `(0, 0, True)` | `(0, 0, False)` | 0 Δv chart value already reflects aerocapture on interplanetary return |

**What this changes.** Under `aerobrake=True`, these edges now contribute their full `dv_m_s` instead of 0 to `total_aerobraked`. The `kerbin_capture` edge is 0 either way, so it's a semantic-only fix. The Eve and Duna edges shift their aerobraked totals by +80 and +360 respectively on paths that traverse them.

**What it doesn't change.** `total_raw` is untouched (chart values themselves are unchanged). The descent edges (`eve_low_orbit → eve_surface` 8000, `duna_low_orbit → duna_surface` 1450, `kerbin_low_orbit → kerbin_surface` 3400) keep `aerobrake=True` — those are real aerobraking venues where ballistic is 8000+ and aerobraked is ~0.

**Rendering impact.** `dv_trip_panel`'s aero column now shows blank instead of `✓ −100%` on these three edges. User-visible but correct — these edges aren't aerobrake discounts, they're pre-baked chart values.

### 3. Algorithm sketch

```python
import heapq
from typing import NamedTuple

def path_dv(graph: DvGraph, from_slug: str, to_slug: str) -> list[Edge]:
    """Shortest-Δv path on the graph (Dijkstra). Raises ValueError if unreachable."""
    if from_slug == to_slug:
        graph.node(from_slug)  # surface KeyError on unknown slug
        return []
    graph.node(from_slug)
    graph.node(to_slug)

    dist: dict[str, float] = {from_slug: 0.0}
    prev: dict[str, tuple[str, Edge]] = {}
    counter = 0  # monotonic tiebreaker — avoids comparing strings on equal distances
    heap: list[tuple[float, int, str]] = [(0.0, counter, from_slug)]

    while heap:
        d, _, u = heapq.heappop(heap)
        if u == to_slug:
            break
        if d > dist.get(u, float("inf")):
            continue
        for edge in graph.neighbors_of(u):
            v = edge.to_slug
            nd = d + edge.dv_m_s
            if nd < dist.get(v, float("inf")):
                dist[v] = nd
                prev[v] = (u, edge)
                counter += 1
                heapq.heappush(heap, (nd, counter, v))

    if to_slug not in prev:
        raise ValueError(f"no path from {from_slug!r} to {to_slug!r}")

    edges: list[Edge] = []
    cur = to_slug
    while cur != from_slug:
        parent, edge = prev[cur]
        edges.append(edge)
        cur = parent
    edges.reverse()
    return edges
```

Private helpers `_ancestors` and `_lowest_common_ancestor` become dead code — delete.

## Acceptance

**Gate 1 (regression — primary acceptance):** All existing tests (201 after 7d) pass unchanged after the Dijkstra swap, confirming behavioural equivalence on the tree-shaped seed.

**Gate 2 (shortcut readiness — synthetic):** A new `test_dijkstra_picks_cheapest_edge_when_shortcut_exists` fixture builds a 4-node graph with a tree path (total dv 100) and a direct shortcut edge (dv 30). Dijkstra picks the shortcut. Proves the new algorithm actually exploits shortcuts if they exist.

**Gate 3 (double-credit fix):** New test pins that
- `eve_capture → eve_low_orbit`, `duna_capture → duna_low_orbit`, and `kerbin_capture → kerbin_low_orbit` have `can_aerobrake=False` in the seeded graph.
- `kerbin_surface → duna_surface` aerobraked total shifts 4,460 → 4,820.
- `kerbin_surface → eve_surface` aerobraked total shifts 4,480 → 4,560.
- CLI output reflects the same.

## Test fallout

Tests with pins affected by the double-credit fix:

- `tests/test_dv_map.py`
  - `test_eve_capture_claims_aerobrake_credit` (line 297) — inverts: the edge should now be `can_aerobrake=False`. Rename to `test_eve_capture_is_not_aerobrake_credited`. Add sibling tests for Duna and Kerbin captures.
  - `test_kerbin_to_duna_surface_aerobraked_totals` (line 411) — pin 4,460 → 4,820; docstring update.
  - `test_kerbin_to_eve_surface_aerobraked_shows_dramatic_savings` (line 433) — pin 4,480 → 4,560; adjust the comment arithmetic.
- `tests/test_cli.py`
  - `test_dv_kerbin_to_duna_shows_with_aerobrake_row` (line 478) — pin "4,460" → "4,820"; comment update.

Strategy: update the pins in a single commit with the seed flag flip and the test code, so no intermediate state has broken tests.

## Files touched

| File | Change |
|------|--------|
| `src/ksp_planner/dv_map.py` | Swap `path_dv` LCA walk → Dijkstra. Add `DvGraph.neighbors_of`. Delete dead `_ancestors` / `_lowest_common_ancestor` helpers. |
| `seeds/seed_stock.py` | Flip `aerobrake` bool on three pre-baked capture edges. |
| `tests/test_dv_map.py` | Dijkstra shortcut test; tree equivalence test; rename + replace Eve-aerobrake-credit test; add Duna/Kerbin siblings; update two 7c integration pins. |
| `tests/test_cli.py` | Update the Duna aerobraked CLI pin. |
| `docs/PROGRESS.md` | 7e completion log + Phase 7 row → `✅ done`; update Key Decision 11 (double-credit quirk → fixed); bump test / phase status. |
| `docs/02-data-sources.md` | One-sentence note: the community chart has no inter-moon shortcut edges — the tree topology is complete. |
| `docs/features/dv-planner.md` | Update §7e to reflect shipped scope (Dijkstra + double-credit fix; no new edges). |

## Build order (TDD)

1. **RED** — `test_dijkstra_picks_cheapest_edge_when_shortcut_exists`. Synthetic 4-node graph with shortcut edge. Will currently fail with the LCA walk because it doesn't know about shortcuts (actually it'll fail on missing parent chain, since the synthetic graph isn't a strict tree).
2. **GREEN** — Add `DvGraph.neighbors_of`; rewrite `path_dv` as Dijkstra; delete `_ancestors` / `_lowest_common_ancestor`. Full suite stays green as the equivalence regression guard.
3. **RED** — `test_eve_capture_is_not_aerobrake_credited`, `test_duna_capture_is_not_aerobrake_credited`, `test_kerbin_capture_is_not_aerobrake_credited`. Update the two Duna/Eve aerobraked integration pins (4,460 → 4,820; 4,480 → 4,560) and the CLI pin. All fail.
4. **GREEN** — Flip the three `aerobrake` flags in `seeds/seed_stock.py`. Regenerate `ksp.db` via `make seed`. Full suite green.
5. **Phase-close ritual** — `make test` + `make lint`; `/simplify` on changed files; update `docs/PROGRESS.md`, `docs/02-data-sources.md`, `docs/features/dv-planner.md`; commit; stop.

## Follow-ups / deferred

- **Chart-independent numerical shortcuts** (KSPTOT / alexmoon-derived). If real usage ever asks for direct Laythe↔Vall, a `seeds/data/dv_shortcuts.csv` with distinct provenance is the right shape. Out of scope for 7e.
- **Configurable-residual CLI flag.** Still not needed.
- **Round-trip outbound-edge caching.** Still fine at <100 edges.
