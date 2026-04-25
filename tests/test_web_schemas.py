"""Phase 8a — Pydantic schema tests (request/response + equivalent_cli)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ksp_planner.dv_map import Stop, plan_trip
from ksp_planner.web.schemas import (
    DvRequest,
    DvResponse,
    StopInput,
    equivalent_cli,
)


def test_dv_request_minimal_validates():
    req = DvRequest(from_="kerbin_surface", to="mun_surface")
    assert req.from_ == "kerbin_surface"
    assert req.to == "mun_surface"
    assert req.via == []
    assert req.round_trip is False
    assert req.aerobrake is True
    assert req.margin_pct == 5.0


def test_dv_request_rejects_negative_margin():
    with pytest.raises(ValidationError):
        DvRequest(from_="a", to="b", margin_pct=-1)


def test_dv_request_rejects_margin_above_100():
    with pytest.raises(ValidationError):
        DvRequest(from_="a", to="b", margin_pct=101)


def test_dv_request_with_via_stops():
    req = DvRequest(
        from_="kerbin_surface",
        to="mun_surface",
        via=[StopInput(body="minmus", action="orbit")],
    )
    assert len(req.via) == 1
    assert req.via[0].action == "orbit"


def test_stop_input_rejects_unknown_action():
    with pytest.raises(ValidationError):
        StopInput(body="minmus", action="loiter")


def test_equivalent_cli_basic():
    req = DvRequest(from_="kerbin_surface", to="mun_surface")
    assert equivalent_cli(req) == "uv run ksp dv kerbin_surface mun_surface"


def test_equivalent_cli_with_return_and_aerobrake_off():
    req = DvRequest(
        from_="kerbin_surface", to="mun_surface", round_trip=True, aerobrake=False
    )
    assert equivalent_cli(req) == (
        "uv run ksp dv kerbin_surface mun_surface --return --no-aerobrake"
    )


def test_equivalent_cli_with_via_and_margin():
    req = DvRequest(
        from_="kerbin_surface",
        to="mun_surface",
        via=[StopInput(body="minmus", action="orbit")],
        margin_pct=10,
    )
    assert equivalent_cli(req) == (
        "uv run ksp dv kerbin_surface mun_surface --via minmus:orbit --margin 10"
    )


def test_equivalent_cli_default_action_omitted():
    """`--via minmus` (no action) is equivalent to `--via minmus:orbit` since orbit is default."""
    req = DvRequest(
        from_="kerbin_surface",
        to="mun_surface",
        via=[StopInput(body="minmus", action="orbit")],
    )
    cli = equivalent_cli(req)
    # Either form is acceptable — we assert the explicit form here.
    assert "--via minmus:orbit" in cli


def test_dv_response_from_trip_shape(db):
    """Round-trip: build a small trip, snap to DvResponse, verify fields."""
    from ksp_planner import db as dblib  # noqa: F401  (suppress unused if linter complains)
    from ksp_planner.db import load_dv_graph

    graph = load_dv_graph(db)
    trip = plan_trip(graph, [Stop("kerbin_surface"), Stop("mun_surface")])

    req = DvRequest(from_="kerbin_surface", to="mun_surface")
    resp = DvResponse.from_trip(trip, req, equivalent_cli(req))

    assert resp.from_slug == "kerbin_surface"
    assert resp.to_slug == "mun_surface"
    assert resp.round_trip is False
    assert resp.aerobrake is True
    assert resp.margin_pct == 5.0
    assert resp.total_raw == pytest.approx(5150, abs=1)
    assert len(resp.legs) == 4  # outbound only
    assert resp.legs[0].from_slug == "kerbin_surface"
    assert resp.legs[-1].to_slug == "mun_surface"
    assert resp.equivalent_cli == "uv run ksp dv kerbin_surface mun_surface"
