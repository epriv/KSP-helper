"""FastAPI application factory and uvicorn entry-point."""

from __future__ import annotations

import os

from fastapi import FastAPI

app = FastAPI(title="KSP Planner", version="0.8.0a")


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
