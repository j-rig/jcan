from jcan.history_db import HistoryDB


def _db():
    return HistoryDB(":memory:")


def test_record_active_codes_inserts_new():
    db = _db()
    db.record_active_codes(["P0301"], vin="VIN123")
    events = db.active_events()
    assert len(events) == 1
    assert events[0]["code"] == "P0301"
    assert events[0]["vin"] == "VIN123"
    assert events[0]["cleared_at"] is None
    assert events[0]["notes"] == ""


def test_record_active_codes_does_not_duplicate():
    db = _db()
    db.record_active_codes(["P0301"], vin="VIN123")
    db.record_active_codes(["P0301"], vin="VIN123")
    assert len(db.active_events()) == 1


def test_record_active_codes_dedupes_within_same_call():
    db = _db()
    db.record_active_codes(["P0301", "P0301"], vin="VIN123")
    assert len(db.active_events()) == 1


def test_clear_active_events_stamps_cleared_at():
    db = _db()
    db.record_active_codes(["P0301"], vin="VIN123")
    db.clear_active_events()
    assert db.active_events() == []


def test_set_notes_updates_existing_event():
    db = _db()
    db.record_active_codes(["P0301"], vin="VIN123")
    event_id = db.active_events()[0]["id"]
    assert db.set_notes(event_id, "replaced spark plug") is True
    assert db.active_events()[0]["notes"] == "replaced spark plug"


def test_set_notes_returns_false_for_missing_event():
    db = _db()
    assert db.set_notes(999, "x") is False


def test_vehicles_view_lists_undecoded_vin():
    db = _db()
    db.record_active_codes(["P0301"], vin="VIN123")
    rows = db.vehicles_view()
    assert len(rows) == 1
    assert rows[0]["vin"] == "VIN123"
    assert rows[0]["make"] is None


def test_upsert_vehicle_then_view_shows_decoded_info():
    db = _db()
    db.record_active_codes(["P0301"], vin="VIN123")
    db.upsert_vehicle("VIN123", "Honda", "Civic", "2018")
    rows = db.vehicles_view()
    assert rows[0]["make"] == "Honda"
    assert rows[0]["model"] == "Civic"
    assert rows[0]["year"] == "2018"


def test_active_events_includes_decoded_vehicle_info():
    db = _db()
    db.record_active_codes(["P0301"], vin="VIN123")
    db.upsert_vehicle("VIN123", "Honda", "Civic", "2018")
    assert db.active_events()[0]["make"] == "Honda"


def test_upsert_vehicle_updates_existing_row():
    db = _db()
    db.record_active_codes(["P0301"], vin="VIN123")
    db.upsert_vehicle("VIN123", "Honda", "Civic", "2017")
    db.upsert_vehicle("VIN123", "Honda", "Civic", "2018")
    rows = db.vehicles_view()
    assert len(rows) == 1
    assert rows[0]["year"] == "2018"


def test_recurring_dtc_after_clear_creates_new_active_row():
    db = _db()
    db.record_active_codes(["P0301"], vin="VIN123")
    db.clear_active_events()
    db.record_active_codes(["P0301"], vin="VIN123")
    events = db.active_events()
    assert len(events) == 1
    assert events[0]["code"] == "P0301"
    assert events[0]["cleared_at"] is None


def test_active_events_description_uses_generic_seed_data():
    db = _db()
    db.record_active_codes(["P0301"], vin=None)
    assert db.active_events()[0]["description"] == "Cylinder 1 Misfire Detected"


def test_active_events_description_unknown_code_fallback():
    db = _db()
    db.record_active_codes(["P9999"], vin=None)
    assert db.active_events()[0]["description"] == "Unknown DTC"


def test_active_events_description_upgrades_to_manufacturer_specific_after_decode():
    db = _db()
    # P1456 is a Honda-specific code with no generic SAE meaning.
    db.record_active_codes(["P1456"], vin="VIN123")
    assert db.active_events()[0]["description"] == "Unknown DTC"
    db.upsert_vehicle("VIN123", "Honda", "Accord", "2008")
    assert db.active_events()[0]["description"] == (
        "Evaporative Emission System Leak (Fuel Tank System)"
    )


def test_dtc_reference_reseed_removes_stale_entries(tmp_path, monkeypatch):
    import json

    from jcan import history_db as history_db_module

    seed_path = tmp_path / "dtc_codes.json"
    seed_path.write_text(json.dumps([{"code": "P0507", "make": "", "description": "Old description"}]))
    monkeypatch.setattr(history_db_module, "SEED_DATA_PATH", seed_path)

    db = HistoryDB(":memory:")
    db.record_active_codes(["P0507"], vin=None)
    assert db.active_events()[0]["description"] == "Old description"

    # Simulate editing the seed file to remove the P0507 entry, then a process restart.
    seed_path.write_text(json.dumps([]))
    db2 = HistoryDB(":memory:")
    db2.record_active_codes(["P0507"], vin=None)
    assert db2.active_events()[0]["description"] == "Unknown DTC"


def test_active_events_description_prefers_manufacturer_specific_over_generic(tmp_path, monkeypatch):
    import json

    from jcan import history_db as history_db_module

    seed_path = tmp_path / "dtc_codes.json"
    seed_path.write_text(json.dumps([
        {"code": "P0420", "make": "", "description": "Generic catalyst description"},
        {"code": "P0420", "make": "Honda", "description": "Honda-specific catalyst description"},
    ]))
    monkeypatch.setattr(history_db_module, "SEED_DATA_PATH", seed_path)

    db = HistoryDB(":memory:")
    db.record_active_codes(["P0420"], vin="VIN123")
    db.upsert_vehicle("VIN123", "Honda", "Accord", "2008")
    assert db.active_events()[0]["description"] == "Honda-specific catalyst description"
