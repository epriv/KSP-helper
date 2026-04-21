"""Phase 6a — round-trip tests for `plans.py`."""

import time

import pytest

from ksp_planner import plans

COMMS_CFG = {
    "target": "kerbin",
    "sats": 3,
    "antenna": "RA-15 Relay Antenna",
    "dsn_level": 2,
    "min_elev": 5.0,
}

HOHMANN_CFG = {
    "source": "kerbin",
    "target": "duna",
    "from_alt_km": 100.0,
    "to_alt_km": 100.0,
}


def test_save_then_load_roundtrip(writable_db):
    plans.save(writable_db, "my-relay", "comms", COMMS_CFG)
    loaded = plans.load(writable_db, "my-relay")
    assert loaded["name"] == "my-relay"
    assert loaded["kind"] == "comms"
    assert loaded["config"] == COMMS_CFG


def test_save_returns_loaded_row(writable_db):
    returned = plans.save(writable_db, "x", "hohmann", HOHMANN_CFG)
    assert returned["name"] == "x"
    assert returned["kind"] == "hohmann"
    assert returned["config"] == HOHMANN_CFG
    assert "created_at" in returned and "updated_at" in returned


def test_duplicate_name_updates_in_place(writable_db):
    plans.save(writable_db, "dup", "comms", COMMS_CFG)
    new_cfg = {**COMMS_CFG, "sats": 5}
    plans.save(writable_db, "dup", "comms", new_cfg)

    all_plans = plans.list_all(writable_db)
    assert len([p for p in all_plans if p["name"] == "dup"]) == 1
    assert plans.load(writable_db, "dup")["config"]["sats"] == 5


def test_update_preserves_created_at_and_advances_updated_at(writable_db):
    first = plans.save(writable_db, "t", "comms", COMMS_CFG)
    # Timestamps are ISO-second resolution; sleep just over a second so
    # updated_at is guaranteed to differ.
    time.sleep(1.1)
    second = plans.save(writable_db, "t", "comms", {**COMMS_CFG, "sats": 4})

    assert second["created_at"] == first["created_at"]
    assert second["updated_at"] > first["updated_at"]


def test_kind_can_change_on_update(writable_db):
    """Updating a plan should overwrite kind too, not just config."""
    plans.save(writable_db, "shape-shifter", "comms", COMMS_CFG)
    plans.save(writable_db, "shape-shifter", "hohmann", HOHMANN_CFG)
    loaded = plans.load(writable_db, "shape-shifter")
    assert loaded["kind"] == "hohmann"
    assert loaded["config"] == HOHMANN_CFG


def test_delete_returns_true_when_removed(writable_db):
    plans.save(writable_db, "doomed", "comms", COMMS_CFG)
    assert plans.delete(writable_db, "doomed") is True
    with pytest.raises(KeyError):
        plans.load(writable_db, "doomed")


def test_delete_returns_false_for_unknown_name(writable_db):
    assert plans.delete(writable_db, "never-existed") is False


def test_load_unknown_name_raises_keyerror(writable_db):
    with pytest.raises(KeyError, match="never-existed"):
        plans.load(writable_db, "never-existed")


def test_save_rejects_invalid_kind(writable_db):
    with pytest.raises(ValueError, match="unknown plan kind"):
        plans.save(writable_db, "bad", "not-a-kind", {})


def test_save_rejects_empty_name(writable_db):
    with pytest.raises(ValueError, match="name must not be empty"):
        plans.save(writable_db, "   ", "comms", COMMS_CFG)


def test_list_all_empty_on_fresh_db(writable_db):
    assert plans.list_all(writable_db) == []


def test_list_all_returns_plans_sorted_by_name(writable_db):
    plans.save(writable_db, "charlie", "comms", COMMS_CFG)
    plans.save(writable_db, "alpha", "hohmann", HOHMANN_CFG)
    plans.save(writable_db, "bravo", "comms", COMMS_CFG)

    names = [p["name"] for p in plans.list_all(writable_db)]
    assert names == ["alpha", "bravo", "charlie"]


def test_list_all_entries_include_parsed_config(writable_db):
    plans.save(writable_db, "p", "comms", COMMS_CFG)
    entry = plans.list_all(writable_db)[0]
    assert entry["config"] == COMMS_CFG
    assert entry["kind"] == "comms"
