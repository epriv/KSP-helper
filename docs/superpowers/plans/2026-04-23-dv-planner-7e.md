# Δv Planner 7e Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Swap the LCA tree walk in `dv_map.path_dv` for a Dijkstra shortest-path search (public API unchanged), and fix the three pre-baked capture edges whose chart Δv already encodes aerobrake so they no longer get double-credited under `aerobrake=True`.

**Architecture:** Dijkstra uses stdlib `heapq` — no new dep. `DvGraph` gains an adjacency list built at init for O(deg(u)) neighbor iteration; `(from, to) → Edge` dict stays for explicit edge lookup. The capture-edge fix is a three-flag flip in `seeds/seed_stock.py` plus pin updates. No schema changes.

**Tech Stack:** Python 3.12, stdlib `heapq`, Typer, Rich, pytest, SQLite. Existing Δv tree + CLI in `src/ksp_planner/dv_map.py`, `src/ksp_planner/cli.py`.

**Spec:** [`docs/superpowers/specs/2026-04-23-dv-planner-7e-design.md`](../specs/2026-04-23-dv-planner-7e-design.md)

---

## File map

| File | Responsibility | Change |
|---|---|---|
| `src/ksp_planner/dv_map.py` | Δv graph types + path walk + plan_trip | Rewrite `path_dv` as Dijkstra; add `DvGraph.neighbors_of`; delete `_ancestors` and `_lowest_common_ancestor` |
| `seeds/seed_stock.py` | Stock seed data | Flip `aerobrake` from `True` to `False` on three pre-baked capture edges |
| `tests/test_dv_map.py` | dv_map unit + integration tests | Add Dijkstra shortcut test; replace eve-aerobrake-credit test; add sibling duna/kerbin tests; update two 7c integration pins |
| `tests/test_cli.py` | CLI tests | Update one 7c Duna aerobraked pin |
| `docs/PROGRESS.md` | Build log | 7e completion log; Phase 7 → ✅ done; update key decision 11 |
| `docs/02-data-sources.md` | Data provenance | One-sentence note that chart has no inter-moon shortcuts |
| `docs/features/dv-planner.md` | Δv planner feature doc | Update §7e to reflect shipped scope |

---

## Task 1: Dijkstra swap (algorithm change, API unchanged)

