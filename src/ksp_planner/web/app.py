"""FastAPI application factory and uvicorn entry-point."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

_HERE = Path(__file__).parent
_STATIC = _HERE / "static"
_TEMPLATES = _HERE / "templates"

VERSION = "0.8.0a"

app = FastAPI(title="KSP Planner", version=VERSION)
app.mount("/static", StaticFiles(directory=_STATIC), name="static")

templates = Jinja2Templates(directory=_TEMPLATES)

from ksp_planner.web.routes import dv as dv_routes  # noqa: E402

app.include_router(dv_routes.router)

from ksp_planner.web.routes import comms as comms_routes  # noqa: E402

app.include_router(comms_routes.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/")
def root() -> RedirectResponse:
    return RedirectResponse(url="/dv")


def serve() -> None:
    """Console-script entry: runs uvicorn with env-var overrides."""
    import uvicorn

    uvicorn.run(
        "ksp_planner.web.app:app",
        host=os.environ.get("KSP_HOST", "127.0.0.1"),
        port=int(os.environ.get("KSP_PORT", "8080")),
        reload=os.environ.get("KSP_RELOAD", "0") == "1",
    )
