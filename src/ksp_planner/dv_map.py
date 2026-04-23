"""Δv chart tree + path finding — Phase 7a.

Pure data structures over a directed-edge tree. The DB layer loads `DvGraph`;
`path_dv` and `plan_trip` operate on the graph with no I/O.
"""

from __future__ import annotations

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
    """Bundle of nodes + directed edges. Indexed for O(1) parent and edge lookup."""

    def __init__(self, nodes: list[DvNode], edges: list[Edge]):
        self._nodes: dict[str, DvNode] = {n.slug: n for n in nodes}
        self._edges: dict[tuple[str, str], Edge] = {(e.from_slug, e.to_slug): e for e in edges}

    def node(self, slug: str) -> DvNode:
        if slug not in self._nodes:
            raise KeyError(f"unknown dv node: {slug!r}")
        return self._nodes[slug]

    def edge(self, from_slug: str, to_slug: str) -> Edge:
        key = (from_slug, to_slug)
        if key not in self._edges:
            raise KeyError(f"no dv edge from {from_slug!r} to {to_slug!r}")
        return self._edges[key]


def _ancestors(graph: DvGraph, slug: str) -> list[str]:
    """Slug + every ancestor up to (and including) the root."""
    chain = [slug]
    cur = graph.node(slug).parent_slug
    while cur is not None:
        chain.append(cur)
        cur = graph.node(cur).parent_slug
    return chain


def _lowest_common_ancestor(graph: DvGraph, a: str, b: str) -> str:
    a_chain = _ancestors(graph, a)
    b_set = set(_ancestors(graph, b))
    for slug in a_chain:
        if slug in b_set:
            return slug
    raise ValueError(f"no common ancestor for {a!r} and {b!r}")


def path_dv(graph: DvGraph, from_slug: str, to_slug: str) -> list[Edge]:
    """Edges traversed when walking the tree from `from_slug` to `to_slug`."""
    if from_slug == to_slug:
        graph.node(from_slug)  # surface KeyError on unknown slug
        return []

    lca = _lowest_common_ancestor(graph, from_slug, to_slug)

    up: list[Edge] = []
    cur = from_slug
    while cur != lca:
        parent = graph.node(cur).parent_slug
        up.append(graph.edge(cur, parent))
        cur = parent

    descent: list[str] = []
    cur = to_slug
    while cur != lca:
        descent.append(cur)
        cur = graph.node(cur).parent_slug

    down: list[Edge] = []
    cur = lca
    for nxt in reversed(descent):
        down.append(graph.edge(cur, nxt))
        cur = nxt

    return up + down


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
