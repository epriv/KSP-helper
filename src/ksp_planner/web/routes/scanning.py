"""Routes for the polar scanning orbit optimizer (Phase 8f)."""

from __future__ import annotations

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Query, Request

from ksp_planner import db as dblib
from ksp_planner.scanning import find_sweet_spots
from ksp_planner.web.deps import get_db
from ksp_planner.web.schemas import ScanningRequest, ScanningResponse, SweetSpotOut

router = APIRouter()

FOV_PRESETS = [
    {"name": "Low-Res SAR",     "fov_deg": 5.0},
    {"name": "Hi-Res Multi",    "fov_deg": 2.0},
    {"name": "Biome / Anomaly", "fov_deg": 3.0},
]

SCANNING_BODIES = [
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
    return {
        "active_nav": "scanning",
        "version": "0.8.0b",
        "bodies": SCANNING_BODIES,
        "fov_presets": FOV_PRESETS,
        **extra,
    }


def _compute(
    conn: sqlite3.Connection,
    body_slug: str,
    fov_deg: float,
    min_alt_km: float | None,
    max_alt_km: float | None,
) -> ScanningResponse:
    body = dblib.get_body(conn, body_slug)

    T_rot = body.get("sidereal_day_s")
    if not T_rot:
        raise ValueError(f"{body['name']!r} has no rotation period — scanning not applicable")

    radius_m = body["radius_m"]
    mu = body["mu_m3s2"]
    atm_m = body.get("atm_height_m") or 0.0
    soi_m = body.get("soi_m")

    min_alt_m = (
        max(1_000.0, atm_m + 10_000.0) if min_alt_km is None else min_alt_km * 1_000.0
    )

    if max_alt_km is None:
        cap_m = (soi_m - radius_m) if soi_m else 2_500_000.0
        max_alt_m = min(cap_m, 2_500_000.0)
    else:
        max_alt_m = max_alt_km * 1_000.0

    spots = find_sweet_spots(
        body_radius_m=radius_m,
        mu_m3s2=mu,
        rotation_period_s=T_rot,
        fov_deg=fov_deg,
        min_alt_m=min_alt_m,
        max_alt_m=max_alt_m,
    )

    return ScanningResponse(
        body_slug=body_slug,
        body_name=body["name"],
        fov_deg=fov_deg,
        min_alt_km=min_alt_m / 1_000.0,
        max_alt_km=max_alt_m / 1_000.0,
        sweet_spots=[
            SweetSpotOut(
                altitude_km=s.altitude_km,
                period_s=s.period_s,
                swath_km=s.swath_km,
                shift_km=s.shift_km,
                orbits_per_day=s.orbits_per_day,
                days_to_coverage=s.days_to_coverage,
            )
            for s in spots
        ],
    )


@router.get("/scanning")
def get_scanning(
    request: Request,
    body: Annotated[str | None, Query()] = None,
    fov_deg: Annotated[float, Query(gt=0, le=90)] = 5.0,
    min_alt_km: Annotated[float | None, Query(ge=0)] = None,
    max_alt_km: Annotated[float | None, Query(ge=0)] = None,
    conn: sqlite3.Connection = Depends(get_db),  # noqa: B008
):
    from ksp_planner.web.app import templates

    response = None
    error = None
    form = None

    if body:
        try:
            response = _compute(conn, body, fov_deg, min_alt_km, max_alt_km)
            form = {"body": body, "fov_deg": fov_deg}
        except (KeyError, ValueError) as e:
            error = str(e).strip("\"'")

    return templates.TemplateResponse(
        request,
        "pages/scanning.html",
        _ctx(response=response, error=error, form=form),
    )


@router.post("/scanning")
def post_scanning(
    request: Request,
    body: Annotated[str, Form()],
    fov_deg: Annotated[float, Form()] = 5.0,
    min_alt_km: Annotated[float | None, Form()] = None,
    max_alt_km: Annotated[float | None, Form()] = None,
    conn: sqlite3.Connection = Depends(get_db),  # noqa: B008
):
    from pydantic import ValidationError

    from ksp_planner.web.app import templates

    response = None
    error = None
    status = 200
    form = {"body": body, "fov_deg": fov_deg}

    try:
        ScanningRequest(body=body, fov_deg=fov_deg)
        response = _compute(conn, body, fov_deg, min_alt_km, max_alt_km)
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
        template = "partials/scanning_result.html"
    else:
        template = "pages/scanning.html"

    return templates.TemplateResponse(
        request,
        template,
        _ctx(response=response, error=error, form=form),
        status_code=status,
    )