**Why first:** The LCA walk only works on strict trees. The synthetic shortcut test in Step 1.1 would crash against the LCA walk (the synthetic graph isn't a tree). We write the test RED, implement Dijkstra GREEN, and let the existing 201-test suite act as the regression guard that equivalence on the tree seed is preserved.

**Files:**
- Modify: `src/ksp_planner/dv_map.py:60-125` (`DvGraph` + `_ancestors` + `_lowest_common_ancestor` + `path_dv`)
- Modify: `tests/test_dv_map.py` (append new test block after the existing `path_dv` tests)

- [ ] **Step 1.1: Write the failing Dijkstra shortcut test**

Append to `tests/test_dv_map.py` (a new section right after the existing `# ---------- path_dv ----------` block — find a natural spot before the `# ---------- resolve_stop ----------` section around line 307, or just after the 7d round-trip block at the end of the file):

```python
# ---------- 7e: Dijkstra shortcut handling ----------


def test_dijkstra_picks_cheapest_edge_when_shortcut_exists():
    """Synthetic graph with a direct shortcut cheaper than the tree walk.

    Graph:
        root
         ├── a  (edge root→a: 50)
         │     └── b  (edge a→b: 30)
         └── c  (edge root→c: 5, edge c→b shortcut: 10)

    Tree-only path a→b is the 30 edge. But the cheapest a→b path is
    a→root→c→b = 50 + 5 + 10 = 65? No: we need reverse edges too.

    Build a graph where a→b via tree is 30, but a→c→b direct shortcut is 15.
    """
    from ksp_planner.dv_map import DvGraph, DvNode, Edge, path_dv

    nodes = [
        DvNode(slug="root", parent_slug=None, body_slug=None, state="sun_orbit"),
        DvNode(slug="a", parent_slug="root", body_slug=None, state="transfer"),
        DvNode(slug="b", parent_slug="a", body_slug=None, state="low_orbit"),
        DvNode(slug="c", parent_slug="root", body_slug=None, state="transfer"),
    ]
    edges = [
        # Tree edges, both directions
        Edge(from_slug="root", to_slug="a", dv_m_s=10, can_aerobrake=False),
        Edge(from_slug="a", to_slug="root", dv_m_s=10, can_aerobrake=False),
        Edge(from_slug="a", to_slug="b", dv_m_s=30, can_aerobrake=False),
        Edge(from_slug="b", to_slug="a", dv_m_s=30, can_aerobrake=False),
        Edge(from_slug="root", to_slug="c", dv_m_s=5, can_aerobrake=False),
        Edge(from_slug="c", to_slug="root", dv_m_s=5, can_aerobrake=False),
        # Shortcut: c → b directly, cheaper than the tree detour
        Edge(from_slug="c", to_slug="b", dv_m_s=2, can_aerobrake=False),
        Edge(from_slug="b", to_slug="c", dv_m_s=2, can_aerobrake=False),
    ]
    g = DvGraph(nodes=nodes, edges=edges)

    # Tree path a→b direct: 30. Shortcut path a→root→c→b: 10 + 5 + 2 = 17. Dijkstra picks shortcut.
    path = path_dv(g, "a", "b")
    total = sum(e.dv_m_s for e in path)
    assert total == 17, f"expected 17 via shortcut, got {total} via {[(e.from_slug, e.to_slug) for e in path]}"
    assert [e.from_slug for e in path] == ["a", "root", "c"]
    assert [e.to_slug for e in path] == ["root", "c", "b"]


def test_dijkstra_unreachable_raises_value_error():
    """Two disconnected components: ValueError, same exception type as the old LCA walk."""
    from ksp_planner.dv_map import DvGraph, DvNode, path_dv

    nodes = [
        DvNode(slug="x", parent_slug=None, body_slug=None, state="sun_orbit"),
        DvNode(slug="y", parent_slug=None, body_slug=None, state="sun_orbit"),
    ]
    g = DvGraph(nodes=nodes, edges=[])
    with pytest.raises(ValueError, match="no path"):
        path_dv(g, "x", "y")


def test_dijkstra_self_loop_returns_empty():
    """Identity path: from == to → []; no search performed."""
    from ksp_planner.dv_map import DvGraph, DvNode, path_dv

    nodes = [DvNode(slug="only", parent_slug=None, body_slug=None, state="sun_orbit")]
    g = DvGraph(nodes=nodes, edges=[])
    assert path_dv(g, "only", "only") == []


def test_dijkstra_unknown_slug_raises_key_error():
    """Unknown endpoints raise KeyError, same as under the LCA walk."""
    from ksp_planner.dv_map import DvGraph, DvNode, path_dv

    nodes = [DvNode(slug="a", parent_slug=None, body_slug=None, state="sun_orbit")]
    g = DvGraph(nodes=nodes, edges=[])
    with pytest.raises(KeyError):
        path_dv(g, "a", "nonexistent")
    with pytest.raises(KeyError):
        path_dv(g, "nonexistent", "a")
```

- [ ] **Step 1.2: Confirm the shortcut test fails under the LCA walk**

Run: `cd "/Users/aj/Development/KSP App" && uv run pytest tests/test_dv_map.py -k "dijkstra" -v`

Expected:
- `test_dijkstra_picks_cheapest_edge_when_shortcut_exists` FAILS — the LCA walk doesn't know about shortcuts and probably crashes trying to find a common ancestor in a non-strict tree.
- `test_dijkstra_unreachable_raises_value_error` — LCA walk may raise `ValueError` with a different message (`"no common ancestor..."`). Acceptable either way; match is lenient (`"no path"` is absent so test fails with mismatch, documenting the message we're about to introduce).
- Self-loop and unknown-slug tests likely pass (existing behaviour).

The point of the RED step: confirm Dijkstra is necessary by watching the shortcut test fail.

- [ ] **Step 1.3: Implement Dijkstra + `DvGraph.neighbors_of`**

Edit `src/ksp_planner/dv_map.py`.

At line 1-11 (top-of-file imports), replace:
```python
"""Δv chart tree + path finding — Phase 7a.

Pure data structures over a directed-edge tree. The DB layer loads `DvGraph`;
`path_dv` and `plan_trip` operate on the graph with no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise
from typing import Literal
```
with:
```python
"""Δv chart graph + path finding — Phase 7a (Dijkstra since 7e).

Pure data structures over a directed graph. The DB layer loads `DvGraph`;
`path_dv` and `plan_trip` operate on the graph with no I/O.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass
from itertools import pairwise
from typing import Literal
```

Replace the `DvGraph` class (lines 60-76) with:
```python
class DvGraph:
    """Bundle of nodes + directed edges. Indexed for O(1) edge lookup and O(deg(u)) neighbor iteration."""

    def __init__(self, nodes: list[DvNode], edges: list[Edge]):
        self._nodes: dict[str, DvNode] = {n.slug: n for n in nodes}
        self._edges: dict[tuple[str, str], Edge] = {(e.from_slug, e.to_slug): e for e in edges}
        self._adj: dict[str, list[Edge]] = {}
        for e in edges:
            self._adj.setdefault(e.from_slug, []).append(e)

    def node(self, slug: str) -> DvNode:
        if slug not in self._nodes:
            raise KeyError(f"unknown dv node: {slug!r}")
        return self._nodes[slug]

    def edge(self, from_slug: str, to_slug: str) -> Edge:
        key = (from_slug, to_slug)
        if key not in self._edges:
            raise KeyError(f"no dv edge from {from_slug!r} to {to_slug!r}")
        return self._edges[key]

    def neighbors_of(self, slug: str) -> list[Edge]:
        """Outgoing edges from `slug`. Raises KeyError if `slug` is unknown.

        Returns `[]` for a known-but-edgeless node (e.g. an isolated component).
        """
        if slug not in self._nodes:
            raise KeyError(f"unknown dv node: {slug!r}")
        return self._adj.get(slug, [])
```

Delete `_ancestors` (lines 79-86) and `_lowest_common_ancestor` (lines 89-95) — they're dead code after the swap.

Replace the `path_dv` function (lines 98-125) with:
```python
def path_dv(graph: DvGraph, from_slug: str, to_slug: str) -> list[Edge]:
    """Shortest-Δv path from `from_slug` to `to_slug` (Dijkstra).

    Raises KeyError if either slug is unknown; ValueError if no path exists.
    Returns `[]` when `from_slug == to_slug`.
    """
    if from_slug == to_slug:
        graph.node(from_slug)  # surface KeyError on unknown slug
        return []
    graph.node(from_slug)
    graph.node(to_slug)

    dist: dict[str, float] = {from_slug: 0.0}
    prev: dict[str, tuple[str, Edge]] = {}
    counter = 0  # monotonic tiebreaker so heapq never compares strings
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

- [ ] **Step 1.4: Run the Dijkstra tests — expect pass**

Run: `cd "/Users/aj/Development/KSP App" && uv run pytest tests/test_dv_map.py -k "dijkstra" -v`

Expected: all 4 new tests pass.

- [ ] **Step 1.5: Full suite — regression guard for tree equivalence**

Run: `cd "/Users/aj/Development/KSP App" && make test`

Expected: all 205 tests pass (201 + 4 new). Every existing tree-walk assertion must still hold — Dijkstra on a strict tree produces the same unique simple path.

If any existing test fails: stop and investigate. Likely causes are (a) off-by-one in prev-chain reconstruction, (b) wrong tiebreaker producing a different but equal-length path, or (c) the unreachable-path message breaking a CLI error-path regex. Fix before proceeding.

- [ ] **Step 1.6: Lint**

Run: `cd "/Users/aj/Development/KSP App" && make lint`

Expected: clean. If ruff complains about unused imports (e.g., stale imports from the deleted helpers), remove them.

- [ ] **Step 1.7: Commit**

```bash
cd "/Users/aj/Development/KSP App"
git add src/ksp_planner/dv_map.py tests/test_dv_map.py
git commit -m "$(cat <<'EOF'
feat(7e): swap LCA walk for Dijkstra in path_dv

Path-finder generalised to Dijkstra shortest-path over DvGraph. Public API
(path_dv, plan_trip, plan_round_trip) unchanged; existing 201 tests stay
green as the tree-equivalence regression guard. DvGraph gains neighbors_of
with an adjacency list built at init. Sets up the graph for future
non-tree edges without another algorithm swap.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Double-credit fix — reclassify three pre-baked capture edges

**Why lockstep:** The seed flag flip, the `test_eve_capture_*` rewrite, the two new sibling tests, and the two Duna/Eve integration pin updates are one semantic change. Splitting them leaves the suite red between steps. Write / update all tests first (RED), then flip the seed flags (GREEN).

**Files:**
- Modify: `seeds/seed_stock.py:181` (Eve), `:192` (Duna), `:159` (Kerbin)
- Modify: `tests/test_dv_map.py:297-304` (rewrite Eve-capture test); also the Duna/Eve integration pins around lines 411-444
- Modify: `tests/test_cli.py:478-486` (one Duna CLI pin)

- [ ] **Step 2.1: Rewrite the Eve-capture flag test and add Duna / Kerbin siblings**

In `tests/test_dv_map.py`, find the existing test at line 297:
```python
def test_eve_capture_claims_aerobrake_credit(db):
    """Eve's tiny chart capture (~80 m/s) only makes sense with aerobrake."""
    from ksp_planner.db import load_dv_graph

    g = load_dv_graph(db)
    edge = g.edge("eve_capture", "eve_low_orbit")
    assert edge.can_aerobrake, "Eve insertion needs can_aerobrake=True for the chart value"
    assert edge.dv_m_s < 200, f"chart Eve capture ~80 m/s w/ aerobrake, got {edge.dv_m_s}"
```

Replace with:
```python
def test_eve_capture_is_not_aerobrake_credited(db):
    """Eve's chart capture (~80 m/s) ALREADY encodes aerobrake — flag must be False.

    The chart value is the aerobraked version; leaving can_aerobrake=True would
    double-credit under aerobrake=True. Fix shipped in 7e.
    """
    from ksp_planner.db import load_dv_graph

    g = load_dv_graph(db)
    edge = g.edge("eve_capture", "eve_low_orbit")
    assert not edge.can_aerobrake, (
        "eve_capture→eve_low_orbit is a pre-baked chart value; "
        "can_aerobrake must be False to avoid double-credit"
    )
    assert edge.dv_m_s < 200, f"chart Eve capture ~80 m/s, got {edge.dv_m_s}"


def test_duna_capture_is_not_aerobrake_credited(db):
    """Duna's chart capture (360 m/s) is pre-baked aerobraked — flag must be False."""
    from ksp_planner.db import load_dv_graph

    g = load_dv_graph(db)
    edge = g.edge("duna_capture", "duna_low_orbit")
    assert not edge.can_aerobrake, (
        "duna_capture→duna_low_orbit is a pre-baked chart value; "
        "can_aerobrake must be False to avoid double-credit"
    )
    assert 300 < edge.dv_m_s < 400


def test_kerbin_capture_is_not_aerobrake_credited(db):
    """Kerbin's chart capture (0 m/s, interplanetary return aerocapture) is pre-baked.

    Zero-value edge so arithmetic is unchanged, but the flag must be False for
    consistency — the chart already models aerocapture as free.
    """
    from ksp_planner.db import load_dv_graph

    g = load_dv_graph(db)
    edge = g.edge("kerbin_capture", "kerbin_low_orbit")
    assert not edge.can_aerobrake, (
        "kerbin_capture→kerbin_low_orbit is a pre-baked 0 m/s chart value; "
        "can_aerobrake must be False for consistency with Eve/Duna siblings"
    )
    assert edge.dv_m_s == 0
```

- [ ] **Step 2.2: Update the Duna aerobraked integration pin**

In `tests/test_dv_map.py` at line 411, replace:
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

with:
```python
def test_kerbin_to_duna_surface_aerobraked_totals(db):
    """kerbin→duna: raw 6,270; aerobraked 4,820 (only duna descent 1450→0 credits).

    7e: duna_capture→duna_low_orbit (360) reclassified can_aerobrake=False — its
    chart value already encodes aerobrake, so it stays full under aerobrake=True.
    """
    from ksp_planner.db import load_dv_graph

    g = load_dv_graph(db)
    plan = plan_trip(g, [Stop("kerbin_surface"), Stop("duna_surface")])
    assert plan.total_raw == pytest.approx(6270, abs=5)
    assert plan.total_aerobraked == pytest.approx(4820, abs=5)
    assert plan.total_aerobraked_planned == pytest.approx(4820 * 1.05, abs=10)
    assert plan.aerobrake is True
```

- [ ] **Step 2.3: Update the Eve aerobraked integration pin**

In `tests/test_dv_map.py` at line 433, replace:
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

with:
```python
def test_kerbin_to_eve_surface_aerobraked_shows_dramatic_savings(db):
    """Eve descent (8000 ballistic) zeroed; Eve capture (80) stays full.

    7e: eve_capture→eve_low_orbit reclassified can_aerobrake=False (chart value
    already encodes aerobrake). Only the 8000 m/s Eve descent credits.
    """
    from ksp_planner.db import load_dv_graph

    g = load_dv_graph(db)
    plan = plan_trip(g, [Stop("kerbin_surface"), Stop("eve_surface")])
    # Outbound: 3400 (ascent, up — not aerobrakable) + 0 (trunk) + 1080 (Eve ejection)
    #           + 80 (Eve capture, pre-baked) + 8000 (Eve descent) = 12,560
    # With aerobrake: 3400 + 0 + 1080 + 80 + 0 = 4,560
    assert plan.total_raw == pytest.approx(12560, abs=10)
    assert plan.total_aerobraked == pytest.approx(4560, abs=10)
    assert plan.total_raw - plan.total_aerobraked == pytest.approx(8000, abs=10)
```

- [ ] **Step 2.4: Update the Duna CLI pin**

In `tests/test_cli.py` at line 478, replace:
```python
def test_dv_kerbin_to_duna_shows_with_aerobrake_row(seed_db):
    """Default (aerobrake on): panel shows 'With aerobrake' totals row."""
    r = _invoke(seed_db, "dv", "kerbin_surface", "duna_surface")
    assert r.exit_code == 0, r.stdout
    assert "Raw total" in r.stdout
    assert "With aerobrake" in r.stdout
    # raw 6,270; aerobraked 4,460; planned aerobraked 4,683
    assert "6,270" in r.stdout
    assert "4,460" in r.stdout
```

with:
```python
def test_dv_kerbin_to_duna_shows_with_aerobrake_row(seed_db):
    """Default (aerobrake on): panel shows 'With aerobrake' totals row."""
    r = _invoke(seed_db, "dv", "kerbin_surface", "duna_surface")
    assert r.exit_code == 0, r.stdout
    assert "Raw total" in r.stdout
    assert "With aerobrake" in r.stdout
    # 7e: raw 6,270; aerobraked 4,820 (duna_capture reclassified — only descent credits)
    assert "6,270" in r.stdout
    assert "4,820" in r.stdout
```

- [ ] **Step 2.5: Run the updated tests — expect fail**

Run: `cd "/Users/aj/Development/KSP App" && uv run pytest tests/test_dv_map.py tests/test_cli.py -k "capture or _to_duna or _to_eve" -v`

Expected: the three `_is_not_aerobrake_credited` tests fail (current flag is True on Eve/Duna/Kerbin captures); the two integration pins fail (seed still credits the pre-baked edges); the CLI pin fails.

- [ ] **Step 2.6: Flip the three `aerobrake` flags in the seed**

Edit `seeds/seed_stock.py`.

At line 159, replace:
```python
    ("kerbin_capture",   "kerbin_low_orbit", 0,    0,    True),   # aerobrake re-entry
```
with:
```python
    ("kerbin_capture",   "kerbin_low_orbit", 0,    0,    False),  # 7e: pre-baked 0 m/s chart value, no double-credit
```

At line 181, replace:
```python
    ("eve_capture",      "eve_low_orbit",    80,   80,   True),   # Eve aerobrake nearly free
```
with:
```python
    ("eve_capture",      "eve_low_orbit",    80,   80,   False),  # 7e: chart value already encodes aerobrake
```

At line 192, replace:
```python
    ("duna_capture",     "duna_low_orbit",   360,  360,  True),   # Duna aerobrake helps capture
```
with:
```python
    ("duna_capture",     "duna_low_orbit",   360,  360,  False),  # 7e: chart value already encodes aerobrake
```

- [ ] **Step 2.7: Regenerate the seed DB**

Run: `cd "/Users/aj/Development/KSP App" && make seed`

Expected: `ksp.db` regenerated without errors.

- [ ] **Step 2.8: Run the targeted tests — expect pass**

Run: `cd "/Users/aj/Development/KSP App" && uv run pytest tests/test_dv_map.py tests/test_cli.py -k "capture or _to_duna or _to_eve" -v`

Expected: all pass.

- [ ] **Step 2.9: Full suite**

Run: `cd "/Users/aj/Development/KSP App" && make test`

Expected: all 205 tests pass (201 + 4 Dijkstra tests from Task 1, with the three old aerobrake-credit tests replaced by three new `_is_not_aerobrake_credited` tests — net +4 from baseline, but the total count should be 205 (201 pre-7e + 4 Dijkstra + 2 new sibling tests - 0 removed = wait, verify: 201 + 4 Dijkstra = 205, then Task 2 replaces 1 test with 3, so +2 = 207). Actual expected total: **207**.

Note on test count arithmetic: Task 1 adds 4 new tests (net +4 → 205). Task 2 replaces `test_eve_capture_claims_aerobrake_credit` with three tests (`_is_not_aerobrake_credited` variants for eve/duna/kerbin), net +2 → 207.

- [ ] **Step 2.10: Lint**

Run: `cd "/Users/aj/Development/KSP App" && make lint`

Expected: clean.

- [ ] **Step 2.11: Manual smoke check**

Run: `cd "/Users/aj/Development/KSP App" && uv run ksp dv kerbin_surface duna_surface`

Expected panel values:
- Raw total: 6,270 m/s
- With aerobrake: 4,820 m/s
- Savings: −1,450 m/s (only the Duna descent credits now)
- `duna_capture → duna_low_orbit` row's aero column is now blank (not `✓ −100%`).

Run: `cd "/Users/aj/Development/KSP App" && uv run ksp dv kerbin_surface eve_surface`

Expected:
- Raw total: 12,560 m/s
- With aerobrake: 4,560 m/s
- Savings: −8,000 m/s (only Eve descent credits).

- [ ] **Step 2.12: Commit**

```bash
cd "/Users/aj/Development/KSP App"
git add seeds/seed_stock.py tests/test_dv_map.py tests/test_cli.py ksp.db
git commit -m "$(cat <<'EOF'
fix(7e): reclassify pre-baked capture edges as non-aerobrakable

Eve (80), Duna (360), and Kerbin (0) capture edges had can_aerobrake=True,
but their chart values already encode aerobrake — the "aerobrake" flag was
double-crediting under aerobrake=True. Flip to False on all three. Only
real aerobraking venues (descents: Eve 8000, Duna 1450, Kerbin 3400) keep
the credit. kerbin→duna aerobraked: 4,460 → 4,820. kerbin→eve aerobraked:
4,480 → 4,560. kerbin→mun round-trip unchanged (path doesn't hit these).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

Note: `ksp.db` is a build artifact; include it in the commit only if the repo tracks it (check `git status` first — if untracked or ignored, drop it from the add list). If it's gitignored, `make seed` will regenerate it from the source when needed.

---

## Task 3: Phase-close ritual

**Files:**
- Modify: `docs/PROGRESS.md` (completion log, test count, Phase 7 status, key-decision 11 update)
- Modify: `docs/02-data-sources.md` (one-sentence note about no inter-moon chart shortcuts)
- Modify: `docs/features/dv-planner.md` (update §7e to reflect shipped scope)

- [ ] **Step 3.1: Final full-suite + lint green check**

Run: `cd "/Users/aj/Development/KSP App" && make test && make lint`

Expected: all 207 tests pass, ruff clean.

- [ ] **Step 3.2: /simplify on changed files**

Invoke the `/simplify` skill against the changes from this sub-phase. Focus files:
- `src/ksp_planner/dv_map.py` (new Dijkstra implementation; deleted LCA helpers)
- `seeds/seed_stock.py` (flag-flip comments)

Apply any safe simplifications directly. If the skill proposes a change that affects pinned values or public API, pause and ask.

- [ ] **Step 3.3: Update `docs/02-data-sources.md`**

Add a one-sentence note under the Δv chart provenance section: the community subway chart publishes no direct inter-moon or cross-branch edges — the tree topology is complete, and any future shortcut edges would need a second, distinct numerical source with its own provenance.

Exact text to append after the existing Δv chart section (find the relevant paragraph, likely near the bottom):

```markdown
**No chart-sourced shortcut edges.** The Cuky / Kowgan subway chart (all lineage variants checked: SVG in Kowgan/ksp_cheat_sheets, the KSP forum thread, and the SpaceDock mod page) publishes zero direct inter-moon or cross-branch edges. Every numeric label matches the existing tree seed. Any future Laythe↔Vall, Mun↔Minmus, etc. shortcut would require a second numerical source (e.g. KSPTOT / alexmoon Hohmann calculator output) with distinct provenance — out of scope for 7e.
```

- [ ] **Step 3.4: Update `docs/features/dv-planner.md` §7e**

Replace the `### 7e — Graph upgrade *(optional)*` block (around line 127) with:

```markdown
### 7e — Graph upgrade ✅ *(shipped 2026-04-23)*

- Swapped LCA tree walk for Dijkstra shortest-path over `DvGraph`; public API unchanged.
- `DvGraph.neighbors_of(slug)` added for O(deg(u)) neighbor iteration; adjacency list built at init.
- **No chart-sourced shortcut edges.** Research confirmed the Cuky community chart publishes zero direct inter-moon values — tree topology is complete. Future shortcuts require a second numerical source; deferred.
- Fixed the 7c-era double-credit on pre-baked capture edges: `eve_capture → eve_low_orbit` (80), `duna_capture → duna_low_orbit` (360), and `kerbin_capture → kerbin_low_orbit` (0) now have `can_aerobrake=False`. Chart values already encode aerobrake; credit was previously applied twice under `aerobrake=True`.

**Done when:** all existing tests pass under Dijkstra (tree-equivalence guarantee); `kerbin_surface → duna_surface` aerobraked shifts 4,460 → 4,820 (only Duna descent credits); synthetic `test_dijkstra_picks_cheapest_edge_when_shortcut_exists` passes on a graph with a non-tree shortcut edge.
```

- [ ] **Step 3.5: Update `docs/PROGRESS.md`**

Apply these edits:

1. **Header (lines 5-6)** — bump `Last updated:` to the current date, test count to `207`, and re-verify coverage via `make test-cov` if the pinned percentages shifted meaningfully.

2. **Phases table row for Phase 7 (line 21)** — change from:
   ```
   | 7 | Δv planner (tree model, margin, stops) | 🟡 in progress (7a ✅; 7b ✅; 7c ✅; 7d ✅; 7e next) | ...
   ```
   to:
   ```
   | 7 | Δv planner (tree + Dijkstra, margin, stops) | ✅ done | Shipped 7a–7e; design locked in [features/dv-planner.md](features/dv-planner.md) |
   ```

3. **Phase 7 breakdown sub-table (line 43)** — change 7e from `⬜ not started` to `✅ done`, and rewrite the acceptance-test cell to reflect the reframed gate:
   ```
   | 7e | Dijkstra swap + double-credit fix on pre-baked capture edges | ✅ done | Existing 201 tests stay green under Dijkstra; kerbin→duna aerobraked shifts 4,460 → 4,820 after capture-edge reclassification |
   ```

4. **Add `### Phase 7e completion log`** after the 7d log (after the current line ~118), covering:
   - Scope decision: inter-moon shortcut edges dropped because Cuky's chart publishes none (full SVG audit linked); 7e repurposed as Dijkstra algorithm swap + long-deferred double-credit fix.
   - Dijkstra replaces LCA walk in `path_dv`; `DvGraph.neighbors_of` added; `_ancestors` / `_lowest_common_ancestor` deleted. All 201 pre-7e tests stay green as the tree-equivalence guard.
   - Three pre-baked capture edges (Eve 80, Duna 360, Kerbin 0) reclassified `can_aerobrake=False`. kerbin→duna aerobraked 4,460 → 4,820 (only 1450 descent credits); kerbin→eve 4,480 → 4,560 (only 8000 descent credits); Mun round-trip path unchanged.
   - 4 new Dijkstra tests (shortcut, unreachable, self-loop, unknown); 3 new `_is_not_aerobrake_credited` tests replacing the old Eve test.
   - New acceptance: every existing test passes under Dijkstra; synthetic shortcut test proves future edges will be honored.

5. **Replace** the `### 7e resume point — Graph upgrade` block (currently lines ~119-134) with a `### Phase 7 done` closing note pointing forward: "Next up: Phase 8 (Web UI + prod1 deploy). Until then, the Δv planner is feature-complete for CLI use."

6. **Running the app section** — no new commands; the Dijkstra swap is transparent. The existing `uv run ksp dv ...` examples still work. Optionally add a one-line comment: `# Phase 7e: Dijkstra under the hood; API unchanged`.

7. **Key decisions item 11** — mark the double-credit quirk as resolved. Update the text to reflect that the three pre-baked capture edges are now flagged `can_aerobrake=False` and no longer over-credit under `aerobrake=True`.

8. **Key decisions** — optionally add item 12: "Phase 7e scope redirection (2026-04-23): dropped inter-moon shortcut edges because the community chart publishes none; shipped Dijkstra generalisation + double-credit fix instead."

- [ ] **Step 3.6: Commit docs**

```bash
cd "/Users/aj/Development/KSP App"
git add docs/PROGRESS.md docs/02-data-sources.md docs/features/dv-planner.md
git commit -m "$(cat <<'EOF'
docs(7e): complete phase — Dijkstra + double-credit fix; no chart shortcuts

Phase 7 closes. 7e shipped Dijkstra in path_dv (public API unchanged,
tree-equivalence regression-guarded), reclassified the three pre-baked
capture edges as can_aerobrake=False, and documented that the community
chart publishes no direct inter-moon edges — any future shortcuts need a
second numerical source. Test total: 207. Next up: Phase 8 web UI.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 3.7: Announce reset**

Surface a short status to the user:
- What shipped (Dijkstra swap + double-credit fix).
- Test total (207).
- Phase 7 is ✅ done; phase ladder next is Phase 8 (Web UI).
- Stop.

---

## Notes on type consistency and spec coverage

**Function / type names used across tasks:**
- `DvGraph.neighbors_of(slug) -> list[Edge]` — defined Task 1, used internally in `path_dv`.
- `path_dv(graph, from, to) -> list[Edge]` — reimplemented Task 1; signature unchanged.
- `plan_trip`, `plan_round_trip`, `Stop`, `Edge`, `DvNode`, `TripPlan` — unchanged.

**Spec coverage check:**
- Dijkstra algorithm swap (§1) → Task 1. ✓
- Preserve public API / tree-equivalence (§1 design) → Task 1.5 full-suite guard. ✓
- Reclassify three pre-baked capture edges (§2) → Task 2.6. ✓
- Updated integration pins (§Test fallout) → Task 2.2, 2.3, 2.4. ✓
- `docs/02-data-sources.md` note on no chart shortcuts → Task 3.3. ✓
- `docs/features/dv-planner.md` §7e update → Task 3.4. ✓
- PROGRESS.md completion log + phase-close ritual → Task 3.5, 3.6. ✓
- `_ancestors` / `_lowest_common_ancestor` deletion → Task 1.3. ✓
