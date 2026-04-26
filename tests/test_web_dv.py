"""Phase 8a — /dv endpoint suite."""

from __future__ import annotations

import pytest


def test_get_dv_returns_workbench_form(client):
    r = client.get("/dv")
    assert r.status_code == 200
    # Workbench shell
    assert "wb-top" in r.text
    assert "KSP Planner" in r.text
    # Form elements
    assert 'name="from_body"' in r.text
    assert 'name="from_action"' in r.text
    assert 'name="to_body"' in r.text
    assert 'name="to_action"' in r.text
    assert 'name="aerobrake"' in r.text
    assert 'name="round_trip"' in r.text
    assert 'name="margin_pct"' in r.text
    # No result yet
    assert "ksp-totals" not in r.text


def test_get_dv_body_select_has_kerbin(client):
    r = client.get("/dv")
    assert "Kerbin" in r.text
    assert "Mun" in r.text
    assert "Minmus" in r.text


def test_post_dv_kerbin_to_mun_round_trip_canonical_numbers(client):
    r = client.post(
        "/dv",
        data={
            "from_body": "kerbin", "from_action": "land",
            "to_body": "mun",     "to_action": "land",
            "round_trip": "on", "aerobrake": "on", "margin_pct": "5",
        },
    )
    assert r.status_code == 200
    body = r.text
    assert "ksp-totals" in body       # result rendered
    assert "ksp-legs" in body         # leg table rendered
    assert "10,300" in body           # raw total
    assert "6,900" in body            # aerobraked total
    assert "7,245" in body            # planned total (aerobraked + 5%)
    assert "uv run ksp dv" in body    # CLI hint


def test_post_dv_htmx_returns_partial_no_chrome(client):
    r = client.post(
        "/dv",
        headers={"HX-Request": "true"},
        data={
            "from_body": "kerbin", "from_action": "land",
            "to_body": "mun",     "to_action": "land",
            "aerobrake": "on", "margin_pct": "5",
        },
    )
    assert r.status_code == 200
    assert "ksp-totals" in r.text
    assert "<html" not in r.text
    assert "<form" not in r.text


def test_post_dv_json_accept_returns_dvresponse(client):
    r = client.post(
        "/dv",
        headers={"Accept": "application/json"},
        data={
            "from_body": "kerbin", "from_action": "land",
            "to_body": "mun",     "to_action": "land",
            "round_trip": "on", "aerobrake": "on", "margin_pct": "5",
        },
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")
    body = r.json()
    assert body["from_slug"] == "kerbin_surface"
    assert body["to_slug"] == "mun_surface"
    assert body["round_trip"] is True
    assert body["total_raw"] == pytest.approx(10_300, abs=1)
    assert body["total_aerobraked"] == pytest.approx(6_900, abs=1)
    assert body["total_aerobraked_planned"] == pytest.approx(7_245, abs=1)
    assert len(body["legs"]) == 8


def test_get_dv_stop_row_partial(client):
    r = client.get("/dv/stop-row")
    assert r.status_code == 200
    assert 'name="via_body"' in r.text
    assert 'name="via_action"' in r.text
    assert "Kerbin" in r.text
    assert "<html" not in r.text


def test_get_dv_stop_row_partial_has_reorder_buttons(client):
    r = client.get("/dv/stop-row")
    assert r.status_code == 200
    assert "↑" in r.text
    assert "↓" in r.text
    assert "moveStopUp" in r.text
    assert "moveStopDown" in r.text
    assert 'name="via_body"' in r.text
    assert 'name="via_action"' in r.text


def test_post_dv_unknown_body_returns_400_flash(client):
    r = client.post(
        "/dv",
        data={"from_body": "notaplanet", "from_action": "land",
              "to_body": "mun", "to_action": "land", "margin_pct": "5"},
    )
    assert r.status_code == 400
    assert "ksp-flash" in r.text
    assert "<form" in r.text


def test_post_dv_negative_margin_returns_400(client):
    r = client.post(
        "/dv",
        data={"from_body": "kerbin", "from_action": "land",
              "to_body": "mun", "to_action": "land", "margin_pct": "-5"},
    )
    assert r.status_code == 400
    assert "ksp-flash" in r.text


def test_get_dv_querystring_computes_canonical_numbers(client):
    r = client.get(
        "/dv",
        params={
            "from_body": "kerbin", "from_action": "land",
            "to_body": "mun",     "to_action": "land",
            "round_trip": "1", "aerobrake": "1", "margin_pct": "5",
        },
    )
    assert r.status_code == 200
    body = r.text
    assert "ksp-totals" in body      # result rendered
    assert "10,300" in body          # raw total
    assert "7,245" in body           # planned total
    assert "<form" in body           # form still present
    assert 'value="kerbin"' in body  # form prepopulated (selected)


def test_get_dv_no_params_shows_empty_state(client):
    r = client.get("/dv")
    assert r.status_code == 200
    assert "ksp-empty" in r.text
    assert "ksp-totals" not in r.text


def test_get_dv_has_itinerary_list_with_js(client):
    r = client.get("/dv")
    assert r.status_code == 200
    assert "itinerary-list" in r.text
    assert "moveStopUp" in r.text
    assert "moveStopDown" in r.text
    # origin and destination are still present as named form fields
    assert 'name="from_body"' in r.text
    assert 'name="to_body"' in r.text
    # HTMX "add stop" inserts before #to-row
    assert 'hx-target="#to-row"' in r.text
    assert 'hx-swap="beforebegin"' in r.text
