"""Routes for the comm network planner page (Phase 8b)."""

from __future__ import annotations

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Query, Request

from ksp_planner import db as dblib
from ksp_planner.comms import comm_network_report, resonant_deploy
from ksp_planner.web.deps import get_db
from ksp_planner.web.schemas import CommsRequest, CommsResponse

router = APIRouter()

COMMS_BODIES = [
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
    return {"active_nav": "comms", "version": "0.8.0b", "bodies": COMMS_BODIES, **extra}


def _sidebar_data(conn: sqlite3.Connection) -> dict:
    antennas = [
        dict(r)
        for r in conn.execute("SELECT name, range_m FROM antennas ORDER BY range_m")
    ]
    dsn_levels = [
        dict(r)
        for r in conn.execute("SELECT level, range_m FROM dsn_levels ORDER BY level")
    ]
    return {"antennas": antennas, "dsn_levels": dsn_levels}


def _antenna_options(conn: sqlite3.Connection) -> list[dict]:
    return [
        dict(r) for r in conn.execute("SELECT name FROM antennas ORDER BY range_m")
    ]


def _compute(
    conn: sqlite3.Connection,
    body_slug: str,
    n_sats: int,
    antenna_name: str,
    dsn_level: int,
    min_elev_deg: float,
) -> CommsResponse:
    body = dblib.get_body(conn, body_slug)
    antenna = dblib.get_antenna(conn, antenna_name)
    dsn = dblib.get_dsn(conn, dsn_level)
    report = comm_network_report(body, n_sats, antenna, dsn, min_elev_deg)
    resonant = resonant_deploy(report["orbit_radius_m"], n_sats, body["mu_m3s2"])
    equiv = (
        f'uv run ksp comms {body_slug} --sats {n_sats}'
        f' --antenna "{antenna_name}" --dsn {dsn_level}'
        + (f" --min-elev {min_elev_deg:g}" if min_elev_deg != 5.0 else "")
    )
    return CommsResponse.from_report(report, resonant, body["radius_m"], equiv)


@router.get("/comms")
def get_comms(
    request: Request,
    body: Annotated[str | None, Query()] = None,
    n_sats: Annotated[int, Query(ge=2)] = 3,
    antenna: Annotated[str | None, Query()] = None,
    dsn_level: Annotated[int, Query(ge=1, le=3)] = 2,
    min_elev_deg: Annotated[float, Query(ge=0, lt=90)] = 5.0,
    conn: sqlite3.Connection = Depends(get_db),  # noqa: B008
):
    from ksp_planner.web.app import templates

    sidebar = _sidebar_data(conn)
    antenna_options = _antenna_options(conn)
    response = None
    error = None
    form = None

    if body and antenna:
        try:
            response = _compute(conn, body, n_sats, antenna, dsn_level, min_elev_deg)
            form = {
                "body": body, "n_sats": n_sats, "antenna": antenna,
                "dsn_level": dsn_level, "min_elev_deg": min_elev_deg,
            }
        except (KeyError, ValueError) as e:
            error = str(e).strip("\"'")

    return templates.TemplateResponse(
        request,
        "pages/comms.html",
        _ctx(response=response, error=error, form=form,
             antenna_options=antenna_options, **sidebar),
    )


@router.post("/comms")
def post_comms(
    request: Request,
    body: Annotated[str, Form()],
    antenna: Annotated[str, Form()],
    n_sats: Annotated[int, Form()] = 3,
    dsn_level: Annotated[int, Form()] = 2,
    min_elev_deg: Annotated[float, Form()] = 5.0,
    conn: sqlite3.Connection = Depends(get_db),  # noqa: B008
):
    from pydantic import ValidationError

    from ksp_planner.web.app import templates

    response = None
    error = None
    status = 200
    sidebar = _sidebar_data(conn)
    antenna_options = _antenna_options(conn)
    form = {
        "body": body, "n_sats": n_sats, "antenna": antenna,
        "dsn_level": dsn_level, "min_elev_deg": min_elev_deg,
    }

    try:
        CommsRequest(body=body, n_sats=n_sats, antenna=antenna,
                     dsn_level=dsn_level, min_elev_deg=min_elev_deg)
        response = _compute(conn, body, n_sats, antenna, dsn_level, min_elev_deg)
    except ValidationError as e:
        first = e.errors()[0]
        error = f"{'.'.join(str(p) for p in first['loc'])}: {first['msg']}"
        status = 400
    except (KeyError, ValueError) as e:
        error = str(e).strip("\"'")
        status = 400

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
        template = "partials/comms_result.html"
    else:
        template = "pages/comms.html"

    return templates.TemplateResponse(
        request,
        template,
        _ctx(response=response, error=error, form=form,
             antenna_options=antenna_options, **sidebar),
        status_code=status,
    )
