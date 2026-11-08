import threading
import time

import isotp

from jcan import pids as pids_module
from jcan.can_transport import create_bus
from jcan.reader import Reader
from jcan.simulator import FAKE_VIN, Simulator


def _start_custom_fake_server(bus, handler):
    addr = isotp.Address(isotp.AddressingMode.Normal_11bits, txid=0x7E8, rxid=0x7DF)
    stack = isotp.CanStack(bus, address=addr)
    stack.start()
    stop_event = threading.Event()

    def run():
        while not stop_event.is_set():
            request = stack.recv(block=True, timeout=0.2)
            if request is None:
                continue
            response = handler(bytes(request))
            if response is not None:
                stack.send(response)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()

    def stop():
        stop_event.set()
        thread.join(timeout=1.0)
        stack.stop()

    return stop


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


def test_stop_before_start_is_safe():
    bus = create_bus("virtual", "reader-test-stop-safety")
    reader = Reader(bus, poll_interval_s=1.0, pid_timeout_s=0.2)
    reader.stop()  # must not raise
    bus.shutdown()


def test_reader_discovers_supported_pids_including_o2():
    channel = "reader-test-discovery"
    bus_sim = create_bus("virtual", channel)
    bus_reader = create_bus("virtual", channel)
    sim = Simulator(bus_sim)
    sim.start()

    reader = Reader(bus_reader, poll_interval_s=1.0, pid_timeout_s=1.0)
    reader.start()
    try:
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline and "o2_b1s1" not in {p.name for p in reader.live_pids}:
            time.sleep(0.05)
        discovered_names = {p.name for p in reader.live_pids}
        assert "o2_b1s1" in discovered_names
        assert "o2_b1s2" in discovered_names
        assert "o2_b2s1" not in discovered_names
    finally:
        reader.stop()
        sim.stop()
        bus_sim.shutdown()
        bus_reader.shutdown()


def test_reader_pushes_readiness_status():
    channel = "reader-test-readiness"
    bus_sim = create_bus("virtual", channel)
    bus_reader = create_bus("virtual", channel)
    sim = Simulator(bus_sim)
    sim.start()

    statuses = []
    readiness_updates = []
    reader = Reader(bus_reader, poll_interval_s=0.1, pid_timeout_s=1.0)
    reader.on_status = lambda status: statuses.append(status)
    reader.on_readiness = lambda status: readiness_updates.append(status)
    reader.start()
    try:
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline and not readiness_updates:
            time.sleep(0.05)
        assert readiness_updates
        status = readiness_updates[0]
        assert status["mil_on"] is True
        assert status["dtc_count"] == 2
        assert {"name": "components", "ready": False} in status["monitors"]
    finally:
        reader.stop()
        sim.stop()
        bus_sim.shutdown()
        bus_reader.shutdown()


def test_reader_vin_read_failure_continues_to_connected():
    channel = "reader-test-vin-failure"
    bus_reader = create_bus("virtual", channel)
    # No simulator is listening on this channel, so read_vin() will time out
    # (pid_timeout_s=0.2 keeps this test fast) rather than ever succeeding.
    statuses = []
    reader = Reader(bus_reader, poll_interval_s=1.0, pid_timeout_s=0.2)
    reader.on_status = lambda status: statuses.append(status)
    reader.start()
    try:
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline and "connected" not in statuses:
            time.sleep(0.05)
        assert "vin_read_failed" in statuses
        assert "connected" in statuses
        assert reader.current_vin is None
    finally:
        reader.stop()
        bus_reader.shutdown()


