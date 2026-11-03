from jcan.history_db import HistoryDB


def _db():
    return HistoryDB(":memory:")


def test_record_active_codes_inserts_new():
    db = _db()
    db.record_active_codes([("P0301", "Cylinder 1 Misfire Detected")], vin="VIN123")
    events = db.active_events()
    assert len(events) == 1
    assert events[0]["code"] == "P0301"
    assert events[0]["vin"] == "VIN123"
    assert events[0]["cleared_at"] is None
    assert events[0]["notes"] == ""


def test_record_active_codes_does_not_duplicate():
    db = _db()
    db.record_active_codes([("P0301", "desc")], vin="VIN123")
    db.record_active_codes([("P0301", "desc")], vin="VIN123")
    assert len(db.active_events()) == 1


def test_clear_active_events_stamps_cleared_at():
    db = _db()
    db.record_active_codes([("P0301", "desc")], vin="VIN123")
    db.clear_active_events()
    assert db.active_events() == []


def test_set_notes_updates_existing_event():
    db = _db()
    db.record_active_codes([("P0301", "desc")], vin="VIN123")
    event_id = db.active_events()[0]["id"]
    assert db.set_notes(event_id, "replaced spark plug") is True
    assert db.active_events()[0]["notes"] == "replaced spark plug"


def test_set_notes_returns_false_for_missing_event():
    db = _db()
    assert db.set_notes(999, "x") is False


def test_vehicles_view_lists_undecoded_vin():
    db = _db()
    db.record_active_codes([("P0301", "desc")], vin="VIN123")
    rows = db.vehicles_view()
    assert len(rows) == 1
    assert rows[0]["vin"] == "VIN123"
    assert rows[0]["make"] is None


def test_upsert_vehicle_then_view_shows_decoded_info():
    db = _db()
    db.record_active_codes([("P0301", "desc")], vin="VIN123")
    db.upsert_vehicle("VIN123", "Honda", "Civic", "2018")
    rows = db.vehicles_view()
    assert rows[0]["make"] == "Honda"
    assert rows[0]["model"] == "Civic"
    assert rows[0]["year"] == "2018"


def test_active_events_includes_decoded_vehicle_info():
    db = _db()
    db.record_active_codes([("P0301", "desc")], vin="VIN123")
    db.upsert_vehicle("VIN123", "Honda", "Civic", "2018")
    assert db.active_events()[0]["make"] == "Honda"
