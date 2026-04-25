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


def test_root_redirects_to_dv(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code in (302, 307)
    assert r.headers["location"] == "/dv"


def test_serve_reads_env_vars(monkeypatch):
    """serve() forwards KSP_HOST / KSP_PORT / KSP_RELOAD to uvicorn."""
    captured: dict = {}

    def fake_run(target, **kwargs):
        captured["target"] = target
        captured.update(kwargs)

    import uvicorn
    monkeypatch.setattr(uvicorn, "run", fake_run)
    monkeypatch.setenv("KSP_HOST", "0.0.0.0")
    monkeypatch.setenv("KSP_PORT", "9090")
    monkeypatch.setenv("KSP_RELOAD", "1")

    from ksp_planner.web.app import serve
    serve()

    assert captured["target"] == "ksp_planner.web.app:app"
    assert captured["host"] == "0.0.0.0"
    assert captured["port"] == 9090
    assert captured["reload"] is True