def test_reader_excludes_unsupported_pids():
    channel = "reader-test-exclude"
    bus_server = create_bus("virtual", channel)
    bus_reader = create_bus("virtual", channel)

    def handler(request):
        if request[0] == 0x09:
            return None  # no VIN response; reader should still proceed to discovery
        if request[0] == 0x01 and request[1] == 0x00:
            # Only PID 0x0C (rpm) reported supported; nothing else, no next range.
            return bytes([0x41, 0x00, 0x00, 0x10, 0x00, 0x00])
        if request[0] == 0x01 and request[1] == 0x0C:
            return bytes([0x41, 0x0C, 0x1A, 0xF8])
        return None

    stop_server = _start_custom_fake_server(bus_server, handler)
    reader = Reader(bus_reader, poll_interval_s=1.0, pid_timeout_s=0.3)
    reader.start()
    try:
        deadline = time.monotonic() + 3.0
        default_names = {p.name for p in pids_module.LIVE_PIDS}
        while time.monotonic() < deadline and {p.name for p in reader.live_pids} == default_names:
            time.sleep(0.05)
        names = {p.name for p in reader.live_pids}
        assert names == {"rpm"}
    finally:
        reader.stop()
        stop_server()
        bus_server.shutdown()
        bus_reader.shutdown()


def test_reader_simulate_disconnect_acks_then_reports_lost():
    channel = "reader-test-simulate-disconnect"
    bus_sim = create_bus("virtual", channel)
    bus_reader = create_bus("virtual", channel)
    sim = Simulator(bus_sim)
    sim.start()

    statuses = []
    reader = Reader(bus_reader, poll_interval_s=0.1, pid_timeout_s=1.0)
    reader.on_status = lambda status: statuses.append(status)
    reader.start()
    try:
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline and "connected" not in statuses:
            time.sleep(0.05)

        status, payload = reader.submit("simulate_disconnect").get(timeout=3.0)
        assert status == "ok"
        assert payload is None

        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline and not any(s.startswith("lost") for s in statuses):
            time.sleep(0.05)
        assert any(s.startswith("lost") for s in statuses)

        # Default reconnect delay is 30s; well within that, no readings resume.
        readings_before = []
        reader.on_reading = lambda name, value, unit: readings_before.append(name)
        time.sleep(0.3)
        assert readings_before == []
    finally:
        reader.stop()
        sim.stop()
        bus_sim.shutdown()
        bus_reader.shutdown()


def test_reader_simulate_disconnect_auto_reconnects_after_delay():
    channel = "reader-test-simulate-disconnect-reconnect"
    bus_sim = create_bus("virtual", channel)
    bus_reader = create_bus("virtual", channel)
    sim = Simulator(bus_sim)
    sim.start()

    statuses = []
    reader = Reader(
        bus_reader, poll_interval_s=0.1, pid_timeout_s=1.0, simulated_reconnect_delay_s=0.2
    )
    reader.on_status = lambda status: statuses.append(status)
    reader.start()
    try:
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline and "connected" not in statuses:
            time.sleep(0.05)

        reader.submit("simulate_disconnect").get(timeout=3.0)

        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline and statuses.count("connected") < 2:
            time.sleep(0.05)
        assert statuses.count("connected") == 2
        assert any(s.startswith("lost") for s in statuses)

        readings = []
        reader.on_reading = lambda name, value, unit: readings.append(name)
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline and not readings:
            time.sleep(0.05)
        assert readings  # polling resumed after reconnect
    finally:
        reader.stop()
        sim.stop()
        bus_sim.shutdown()
        bus_reader.shutdown()


def test_reader_falls_back_to_full_catalog_when_discovery_fails():
    channel = "reader-test-discovery-fail"
    bus_server = create_bus("virtual", channel)
    bus_reader = create_bus("virtual", channel)

    def handler(request):
        if request[0] == 0x09:
            return bytes([0x49, 0x02, 0x01]) + b"1HGCM82633A004352"
        return None  # PID 0x00 (and everything else) never answered

    stop_server = _start_custom_fake_server(bus_server, handler)
    reader = Reader(bus_reader, poll_interval_s=1.0, pid_timeout_s=0.3)
    reader.start()
    try:
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline and reader.current_vin is None:
            time.sleep(0.05)
        time.sleep(0.5)  # give the (failing) discovery request time to time out and fall back
        assert {p.name for p in reader.live_pids} == {p.name for p in pids_module.LIVE_PIDS}
    finally:
        reader.stop()
        stop_server()
        bus_server.shutdown()
        bus_reader.shutdown()
