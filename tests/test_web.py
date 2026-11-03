import queue

from fastapi.testclient import TestClient

from jcan.history_db import HistoryDB
from jcan.web import create_app


class StubReader:
    def __init__(self):
        self.current_vin = "VIN123"
        self.on_reading = lambda *a: None
        self.on_status = lambda *a: None
        self._next_result = ("ok", None)
        self.started = False

    def start(self):
        self.started = True

    def stop(self):
        self.started = False

    def set_next_result(self, result):
        self._next_result = result

    def submit(self, action):
        q = queue.Queue(maxsize=1)
        q.put(self._next_result)
        return q


def _client():
    reader = StubReader()
    db = HistoryDB(":memory:")
    app = create_app(reader, db, static_dir="jcan/static")
    return TestClient(app), reader, db


def test_get_dtcs_records_and_returns_active_codes():
    client, reader, db = _client()
    reader.set_next_result(("ok", ["P0301"]))
    with client:
        response = client.get("/dtcs")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["code"] == "P0301"
    assert body[0]["vin"] == "VIN123"


def test_get_dtcs_propagates_reader_error():
    client, reader, db = _client()
    reader.set_next_result(("error", "no response"))
    with client:
        response = client.get("/dtcs")
    assert response.status_code == 503


def test_clear_dtcs_stamps_existing_events():
    client, reader, db = _client()
    db.record_active_codes(["P0301"], vin="VIN123")
    reader.set_next_result(("ok", None))
    with client:
        response = client.post("/dtcs/clear")
    assert response.status_code == 200
    assert db.active_events() == []


def test_patch_notes_updates_event():
    client, reader, db = _client()
    db.record_active_codes(["P0301"], vin="VIN123")
    event_id = db.active_events()[0]["id"]
    with client:
        response = client.patch(f"/dtcs/{event_id}/notes", json={"notes": "fixed it"})
    assert response.status_code == 200
    assert db.active_events()[0]["notes"] == "fixed it"


def test_patch_notes_404_for_missing_event():
    client, reader, db = _client()
    with client:
        response = client.patch("/dtcs/999/notes", json={"notes": "x"})
    assert response.status_code == 404


def test_get_vehicles_lists_distinct_vins():
    client, reader, db = _client()
    db.record_active_codes(["P0301"], vin="VIN123")
    with client:
        response = client.get("/vehicles")
    assert response.status_code == 200
    body = response.json()
    assert body[0]["vin"] == "VIN123"
    assert body[0]["raw"] is None  # not decoded yet


def test_decode_vehicle_persists_result(monkeypatch):
    client, reader, db = _client()
    db.record_active_codes(["P0301"], vin="VIN123")

    monkeypatch.setattr(
        "jcan.web.decode_vin",
        lambda vin: {
            "make": "Honda",
            "model": "Civic",
            "year": "2018",
            "raw": {"Make": "Honda", "Model": "Civic", "ModelYear": "2018", "Trim": "EX"},
        },
    )
    with client:
        response = client.post("/vehicles/VIN123/decode")
    assert response.status_code == 200
    body = response.json()
    assert body["make"] == "Honda"
    assert body["raw"]["Trim"] == "EX"

    rows = db.vehicles_view()
    assert rows[0]["make"] == "Honda"
    assert rows[0]["raw_json"] is not None

    with client:
        vehicles_response = client.get("/vehicles")
    assert vehicles_response.json()[0]["raw"]["Trim"] == "EX"


def test_decode_vehicle_502_on_failure(monkeypatch):
    client, reader, db = _client()

    def fake_decode_vin(vin):
        from jcan.vin_decoder import VinDecodeError
        raise VinDecodeError("not found")

    monkeypatch.setattr("jcan.web.decode_vin", fake_decode_vin)
    with client:
        response = client.post("/vehicles/VIN123/decode")
    assert response.status_code == 502


def test_websocket_broadcasts_reading():
    client, reader, db = _client()
    with client:
        with client.websocket_connect("/ws") as websocket:
            reader.on_reading("rpm", 1234.0, "rpm")
            message = websocket.receive_json()
    assert message == {"type": "reading", "pid": "rpm", "value": 1234.0, "unit": "rpm"}


def test_websocket_broadcasts_status():
    client, reader, db = _client()
    with client:
        with client.websocket_connect("/ws") as websocket:
            reader.on_status("connected")
            message = websocket.receive_json()
    assert message == {"type": "status", "status": "connected"}
