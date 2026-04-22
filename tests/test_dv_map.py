r"""Δv path-finding tests — Phase 7a.

Hand-built tree fixture, no DB. Covers LCA tree-walk corner cases.

       root
      /    \
     A      B
    / \      \
   C   D      E
       |
       F
"""

from __future__ import annotations

import pytest

from ksp_planner.dv_map import DvGraph, DvNode, Edge, Stop, path_dv, plan_trip, resolve_stop


@pytest.fixture
def tree() -> DvGraph:
    nodes = [
        DvNode(slug="root", parent_slug=None, body_slug=None, state="sun_orbit"),
        DvNode(slug="a",    parent_slug="root", body_slug=None, state="transfer"),
        DvNode(slug="b",    parent_slug="root", body_slug=None, state="transfer"),
        DvNode(slug="c",    parent_slug="a",    body_slug=None, state="low_orbit"),
        DvNode(slug="d",    parent_slug="a",    body_slug=None, state="low_orbit"),
        DvNode(slug="e",    parent_slug="b",    body_slug=None, state="low_orbit"),
        DvNode(slug="f",    parent_slug="d",    body_slug=None, state="surface"),
    ]
    edges = [
        # adjacency: (child, parent, up_dv, down_dv)
        ("a", "root", 10, 100),
        ("b", "root", 20, 200),
        ("c", "a",    1,  11),
        ("d", "a",    2,  12),
        ("e", "b",    3,  13),
        ("f", "d",    4,  14),
    ]
    edge_objs = []
    for child, parent, up, down in edges:
        edge_objs.append(Edge(from_slug=child, to_slug=parent, dv_m_s=up,   can_aerobrake=False))
        edge_objs.append(Edge(from_slug=parent, to_slug=child, dv_m_s=down, can_aerobrake=False))
    return DvGraph(nodes=nodes, edges=edge_objs)


# ---------- path_dv ----------

def test_identity_returns_empty_path(tree):
    assert path_dv(tree, "f", "f") == []


def test_same_branch_walk_up(tree):
    # f -> d -> a, dv = 4 + 2 = 6
    legs = path_dv(tree, "f", "a")
    assert [(e.from_slug, e.to_slug, e.dv_m_s) for e in legs] == [
        ("f", "d", 4),
        ("d", "a", 2),
    ]


def test_same_branch_walk_down(tree):
    # a -> d -> f, dv = 12 + 14 = 26
    legs = path_dv(tree, "a", "f")
    assert [(e.from_slug, e.to_slug, e.dv_m_s) for e in legs] == [
        ("a", "d", 12),
        ("d", "f", 14),
    ]


def test_cross_lca_shallow(tree):
    # c -> f, LCA = a. up: c->a (1). down: a->d->f (12+14).
    legs = path_dv(tree, "c", "f")
    assert [(e.from_slug, e.to_slug, e.dv_m_s) for e in legs] == [
        ("c", "a", 1),
        ("a", "d", 12),
        ("d", "f", 14),
    ]
    assert sum(e.dv_m_s for e in legs) == 27


def test_cross_lca_deep_via_root(tree):
    # d -> e, LCA = root. up: d->a->root (2+10). down: root->b->e (200+13).
    legs = path_dv(tree, "d", "e")
    assert [(e.from_slug, e.to_slug, e.dv_m_s) for e in legs] == [
        ("d", "a", 2),
        ("a", "root", 10),
        ("root", "b", 200),
        ("b", "e", 13),
    ]
    assert sum(e.dv_m_s for e in legs) == 225


def test_unknown_from_slug_raises(tree):
    with pytest.raises(KeyError, match="ghost"):
        path_dv(tree, "ghost", "a")


def test_unknown_to_slug_raises(tree):
    with pytest.raises(KeyError, match="ghost"):
        path_dv(tree, "a", "ghost")


def test_missing_edge_raises(tree):
    # break the graph by removing one direction
    bad_edges = [e for e in tree._edges.values() if not (e.from_slug == "d" and e.to_slug == "f")]
    broken = DvGraph(nodes=list(tree._nodes.values()), edges=bad_edges)
    with pytest.raises(KeyError, match=r"d.*f"):
        path_dv(broken, "a", "f")


# ---------- plan_trip ----------

