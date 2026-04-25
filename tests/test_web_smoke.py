"""Phase 8a — smoke tests for the FastAPI app skeleton."""

from __future__ import annotations


def test_health_endpoint_returns_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_app_module_exposes_serve():
    from ksp_planner.web import app as web_app

    assert callable(web_app.serve)


def test_static_htmx_is_served(client):
    r = client.get("/static/js/htmx.min.js")
    assert r.status_code == 200
    assert "javascript" in r.headers["content-type"]
    assert b"htmx" in r.content


def test_static_theme_css_has_design_tokens(client):
    r = client.get("/static/css/theme.css")
    assert r.status_code == 200
    assert "text/css" in r.headers["content-type"]
    assert "--bg" in r.text
    assert "--accent" in r.text


def test_static_components_css_loaded(client):
    r = client.get("/static/css/components.css")
    assert r.status_code == 200
