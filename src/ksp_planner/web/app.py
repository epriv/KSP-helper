"""FastAPI application factory and uvicorn entry-point."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

_HERE = Path(__file__).parent
_STATIC = _HERE / "static"

app = FastAPI(title="KSP Planner", version="0.8.0a")
app.mount("/static", StaticFiles(directory=_STATIC), name="static")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def serve() -> None:
    """Console-script entry: runs uvicorn with env-var overrides."""
    import uvicorn

    uvicorn.run(
        "ksp_planner.web.app:app",
        host=os.environ.get("KSP_HOST", "127.0.0.1"),
        port=int(os.environ.get("KSP_PORT", "8080")),
        reload=os.environ.get("KSP_RELOAD", "0") == "1",
    )