def test_plan_trip_two_stops_default_margin(tree):
    stops_in = [Stop("c"), Stop("f")]
    plan = plan_trip(tree, stops_in)
    assert plan.total_raw == 27
    assert plan.margin_pct == 5.0
    assert plan.total_planned == pytest.approx(27 * 1.05)
    assert len(plan.legs) == 1
    assert len(plan.legs[0]) == 3
    assert plan.stops == stops_in


def test_plan_trip_three_stops(tree):
    # c -> f -> e
    # leg1: c -> f = 27 (c->a 1, a->d 12, d->f 14)
    # leg2: f -> e (LCA root): f->d 4, d->a 2, a->root 10, root->b 200, b->e 13 = 229
    stops_in = [Stop("c"), Stop("f"), Stop("e")]
    plan = plan_trip(tree, stops_in)
    assert plan.total_raw == 27 + 229
    assert len(plan.legs) == 2
    assert plan.stops == stops_in


def test_plan_trip_custom_margin(tree):
    plan = plan_trip(tree, [Stop("c"), Stop("f")], margin_pct=10.0)
    assert plan.margin_pct == 10.0
    assert plan.total_planned == pytest.approx(27 * 1.10)


def test_plan_trip_zero_margin(tree):
    plan = plan_trip(tree, [Stop("c"), Stop("f")], margin_pct=0.0)
    assert plan.total_planned == plan.total_raw


def test_plan_trip_requires_two_stops(tree):
    with pytest.raises(ValueError, match="at least two"):
        plan_trip(tree, [Stop("c")])


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


# ---------- seed integration: load_dv_graph + chart smoke ----------

def test_load_dv_graph_round_trip(db):
    from ksp_planner.db import load_dv_graph

    g = load_dv_graph(db)
    assert g.node("kerbol_orbit").parent_slug is None
    assert g.node("mun_surface").parent_slug == "mun_low_orbit"
    assert g.node("kerbin_surface").body_slug == "kerbin"
    # both directions seeded for every adjacency
    assert g.edge("kerbin_low_orbit", "kerbin_surface").dv_m_s == 3400
    assert g.edge("kerbin_surface", "kerbin_low_orbit").dv_m_s == 3400


def test_acceptance_kerbin_surface_to_mun_surface(db):
    """Phase 7a acceptance: ksp dv kerbin_surface mun_surface within ±50 m/s of chart (5150)."""
    from ksp_planner.db import load_dv_graph

    g = load_dv_graph(db)
    legs = path_dv(g, "kerbin_surface", "mun_surface")
    total = sum(e.dv_m_s for e in legs)
    assert total == pytest.approx(5150, abs=50)


# ---------- Hohmann cross-check: catches chart typos & orbital-math regressions ----------
#
# Tolerance is loose (30%) because community chart values bake in Oberth bonuses,
# plane-change shortcuts, and (where applicable) aerobrake credit that pure
# circular-coplanar Hohmann doesn't model. A typo (e.g. "10600" instead of
# "1060") or a broken vis-viva would push values 2-10× off and still trip this.
# Eve is excluded — its 80 m/s chart capture reflects aerobrake credit (Hohmann
# insertion ≈ 1400 m/s), checked separately.
INTERPLANETARY_FROM_KERBIN_HOHMANN_OK = ["moho", "duna", "dres", "jool", "eeloo"]


@pytest.mark.parametrize("planet_slug", INTERPLANETARY_FROM_KERBIN_HOHMANN_OK)
def test_seeded_path_within_30pct_of_hohmann(db, planet_slug):
    """LKO → planet LO total within 30% of orbital.interbody_hohmann()."""
    from ksp_planner.db import get_body, load_dv_graph
    from ksp_planner.orbital import interbody_hohmann

    g = load_dv_graph(db)
    kerbin = get_body(db, "kerbin")
    planet = get_body(db, planet_slug)
    kerbol = get_body(db, "kerbol")
    parking_alt = 100_000.0  # 100 km, the chart's implicit parking altitude

    seeded = sum(
        e.dv_m_s for e in path_dv(g, "kerbin_low_orbit", f"{planet_slug}_low_orbit")
    )
    computed = interbody_hohmann(
        mu_parent=kerbol["mu_m3s2"],
        sma_source_m=kerbin["sma_m"],
        sma_target_m=planet["sma_m"],
        mu_source_body=kerbin["mu_m3s2"],
        r_parking_source_m=kerbin["radius_m"] + parking_alt,
        mu_target_body=planet["mu_m3s2"],
        r_parking_target_m=planet["radius_m"] + parking_alt,
    )["dv_total_m_s"]
    assert seeded == pytest.approx(computed, rel=0.30), (
        f"{planet_slug}: seeded={seeded:.0f} vs hohmann={computed:.0f}"
    )


