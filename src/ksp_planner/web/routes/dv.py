"""Routes for the Δv planner page (Phase 8a)."""

from __future__ import annotations

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Query, Request

from ksp_planner.db import load_dv_graph
from ksp_planner.dv_map import Stop, plan_round_trip, plan_trip, resolve_stop
from ksp_planner.web.deps import get_db
from ksp_planner.web.schemas import DvRequest, DvResponse, StopInput, equivalent_cli

router = APIRouter()

# Bodies available in the dv graph, ordered and grouped for the picker.
DV_BODIES = [
    {"slug": "kerbol", "name": "Kerbol Orbit", "system": "sun"},
    {"slug": "moho",   "name": "Moho",   "system": "inner"},
    {"slug": "eve",    "name": "Eve",     "system": "inner"},
    {"slug": "gilly",  "name": "Gilly",   "system": "inner"},
    {"slug": "kerbin", "name": "Kerbin",  "system": "home"},
    {"slug": "mun",    "name": "Mun",     "system": "home"},
    {"slug": "minmus", "name": "Minmus",  "system": "home"},
    {"slug": "duna",   "name": "Duna",    "system": "outer"},
    {"slug": "ike",    "name": "Ike",     "system": "outer"},
    {"slug": "dres",   "name": "Dres",    "system": "outer"},
    {"slug": "jool",   "name": "Jool",    "system": "jool"},
    {"slug": "laythe", "name": "Laythe",  "system": "jool"},
    {"slug": "vall",   "name": "Vall",    "system": "jool"},
    {"slug": "tylo",   "name": "Tylo",    "system": "jool"},
    {"slug": "bop",    "name": "Bop",     "system": "jool"},
    {"slug": "pol",    "name": "Pol",     "system": "jool"},
    {"slug": "eeloo",  "name": "Eeloo",   "system": "far"},
]


def _ctx(**extra) -> dict:
    """Base template context for every /dv response."""
    return {
        "active_nav": "dv",
        "version": "0.8.0a",
        "bodies": DV_BODIES,
        **extra,
    }


class _FormState:
    """Simple namespace for re-populating the form after a POST."""

    def __init__(
        self,
        from_body: str,
        from_action: str,
        to_body: str,
        to_action: str,
        via: list[StopInput],
        round_trip: bool,
        aerobrake: bool,
        margin_pct: float,
    ) -> None:
        self.from_body = from_body
        self.from_action = from_action
        self.to_body = to_body
        self.to_action = to_action
        self.via = via
        self.round_trip = round_trip
        self.aerobrake = aerobrake
        self.margin_pct = margin_pct


def _subway_rows(conn: sqlite3.Connection) -> list[dict]:
    """Build subway-map data for the reference sidebar."""
    graph = load_dv_graph(conn)
    node_slugs = set(graph._nodes.keys())

    systems = [
        ("Inner",  ["moho", "eve", "gilly"]),
        ("Home",   ["kerbin", "mun", "minmus"]),
        ("Outer",  ["duna", "ike", "dres"]),
        ("Jool",   ["jool", "laythe", "vall", "tylo", "bop", "pol"]),
        ("Far",    ["eeloo"]),
    ]
    states = ["transfer", "capture", "low_orbit", "surface"]
    label_abbrev = {
        "moho": "Mo", "eve": "Ev", "gilly": "Gi",
        "kerbin": "Ke", "mun": "Mu", "minmus": "Mi",
        "duna": "Du", "ike": "Ik", "dres": "Dr",
        "jool": "Jo", "laythe": "La", "vall": "Va",
        "tylo": "Ty", "bop": "Bo", "pol": "Po",
        "eeloo": "El",
    }

    rows = []
    for sys_name, bodies in systems:
        cells = []
        for state in states:
            cell_nodes = []
            for body in bodies:
                slug = f"{body}_{state}"
                if slug in node_slugs:
                    abbrev = label_abbrev.get(body, body[:2].title())
                    cell_nodes.append({"slug": slug, "label": abbrev})
            cells.append(cell_nodes)
        rows.append({"system": sys_name, "cells": cells})
    return rows


