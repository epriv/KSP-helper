"""Phase 8a — smoke tests for the FastAPI app skeleton."""

from __future__ import annotations


def test_health_endpoint_returns_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_app_module_exposes_serve():
    from ksp_planner.web import app as web_app

    assert callable(web_app.serve)
