"""Phase 8b — smoke + integration tests for the /comms page."""

from __future__ import annotations

import pytest


def test_get_comms_empty_state(client):
    r = client.get("/comms")
    assert r.status_code == 200
    assert "Constellation" in r.text
    assert "Calculate" in r.text
    # no result rendered yet
    assert "Coverage" not in r.text


def test_comms_nav_chip_active(client):
    r = client.get("/comms")
    assert r.status_code == 200
    # base.html renders the chip as a real link when on /comms
    assert 'href="/comms"' in r.text


def test_comms_sidebar_loaded(client):
    r = client.get("/comms")
    assert r.status_code == 200
    assert "RA-15 Relay Antenna" in r.text
    assert "DSN Levels" in r.text


def test_post_comms_canonical_result(client):
    """Kerbin 3-sat RA-15 DSN-2 → canonical coverage result from the integration test."""
    r = client.post("/comms", data={
        "body": "kerbin",
        "antenna": "RA-15 Relay Antenna",
        "n_sats": "3",
        "dsn_level": "2",
        "min_elev_deg": "5",
    })
    assert r.status_code == 200
    assert "Coverage OK" in r.text
    assert "814" in r.text          # orbit altitude km
    assert "479" in r.text          # resonant altitude km
    assert "2/3" in r.text          # resonant ratio


def test_post_comms_bad_body(client):
    r = client.post("/comms", data={
        "body": "notaplanet",
        "antenna": "RA-15 Relay Antenna",
        "n_sats": "3",
        "dsn_level": "2",
        "min_elev_deg": "5",
    })
    assert r.status_code == 400


def test_post_comms_geometry_impossible(client):
    # N=2, min_elev=45°: cos(π/2 + π/4) < 0 → ValueError from orbit_for_coverage
    r = client.post("/comms", data={
        "body": "kerbin",
        "antenna": "RA-15 Relay Antenna",
        "n_sats": "2",
        "dsn_level": "2",
        "min_elev_deg": "45",
    })
    assert r.status_code == 400
    assert "geometrically impossible" in r.text or "unbounded" in r.text
