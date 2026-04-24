"""Δv chart graph + path finding — Phase 7a (Dijkstra since 7e).

Pure data structures over a directed graph. The DB layer loads `DvGraph`;
`path_dv` and `plan_trip` operate on the graph with no I/O.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass
from itertools import pairwise
from typing import Literal


@dataclass(frozen=True)
class DvNode:
    slug: str
    parent_slug: str | None
    body_slug: str | None
    state: str


@dataclass(frozen=True)
class Edge:
    from_slug: str
    to_slug: str
    dv_m_s: float
    can_aerobrake: bool


@dataclass(frozen=True)
class Stop:
    slug: str
    action: Literal["land", "orbit", "flyby"] = "orbit"


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


ACTION_SUFFIXES = {
    "land": "_surface",
    "orbit": "_low_orbit",
    "flyby": "_transfer",
}

# 0% residual = aerobrake fully credits can_aerobrake edges (community-chart convention).
# The 5% trip margin is the safety buffer for correction burns and imperfect passes.
# Kept as a module constant so a future tune (e.g. 5%) is still a one-line change.
AEROBRAKE_RESIDUAL_PCT = 0.0


class DvGraph:
    """Bundle of nodes + directed edges.

    Indexed for O(1) edge lookup and O(deg(u)) neighbor iteration.
    """

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
        if slug not in self._nodes:
            raise KeyError(f"unknown dv node: {slug!r}")
        return self._adj.get(slug, [])


def path_dv(graph: DvGraph, from_slug: str, to_slug: str) -> list[Edge]:
    """Shortest-Δv path from `from_slug` to `to_slug` (Dijkstra).

    Raises KeyError if either slug is unknown; ValueError if no path exists.
    Returns `[]` when `from_slug == to_slug`.
    """
    graph.node(from_slug)
    if from_slug == to_slug:
        return []
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


def plan_round_trip(
    graph: DvGraph,
    stops: list[Stop],
    margin_pct: float = 5.0,
    aerobrake: bool = True,
) -> TripPlan:
    """Plan a round trip that returns to the starting stop.

    Doubles the itinerary: `[A, B]` → `[A, B, A]`; `[A, B, C]` → `[A, B, C, B, A]`.
    The doubled stops list is passed to `plan_trip`, which produces legs for every
    pairwise hop. Composes with intermediate stops and aerobrake credit.
    """
    if len(stops) < 2:
        raise ValueError("round trip requires at least two stops")
    doubled = [*stops, *reversed(stops[:-1])]
    return plan_trip(graph, doubled, margin_pct=margin_pct, aerobrake=aerobrake)


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
