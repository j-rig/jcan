import time

from jcan.can_transport import create_bus
from jcan.reader import Reader
from jcan.simulator import FAKE_VIN, Simulator


def test_reader_reads_vin_and_polls_pids():
    channel = "reader-test-1"
    bus_sim = create_bus("virtual", channel)
    bus_reader = create_bus("virtual", channel)
    sim = Simulator(bus_sim)
    sim.start()

    readings = []
    statuses = []
    reader = Reader(bus_reader, poll_interval_s=0.1, pid_timeout_s=1.0)
    reader.on_reading = lambda name, value, unit: readings.append((name, value, unit))
    reader.on_status = lambda status: statuses.append(status)
    reader.start()
    try:
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline and len(readings) < 6:
            time.sleep(0.05)
        names = {r[0] for r in readings}
        assert "rpm" in names
        assert "speed" in names
        assert reader.current_vin == FAKE_VIN
        assert "connected" in statuses
    finally:
        reader.stop()
        sim.stop()
        bus_sim.shutdown()
        bus_reader.shutdown()


def test_reader_submit_read_dtcs():
    channel = "reader-test-2"
    bus_sim = create_bus("virtual", channel)
    bus_reader = create_bus("virtual", channel)
    sim = Simulator(bus_sim)
    sim.start()

    reader = Reader(bus_reader, poll_interval_s=1.0, pid_timeout_s=1.0)
    reader.start()
    try:
        status, payload = reader.submit("read_dtcs").get(timeout=3.0)
        assert status == "ok"
        assert set(payload) == {"P0133", "P0301"}
    finally:
        reader.stop()
        sim.stop()
        bus_sim.shutdown()
        bus_reader.shutdown()


def test_reader_submit_clear_dtcs():
    channel = "reader-test-3"
    bus_sim = create_bus("virtual", channel)
    bus_reader = create_bus("virtual", channel)
    sim = Simulator(bus_sim)
    sim.start()

    reader = Reader(bus_reader, poll_interval_s=1.0, pid_timeout_s=1.0)
    reader.start()
    try:
        status, _ = reader.submit("clear_dtcs").get(timeout=3.0)
        assert status == "ok"
        status, payload = reader.submit("read_dtcs").get(timeout=3.0)
        assert status == "ok"
        assert payload == []
    finally:
        reader.stop()
        sim.stop()
        bus_sim.shutdown()
        bus_reader.shutdown()
