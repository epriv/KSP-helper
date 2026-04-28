"""Phase 8f — /scanning endpoint tests."""

from __future__ import annotations

import pytest


def test_get_scanning_returns_form(client):
    r = client.get("/scanning")
    assert r.status_code == 200
    assert "wb-top" in r.text
    assert "KSP Planner" in r.text
    assert 'name="body"' in r.text
    assert 'name="fov_deg"' in r.text


def test_get_scanning_no_params_shows_empty_state(client):
    r = client.get("/scanning")
    assert r.status_code == 200
    assert "ksp-empty" in r.text
    assert "scanning-results" not in r.text


def test_post_scanning_kerbin_returns_sweet_spots(client):
    r = client.post("/scanning", data={"body": "kerbin", "fov_deg": "5"})
    assert r.status_code == 200
    assert "scanning-results" in r.text
    assert "km" in r.text


def test_post_scanning_bad_body_returns_400(client):
    r = client.post("/scanning", data={"body": "notaplanet", "fov_deg": "5"})
    assert r.status_code == 400
    assert "ksp-flash" in r.text


def test_post_scanning_negative_fov_returns_400(client):
    r = client.post("/scanning", data={"body": "kerbin", "fov_deg": "-1"})
    assert r.status_code == 400
    assert "ksp-flash" in r.text


def test_post_scanning_htmx_returns_partial_no_chrome(client):
    r = client.post(
        "/scanning",
        headers={"HX-Request": "true"},
        data={"body": "kerbin", "fov_deg": "5"},
    )
    assert r.status_code == 200
    assert "<html" not in r.text
    assert "scanning-results" in r.text


def test_post_scanning_json_returns_scanning_response(client):
    r = client.post(
        "/scanning",
        headers={"Accept": "application/json"},
        data={"body": "kerbin", "fov_deg": "5"},
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")
    data = r.json()
    assert data["body_slug"] == "kerbin"
    assert data["fov_deg"] == pytest.approx(5.0)
    assert len(data["sweet_spots"]) > 0
    for spot in data["sweet_spots"]:
        assert spot["altitude_km"] > 0
        assert spot["days_to_coverage"] > 0


def test_get_scanning_shareable_url(client):
    r = client.get("/scanning", params={"body": "kerbin", "fov_deg": 5.0})
    assert r.status_code == 200
    assert "scanning-results" in r.text


def test_scanning_nav_chip_is_active_link(client):
    r = client.get("/scanning")
    assert r.status_code == 200
    assert 'href="/scanning"' in r.text
    assert "is-active" in r.text
