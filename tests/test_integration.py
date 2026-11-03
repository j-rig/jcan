import time

from fastapi.testclient import TestClient

from jcan.can_transport import create_bus
from jcan.history_db import HistoryDB
from jcan.reader import Reader
from jcan.simulator import FAKE_VIN, Simulator
from jcan.web import create_app


def test_full_app_against_simulator(monkeypatch, tmp_path):
    channel = "integration-test-1"
    bus_sim = create_bus("virtual", channel)
    bus_reader = create_bus("virtual", channel)
    sim = Simulator(bus_sim)
    sim.start()

    reader = Reader(bus_reader, poll_interval_s=0.2, pid_timeout_s=1.0)
    db = HistoryDB(str(tmp_path / "jcan.db"))
    app = create_app(reader, db, static_dir="jcan/static")

    monkeypatch.setattr(
        "jcan.web.decode_vin",
        lambda vin: {
            "make": "Honda",
            "model": "Civic",
            "year": "2018",
            "raw": {"Make": "Honda", "Model": "Civic", "ModelYear": "2018", "Trim": "EX"},
        },
    )

    try:
        with TestClient(app) as client:
            deadline = time.monotonic() + 3.0
            while time.monotonic() < deadline and reader.current_vin is None:
                time.sleep(0.05)
            assert reader.current_vin == FAKE_VIN

            with client.websocket_connect("/ws") as websocket:
                message = websocket.receive_json()
                assert message["type"] in ("reading", "status")

            dtcs_response = client.get("/dtcs")
            assert dtcs_response.status_code == 200
            events = dtcs_response.json()
            codes = {event["code"] for event in events}
            assert codes == {"P0133", "P0301"}
            assert all(event["vin"] == FAKE_VIN for event in events)
            descriptions = {event["code"]: event["description"] for event in events}
            assert descriptions["P0301"] == "Cylinder 1 Misfire Detected"

            event_id = events[0]["id"]
            notes_response = client.patch(f"/dtcs/{event_id}/notes", json={"notes": "checked, looks fine"})
            assert notes_response.status_code == 200
            assert client.get("/dtcs").json()[0]["notes"] == "checked, looks fine"

            vehicles_response = client.get("/vehicles")
            vehicles = vehicles_response.json()
            assert vehicles[0]["vin"] == FAKE_VIN
            assert vehicles[0]["make"] is None

            decode_response = client.post(f"/vehicles/{FAKE_VIN}/decode")
            assert decode_response.status_code == 200

            vehicles_after = client.get("/vehicles").json()
            assert vehicles_after[0]["make"] == "Honda"
            assert vehicles_after[0]["raw"]["Trim"] == "EX"

            clear_response = client.post("/dtcs/clear")
            assert clear_response.status_code == 200
            assert client.get("/dtcs").json() == []
    finally:
        sim.stop()
        bus_sim.shutdown()
        bus_reader.shutdown()