def test_eve_capture_claims_aerobrake_credit(db):
    """Eve's tiny chart capture (~80 m/s) only makes sense with aerobrake."""
    from ksp_planner.db import load_dv_graph

    g = load_dv_graph(db)
    edge = g.edge("eve_capture", "eve_low_orbit")
    assert edge.can_aerobrake, "Eve insertion needs can_aerobrake=True for the chart value"
    assert edge.dv_m_s < 200, f"chart Eve capture ~80 m/s w/ aerobrake, got {edge.dv_m_s}"


# ---------- resolve_stop ----------


@pytest.fixture
def body_tree() -> DvGraph:
    """Minimal body-style fixture: Minmus (full chain) + Kerbol (only _orbit)."""
    nodes = [
        DvNode(slug="kerbol_orbit", parent_slug=None, body_slug="kerbol", state="sun_orbit"),
        DvNode(
            slug="minmus_transfer", parent_slug="kerbol_orbit", body_slug="minmus", state="transfer"
        ),
        DvNode(
            slug="minmus_low_orbit",
            parent_slug="minmus_transfer",
            body_slug="minmus",
            state="low_orbit",
        ),
        DvNode(
            slug="minmus_surface",
            parent_slug="minmus_low_orbit",
            body_slug="minmus",
            state="surface",
        ),
    ]
    return DvGraph(nodes=nodes, edges=[])


def test_resolve_stop_land(body_tree):
    stop = resolve_stop(body_tree, "minmus", "land")
    assert stop == Stop(slug="minmus_surface", action="land")


def test_resolve_stop_orbit(body_tree):
    stop = resolve_stop(body_tree, "minmus", "orbit")
    assert stop == Stop(slug="minmus_low_orbit", action="orbit")


def test_resolve_stop_flyby(body_tree):
    stop = resolve_stop(body_tree, "minmus", "flyby")
    assert stop == Stop(slug="minmus_transfer", action="flyby")


def test_resolve_stop_unknown_action_raises(body_tree):
    with pytest.raises(KeyError, match="unknown action"):
        resolve_stop(body_tree, "minmus", "fly")


def test_resolve_stop_body_missing_state_raises(body_tree):
    """Kerbol has only kerbol_orbit — actions needing kerbol_surface/_low_orbit/_transfer error."""
    with pytest.raises(KeyError, match="kerbol_surface"):
        resolve_stop(body_tree, "kerbol", "land")


def test_resolve_stop_unknown_body_raises(body_tree):
    with pytest.raises(KeyError, match="gorgon"):
        resolve_stop(body_tree, "gorgon", "orbit")


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

    g = load_dv_graph(db)
    stop = resolve_stop(g, body_slug, action)
    assert stop.slug == expected_node
    assert stop.action == action


def test_kerbin_via_minmus_orbit_to_mun_surface_acceptance(db):
    """7b acceptance gate: totals match the chart walk within ±50 m/s of 7,330."""
    from ksp_planner.db import load_dv_graph

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


# ---------- 7c: integration — real-seed aerobrake ----------


def test_kerbin_to_duna_surface_aerobraked_totals(db):
    """kerbin→duna: raw 6,270; aerobraked ≈ 4,822 (duna capture 360→72, duna descent 1450→290)."""
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
    """Eve descent (8000 ballistic) credited at 80% → ~1,600 + small quirk on capture."""
    from ksp_planner.db import load_dv_graph

    g = load_dv_graph(db)
    plan = plan_trip(g, [Stop("kerbin_surface"), Stop("eve_surface")])
    # Outbound: 3400 + 0 + 0 + 0 + 0 + 1080 + 80 + 8000 = 12,560
    # With aerobrake: 3400 + 0 + 0 + 0 + 0 + 1080 + 16 + 1600 = 6,096
    # (eve_capture→eve_low_orbit 80 is already chart-baked; double-credit → 16 residual,
    #  accepted per 7c spec.)
    assert plan.total_raw == pytest.approx(12560, abs=10)
    assert plan.total_aerobraked == pytest.approx(6096, abs=10)
    # savings should be large (> 6000 m/s)
    assert plan.total_raw - plan.total_aerobraked > 6000
