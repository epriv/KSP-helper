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