@router.get("/dv")
def get_dv(
    request: Request,
    from_body: Annotated[str | None, Query()] = None,
    from_action: Annotated[str, Query()] = "land",
    to_body: Annotated[str | None, Query()] = None,
    to_action: Annotated[str, Query()] = "land",
    round_trip: Annotated[bool, Query()] = False,
    aerobrake: Annotated[bool, Query()] = True,
    margin_pct: Annotated[float, Query(ge=0, le=100)] = 5.0,
    via_body: Annotated[list[str] | None, Query()] = None,
    via_action: Annotated[list[str] | None, Query()] = None,
    conn: sqlite3.Connection = Depends(get_db),  # noqa: B008
):
    from ksp_planner.web.app import templates

    form_state = None
    response = None
    error = None

    if from_body and to_body:
        try:
            graph = load_dv_graph(conn)
            from_stop = resolve_stop(graph, from_body, from_action)
            to_stop = resolve_stop(graph, to_body, to_action)
            via = [
                StopInput(body=b, action=a)
                for b, a in zip(via_body or [], via_action or [], strict=False)
            ]
            req = DvRequest(
                **{"from": from_stop.slug},
                to=to_stop.slug,
                via=via,
                round_trip=round_trip,
                aerobrake=aerobrake,
                margin_pct=margin_pct,
            )
            stops: list[Stop] = [Stop(req.from_)]
            for v in req.via:
                stops.append(resolve_stop(graph, v.body, v.action))
            stops.append(Stop(req.to))
            planner = plan_round_trip if req.round_trip else plan_trip
            trip = planner(graph, stops, margin_pct=req.margin_pct, aerobrake=req.aerobrake)
            response = DvResponse.from_trip(trip, req, equivalent_cli(req))

            form_state = _FormState(
                from_body=from_body,
                from_action=from_action,
                to_body=to_body,
                to_action=to_action,
                via=via,
                round_trip=round_trip,
                aerobrake=aerobrake,
                margin_pct=margin_pct,
            )
        except (KeyError, ValueError) as e:
            error = str(e).strip("\"'")

    return templates.TemplateResponse(
        request,
        "pages/dv.html",
        _ctx(form=form_state, response=response, error=error, subway_rows=_subway_rows(conn)),
    )


@router.get("/dv/stop-row")
def get_stop_row(request: Request):
    from ksp_planner.web.app import templates

    return templates.TemplateResponse(
        request,
        "partials/stop_row.html",
        _ctx(form=None, response=None, error=None),
    )


@router.post("/dv")
def post_dv(
    request: Request,
    from_body: Annotated[str, Form()],
    from_action: Annotated[str, Form()],
    to_body: Annotated[str, Form()],
    to_action: Annotated[str, Form()],
    round_trip: Annotated[bool, Form()] = False,
    aerobrake: Annotated[bool, Form()] = False,
    margin_pct: Annotated[float, Form()] = 5.0,
    via_body: Annotated[list[str] | None, Form()] = None,
    via_action: Annotated[list[str] | None, Form()] = None,
    conn: sqlite3.Connection = Depends(get_db),  # noqa: B008
):
    from pydantic import ValidationError

    from ksp_planner.web.app import templates

    req = None
    response = None
    error = None
    status = 200

    try:
        graph = load_dv_graph(conn)
        from_stop = resolve_stop(graph, from_body, from_action)
        to_stop = resolve_stop(graph, to_body, to_action)
        via = [
            StopInput(body=b, action=a)
            for b, a in zip(via_body or [], via_action or [], strict=True)
        ]
        req = DvRequest(
            **{"from": from_stop.slug},
            to=to_stop.slug,
            via=via,
            round_trip=round_trip,
            aerobrake=aerobrake,
            margin_pct=margin_pct,
        )
        stops: list[Stop] = [Stop(req.from_)]
        for v in req.via:
            stops.append(resolve_stop(graph, v.body, v.action))
        stops.append(Stop(req.to))
        planner = plan_round_trip if req.round_trip else plan_trip
        trip = planner(graph, stops, margin_pct=req.margin_pct, aerobrake=req.aerobrake)
        response = DvResponse.from_trip(trip, req, equivalent_cli(req))
    except ValidationError as e:
        first = e.errors()[0]
        error = f"{'.'.join(str(p) for p in first['loc'])}: {first['msg']}"
        status = 400
    except (KeyError, ValueError) as e:
        error = str(e).strip("\"'")
        status = 400

    form_state = _FormState(
        from_body=from_body,
        from_action=from_action,
        to_body=to_body,
        to_action=to_action,
        via=[
            StopInput(body=b, action=a)
            for b, a in zip(via_body or [], via_action or [], strict=False)
        ],
        round_trip=round_trip,
        aerobrake=aerobrake,
        margin_pct=margin_pct,
    )

    accept = request.headers.get("accept", "")
    wants_json = "application/json" in accept and "text/html" not in accept

    if wants_json:
        if error:
            from fastapi.responses import JSONResponse

            return JSONResponse({"error": error}, status_code=status)
        return response

    is_hx = request.headers.get("hx-request") == "true"
    if is_hx and error:
        template = "partials/error_flash.html"
    elif is_hx and response:
        template = "partials/dv_result.html"
    else:
        template = "pages/dv.html"

    return templates.TemplateResponse(
        request,
        template,
        _ctx(form=form_state, response=response, error=error, subway_rows=_subway_rows(conn)),
        status_code=status,
    )
