# jcan Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a personal OBD-II diagnostic tool — a Python service that reads live engine data and trouble codes off a car's CAN bus via a USB dongle, stores DTC history in SQLite, and serves a browser UI (Gauges / Diagnostics / Vehicles tabs) over HTTP + WebSocket.

**Architecture:** Single Python process. A background thread (`reader`) owns a `python-can` bus connection and an ISO-TP/OBD2 session, continuously polling live PIDs and handling on-demand DTC read/clear commands via a thread-safe queue. A FastAPI app streams live readings over WebSocket and exposes REST endpoints backed by a thin SQLite wrapper. A `virtual` CAN bus + built-in fake-ECU `simulator` module lets the entire stack run and be tested with zero real hardware; swapping to the `slcan` bus backend is the only change needed for real hardware.

**Tech Stack:** Python 3.10+, `python-can` (CAN transport), `can-isotp` (ISO-TP transport for multi-frame OBD2 responses), FastAPI + `uvicorn` (HTTP/WebSocket server), `requests` (NHTSA vPIC VIN decoding), stdlib `sqlite3` (history storage), plain HTML/CSS/JS frontend (no framework), `pytest` for tests.

Reference docs: `docs/superpowers/specs/2026-11-02-car-diagnostic-tool-design.md` (design), `docs/hardware-obd2-wiring.md` (wiring/dongle reference).

---

## File Structure

```
jcan/
  __init__.py
  config.py          # env-based config (bus type/channel, poll interval, DB path, HTTP host/port)
  pids.py            # SAE J1979 Mode 01 PID table + decode formulas
  dtc.py             # DTC byte decoding + a small code->description lookup
  can_transport.py   # python-can Bus factory: "slcan" (real) or "virtual" (sim/test)
  obd2.py            # ISO-TP/OBD2 request-response session (Mode 01/03/04/09)
  simulator.py        # fake ECU on a virtual bus, for dev/test without hardware
  reader.py          # background thread: VIN read, PID polling, on-demand DTC commands
  history_db.py      # SQLite wrapper: dtc_events + vehicles tables
  vin_decoder.py      # NHTSA vPIC VIN decode wrapper
  web.py             # FastAPI app: WebSocket stream + REST endpoints
  main.py            # entrypoint: wires config -> bus -> db -> reader -> web app -> uvicorn
  static/
    index.html
    app.js
    style.css

tests/
  test_config.py
  test_pids.py
  test_dtc.py
  test_can_transport.py
  test_obd2.py
  test_simulator.py
  test_history_db.py
  test_vin_decoder.py
  test_reader.py
  test_web.py
  test_integration.py

pyproject.toml
README.md
```

---

### Task 1: Project scaffolding and config

**Files:**
- Create: `pyproject.toml`
- Create: `jcan/__init__.py`
- Create: `jcan/config.py`
- Create: `jcan/static/index.html` (placeholder — full version in Task 11)
- Test: `tests/test_config.py`

- [ ] **Step 1: Create the package layout and dependency manifest**

`jcan/__init__.py`:
```python
```

(empty file — just marks `jcan` as a package)

`jcan/static/index.html` (placeholder so FastAPI's `StaticFiles` mount succeeds once `web.py` exists; replaced with the real UI in Task 11):
```html
<!DOCTYPE html>
<html><head><title>jcan</title></head><body>placeholder</body></html>
```

`pyproject.toml`:
```toml
[project]
name = "jcan"
version = "0.1.0"
description = "Personal OBD-II / CAN bus diagnostic tool"
requires-python = ">=3.10"
dependencies = [
    "python-can>=4.3",
    "can-isotp>=2.0",
    "fastapi>=0.110",
    "uvicorn[standard]>=0.29",
    "requests>=2.31",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "httpx>=0.27",
]

[tool.setuptools.packages.find]
include = ["jcan*"]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"
```

- [ ] **Step 2: Install the project in editable mode with dev dependencies**

Run: `pip install -e ".[dev]"`
Expected: installs `jcan`, `python-can`, `can-isotp`, `fastapi`, `uvicorn`, `requests`, `pytest`, `httpx` without errors.

- [ ] **Step 3: Write the failing test for config**

`tests/test_config.py`:
```python
from jcan.config import Config


def test_from_env_uses_defaults(monkeypatch):
    for key in [
        "JCAN_BUS_TYPE", "JCAN_CHANNEL", "JCAN_POLL_INTERVAL_S",
        "JCAN_PID_TIMEOUT_S", "JCAN_DB_PATH", "JCAN_HTTP_HOST", "JCAN_HTTP_PORT",
    ]:
        monkeypatch.delenv(key, raising=False)
    cfg = Config.from_env()
    assert cfg.bus_type == "virtual"
    assert cfg.channel == "jcan-sim"
    assert cfg.poll_interval_s == 1.0
    assert cfg.pid_timeout_s == 0.2
    assert cfg.db_path == "jcan.db"
    assert cfg.http_host == "127.0.0.1"
    assert cfg.http_port == 8000


def test_from_env_reads_overrides(monkeypatch):
    monkeypatch.setenv("JCAN_BUS_TYPE", "slcan")
    monkeypatch.setenv("JCAN_CHANNEL", "/dev/tty.usbmodem1")
    cfg = Config.from_env()
    assert cfg.bus_type == "slcan"
    assert cfg.channel == "/dev/tty.usbmodem1"
```

- [ ] **Step 4: Run test to verify it fails**

Run: `pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'jcan.config'`

- [ ] **Step 5: Implement config.py**

`jcan/config.py`:
```python
import os
from dataclasses import dataclass


@dataclass
class Config:
    bus_type: str
    channel: str
    poll_interval_s: float
    pid_timeout_s: float
    db_path: str
    http_host: str
    http_port: int

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            bus_type=os.environ.get("JCAN_BUS_TYPE", "virtual"),
            channel=os.environ.get("JCAN_CHANNEL", "jcan-sim"),
            poll_interval_s=float(os.environ.get("JCAN_POLL_INTERVAL_S", "1.0")),
            pid_timeout_s=float(os.environ.get("JCAN_PID_TIMEOUT_S", "0.2")),
            db_path=os.environ.get("JCAN_DB_PATH", "jcan.db"),
            http_host=os.environ.get("JCAN_HTTP_HOST", "127.0.0.1"),
            http_port=int(os.environ.get("JCAN_HTTP_PORT", "8000")),
        )
```

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/test_config.py -v`
Expected: PASS (2 passed)

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml jcan/__init__.py jcan/config.py jcan/static/index.html tests/test_config.py
git commit -m "feat: project scaffolding and env-based config"
```

---

### Task 2: PID formula table

**Files:**
- Create: `jcan/pids.py`
- Test: `tests/test_pids.py`

- [ ] **Step 1: Write the failing test**

`tests/test_pids.py`:
```python
from jcan.pids import LIVE_PIDS, PIDS_BY_ID


def _decode(name, data):
    pid_def = next(p for p in LIVE_PIDS if p.name == name)
    return pid_def.decode(bytes(data))


def test_rpm_decode():
    assert _decode("rpm", [0x1A, 0xF8]) == 1726.0


def test_speed_decode():
    assert _decode("speed", [0x50]) == 80.0


def test_coolant_temp_decode():
    assert _decode("coolant_temp", [0x7B]) == 83.0


def test_intake_air_temp_decode():
    assert _decode("intake_air_temp", [0x46]) == 30.0


def test_throttle_position_decode():
    assert _decode("throttle_position", [0x80]) == 50.2


def test_engine_load_decode():
    assert _decode("engine_load", [0x80]) == 50.2


def test_pids_by_id_lookup():
    assert PIDS_BY_ID[0x0C].name == "rpm"
    assert PIDS_BY_ID[0x0C].unit == "rpm"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_pids.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'jcan.pids'`

- [ ] **Step 3: Implement pids.py**

`jcan/pids.py`:
```python
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class PidDef:
    pid: int
    name: str
    unit: str
    decode: Callable[[bytes], float]


def _decode_rpm(data: bytes) -> float:
    return ((data[0] * 256) + data[1]) / 4


def _decode_speed(data: bytes) -> float:
    return float(data[0])


def _decode_temp(data: bytes) -> float:
    return float(data[0] - 40)


def _decode_percent(data: bytes) -> float:
    return round(data[0] * 100 / 255, 1)


LIVE_PIDS = [
    PidDef(0x0C, "rpm", "rpm", _decode_rpm),
    PidDef(0x0D, "speed", "km/h", _decode_speed),
    PidDef(0x05, "coolant_temp", "C", _decode_temp),
    PidDef(0x11, "throttle_position", "%", _decode_percent),
    PidDef(0x04, "engine_load", "%", _decode_percent),
    PidDef(0x0F, "intake_air_temp", "C", _decode_temp),
]

PIDS_BY_ID = {p.pid: p for p in LIVE_PIDS}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_pids.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add jcan/pids.py tests/test_pids.py
git commit -m "feat: SAE J1979 Mode 01 PID decode table"
```

---

### Task 3: DTC decoding

**Files:**
- Create: `jcan/dtc.py`
- Test: `tests/test_dtc.py`

- [ ] **Step 1: Write the failing test**

`tests/test_dtc.py`:
```python
from jcan.dtc import decode_dtc, decode_dtcs, describe_dtc


def test_decode_single_dtc_powertrain():
    assert decode_dtc(0x01, 0x33) == "P0133"


def test_decode_dtc_chassis_type():
    assert decode_dtc(0x41, 0x00) == "C0100"


def test_decode_dtcs_skips_zero_padding():
    data = bytes([0x01, 0x33, 0x00, 0x00])
    assert decode_dtcs(data) == ["P0133"]


def test_decode_dtcs_multiple():
    data = bytes([0x01, 0x33, 0x03, 0x01])
    assert decode_dtcs(data) == ["P0133", "P0301"]


def test_decode_dtcs_empty():
    assert decode_dtcs(b"") == []


def test_describe_known_code():
    assert describe_dtc("P0301") == "Cylinder 1 Misfire Detected"


def test_describe_unknown_code():
    assert describe_dtc("P9999") == "Unknown DTC"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_dtc.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'jcan.dtc'`

- [ ] **Step 3: Implement dtc.py**

`jcan/dtc.py`:
```python
DTC_DESCRIPTIONS = {
    "P0133": "O2 Sensor Circuit Slow Response (Bank 1 Sensor 1)",
    "P0301": "Cylinder 1 Misfire Detected",
    "P0420": "Catalyst System Efficiency Below Threshold (Bank 1)",
}

_TYPE_CHARS = {0b00: "P", 0b01: "C", 0b10: "B", 0b11: "U"}


def decode_dtc(byte1: int, byte2: int) -> str:
    type_char = _TYPE_CHARS[(byte1 >> 6) & 0b11]
    first_digit = (byte1 >> 4) & 0b11
    second_digit = byte1 & 0b1111
    third_digit = (byte2 >> 4) & 0b1111
    fourth_digit = byte2 & 0b1111
    return f"{type_char}{first_digit}{second_digit:X}{third_digit:X}{fourth_digit:X}"


def decode_dtcs(data: bytes) -> list[str]:
    codes = []
    for i in range(0, len(data) - 1, 2):
        b1, b2 = data[i], data[i + 1]
        if b1 == 0 and b2 == 0:
            continue
        codes.append(decode_dtc(b1, b2))
    return codes


def describe_dtc(code: str) -> str:
    return DTC_DESCRIPTIONS.get(code, "Unknown DTC")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_dtc.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add jcan/dtc.py tests/test_dtc.py
git commit -m "feat: DTC byte decoding and description lookup"
```

---

### Task 4: CAN transport (real/virtual bus factory)

**Files:**
- Create: `jcan/can_transport.py`
- Test: `tests/test_can_transport.py`

- [ ] **Step 1: Write the failing test**

`tests/test_can_transport.py`:
```python
import pytest
import can

from jcan.can_transport import create_bus


def test_virtual_buses_on_same_channel_communicate():
    channel = "test-channel-1"
    bus_a = create_bus("virtual", channel)
    bus_b = create_bus("virtual", channel)
    try:
        bus_a.send(can.Message(arbitration_id=0x123, data=[1, 2, 3], is_extended_id=False))
        received = bus_b.recv(timeout=1.0)
        assert received is not None
        assert received.arbitration_id == 0x123
        assert bytes(received.data) == bytes([1, 2, 3])
    finally:
        bus_a.shutdown()
        bus_b.shutdown()


def test_unknown_bus_type_raises():
    with pytest.raises(ValueError):
        create_bus("bogus", "chan")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_can_transport.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'jcan.can_transport'`

- [ ] **Step 3: Implement can_transport.py**

`jcan/can_transport.py`:
```python
import can


def create_bus(bus_type: str, channel: str) -> can.BusABC:
    if bus_type == "slcan":
        return can.Bus(interface="slcan", channel=channel, bitrate=500000)
    if bus_type == "virtual":
        return can.Bus(interface="virtual", channel=channel, receive_own_messages=False)
    raise ValueError(f"Unknown bus_type: {bus_type!r} (expected 'slcan' or 'virtual')")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_can_transport.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add jcan/can_transport.py tests/test_can_transport.py
git commit -m "feat: python-can bus factory for slcan/virtual backends"
```

---

### Task 5: OBD2 over ISO-TP session

**Files:**
- Create: `jcan/obd2.py`
- Test: `tests/test_obd2.py`

- [ ] **Step 1: Write the failing test**

`tests/test_obd2.py`:
```python
import threading

import pytest
import isotp

from jcan.can_transport import create_bus
from jcan.obd2 import Obd2Session, Obd2Error

RESPONSE_ID = 0x7E8
REQUEST_ID = 0x7DF


def _start_fake_server(bus, handler):
    addr = isotp.Address(isotp.AddressingMode.Normal_11bits, txid=RESPONSE_ID, rxid=REQUEST_ID)
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


def test_read_pid_rpm():
    channel = "test-obd2-1"
    bus_server = create_bus("virtual", channel)
    bus_client = create_bus("virtual", channel)

    def handler(request):
        assert request == bytes([0x01, 0x0C])
        return bytes([0x41, 0x0C, 0x1A, 0xF8])

    stop_server = _start_fake_server(bus_server, handler)
    session = Obd2Session(bus_client, response_id=RESPONSE_ID, timeout=1.0)
    try:
        data = session.read_pid(0x0C)
        assert data == bytes([0x1A, 0xF8])
    finally:
        session.close()
        stop_server()
        bus_server.shutdown()
        bus_client.shutdown()


def test_read_dtcs():
    channel = "test-obd2-2"
    bus_server = create_bus("virtual", channel)
    bus_client = create_bus("virtual", channel)

    def handler(request):
        assert request == bytes([0x03])
        return bytes([0x43, 0x01, 0x01, 0x33])

    stop_server = _start_fake_server(bus_server, handler)
    session = Obd2Session(bus_client, response_id=RESPONSE_ID, timeout=1.0)
    try:
        data = session.read_dtcs()
        assert data == bytes([0x01, 0x33])
    finally:
        session.close()
        stop_server()
        bus_server.shutdown()
        bus_client.shutdown()


def test_clear_dtcs():
    channel = "test-obd2-3"
    bus_server = create_bus("virtual", channel)
    bus_client = create_bus("virtual", channel)

    def handler(request):
        assert request == bytes([0x04])
        return bytes([0x44])

    stop_server = _start_fake_server(bus_server, handler)
    session = Obd2Session(bus_client, response_id=RESPONSE_ID, timeout=1.0)
    try:
        session.clear_dtcs()
    finally:
        session.close()
        stop_server()
        bus_server.shutdown()
        bus_client.shutdown()


def test_read_vin():
    channel = "test-obd2-4"
    bus_server = create_bus("virtual", channel)
    bus_client = create_bus("virtual", channel)

    def handler(request):
        assert request == bytes([0x09, 0x02])
        return bytes([0x49, 0x02, 0x01]) + b"1HGCM82633A004352"

    stop_server = _start_fake_server(bus_server, handler)
    session = Obd2Session(bus_client, response_id=RESPONSE_ID, timeout=1.0)
    try:
        vin = session.read_vin()
        assert vin == "1HGCM82633A004352"
    finally:
        session.close()
        stop_server()
        bus_server.shutdown()
        bus_client.shutdown()


def test_read_pid_timeout_raises():
    channel = "test-obd2-5"
    bus_client = create_bus("virtual", channel)
    session = Obd2Session(bus_client, response_id=RESPONSE_ID, timeout=0.2)
    try:
        with pytest.raises(Obd2Error):
            session.read_pid(0x0C)
    finally:
        session.close()
        bus_client.shutdown()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_obd2.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'jcan.obd2'`

- [ ] **Step 3: Implement obd2.py**

`jcan/obd2.py`:
```python
import can
import isotp

REQUEST_ID = 0x7DF

MODE_CURRENT_DATA = 0x01
MODE_STORED_DTCS = 0x03
MODE_CLEAR_DTCS = 0x04
MODE_VEHICLE_INFO = 0x09
PID_VIN = 0x02


class Obd2Error(Exception):
    pass


class Obd2Session:
    def __init__(self, bus: can.BusABC, response_id: int = 0x7E8, timeout: float = 0.2):
        addr = isotp.Address(isotp.AddressingMode.Normal_11bits, txid=REQUEST_ID, rxid=response_id)
        self._stack = isotp.CanStack(bus, address=addr)
        self._timeout = timeout
        self._stack.start()

    def close(self) -> None:
        self._stack.stop()

    def _request(self, payload: bytes) -> bytes:
        self._stack.send(payload)
        response = self._stack.recv(block=True, timeout=self._timeout)
        if response is None:
            raise Obd2Error(f"No response to request {payload.hex()}")
        return bytes(response)

    def read_pid(self, pid: int) -> bytes:
        response = self._request(bytes([MODE_CURRENT_DATA, pid]))
        if len(response) < 3 or response[0] != MODE_CURRENT_DATA + 0x40 or response[1] != pid:
            raise Obd2Error(f"Unexpected PID response: {response.hex()}")
        return response[2:]

    def read_dtcs(self) -> bytes:
        response = self._request(bytes([MODE_STORED_DTCS]))
        if len(response) < 2 or response[0] != MODE_STORED_DTCS + 0x40:
            raise Obd2Error(f"Unexpected DTC response: {response.hex()}")
        return response[2:]  # skip mode byte and DTC-count byte

    def clear_dtcs(self) -> None:
        response = self._request(bytes([MODE_CLEAR_DTCS]))
        if len(response) < 1 or response[0] != MODE_CLEAR_DTCS + 0x40:
            raise Obd2Error(f"Unexpected clear-DTC response: {response.hex()}")

    def read_vin(self) -> str:
        response = self._request(bytes([MODE_VEHICLE_INFO, PID_VIN]))
        if len(response) < 3 or response[0] != MODE_VEHICLE_INFO + 0x40 or response[1] != PID_VIN:
            raise Obd2Error(f"Unexpected VIN response: {response.hex()}")
        raw = response[3:]
        return raw.decode("ascii", errors="ignore").strip("\x00").strip()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_obd2.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add jcan/obd2.py tests/test_obd2.py
git commit -m "feat: OBD2 Mode 01/03/04/09 session over ISO-TP"
```

---

### Task 6: Fake ECU simulator

**Files:**
- Create: `jcan/simulator.py`
- Test: `tests/test_simulator.py`

- [ ] **Step 1: Write the failing test**

`tests/test_simulator.py`:
```python
from jcan.can_transport import create_bus
from jcan.dtc import decode_dtcs
from jcan.obd2 import Obd2Session
from jcan.simulator import FAKE_VIN, Simulator


def _make_session(channel):
    bus_sim = create_bus("virtual", channel)
    bus_client = create_bus("virtual", channel)
    sim = Simulator(bus_sim)
    sim.start()
    session = Obd2Session(bus_client, timeout=1.0)
    return sim, session, bus_sim, bus_client


def test_simulator_rpm_pid():
    sim, session, bus_sim, bus_client = _make_session("sim-test-1")
    try:
        data = session.read_pid(0x0C)
        rpm = ((data[0] * 256) + data[1]) / 4
        assert 3000 <= rpm <= 4000
    finally:
        session.close()
        sim.stop()
        bus_sim.shutdown()
        bus_client.shutdown()


def test_simulator_vin():
    sim, session, bus_sim, bus_client = _make_session("sim-test-2")
    try:
        assert session.read_vin() == FAKE_VIN
    finally:
        session.close()
        sim.stop()
        bus_sim.shutdown()
        bus_client.shutdown()


def test_simulator_dtcs_then_clear():
    sim, session, bus_sim, bus_client = _make_session("sim-test-3")
    try:
        codes = decode_dtcs(session.read_dtcs())
        assert codes == ["P0133", "P0301"]

        session.clear_dtcs()

        assert decode_dtcs(session.read_dtcs()) == []
    finally:
        session.close()
        sim.stop()
        bus_sim.shutdown()
        bus_client.shutdown()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_simulator.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'jcan.simulator'`

- [ ] **Step 3: Implement simulator.py**

`jcan/simulator.py`:
```python
import sys
import threading
import time

import can
import isotp

SIM_RESPONSE_ID = 0x7E8
SIM_REQUEST_ID = 0x7DF

FAKE_VIN = "1HGCM82633A004352"
FAKE_DTCS = [(0x01, 0x33), (0x03, 0x01)]  # P0133, P0301


class Simulator:
    def __init__(self, bus: can.BusABC):
        addr = isotp.Address(isotp.AddressingMode.Normal_11bits, txid=SIM_RESPONSE_ID, rxid=SIM_REQUEST_ID)
        self._stack = isotp.CanStack(bus, address=addr)
        self._dtcs_cleared = False
        self._rpm_phase = 0
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._stack.start()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=1.0)
        self._stack.stop()

    def _run(self) -> None:
        while not self._stop_event.is_set():
            request = self._stack.recv(block=True, timeout=0.2)
            if request is None:
                continue
            response = self._handle(bytes(request))
            if response is not None:
                self._stack.send(response)

    def _handle(self, request: bytes) -> bytes | None:
        if not request:
            return None
        mode = request[0]
        if mode == 0x01 and len(request) >= 2:
            return self._handle_pid(request[1])
        if mode == 0x03:
            return self._handle_read_dtcs()
        if mode == 0x04:
            self._dtcs_cleared = True
            return bytes([0x44])
        if mode == 0x09 and len(request) >= 2 and request[1] == 0x02:
            return self._handle_vin()
        return None

    def _handle_pid(self, pid: int) -> bytes | None:
        if pid == 0x0C:
            self._rpm_phase += 1
            rpm_raw = 3000 + (self._rpm_phase % 10) * 100
            a, b = divmod(rpm_raw * 4, 256)
            return bytes([0x41, pid, a, b])
        if pid == 0x0D:
            return bytes([0x41, pid, 60])
        if pid == 0x05:
            return bytes([0x41, pid, 40 + 90])
        if pid == 0x0F:
            return bytes([0x41, pid, 40 + 25])
        if pid in (0x11, 0x04):
            return bytes([0x41, pid, 128])
        return None

    def _handle_read_dtcs(self) -> bytes:
        if self._dtcs_cleared:
            return bytes([0x43, 0x00])
        payload = bytearray([0x43, len(FAKE_DTCS)])
        for b1, b2 in FAKE_DTCS:
            payload += bytes([b1, b2])
        return bytes(payload)

    def _handle_vin(self) -> bytes:
        return bytes([0x49, 0x02, 0x01]) + FAKE_VIN.encode("ascii")


def main() -> None:
    channel = sys.argv[1] if len(sys.argv) > 1 else "jcan-sim"
    bus = can.Bus(interface="virtual", channel=channel, receive_own_messages=False)
    sim = Simulator(bus)
    sim.start()
    print(f"Simulator running on virtual channel '{channel}'. Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        sim.stop()
        bus.shutdown()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_simulator.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add jcan/simulator.py tests/test_simulator.py
git commit -m "feat: fake ECU simulator on a virtual CAN bus"
```

---

### Task 7: History database

**Files:**
- Create: `jcan/history_db.py`
- Test: `tests/test_history_db.py`

- [ ] **Step 1: Write the failing test**

`tests/test_history_db.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_history_db.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'jcan.history_db'`

- [ ] **Step 3: Implement history_db.py**

`jcan/history_db.py`:
```python
import sqlite3
from datetime import datetime, timezone


class HistoryDB:
    def __init__(self, path: str):
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS dtc_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL,
                description TEXT NOT NULL,
                vin TEXT,
                first_seen TEXT NOT NULL,
                cleared_at TEXT,
                notes TEXT NOT NULL DEFAULT ''
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS vehicles (
                vin TEXT PRIMARY KEY,
                make TEXT NOT NULL,
                model TEXT NOT NULL,
                year TEXT NOT NULL,
                decoded_at TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

    def record_active_codes(self, codes: list[tuple[str, str]], vin: str | None) -> None:
        now = datetime.now(timezone.utc).isoformat()
        existing = {
            row["code"]
            for row in self._conn.execute("SELECT code FROM dtc_events WHERE cleared_at IS NULL")
        }
        for code, description in codes:
            if code not in existing:
                self._conn.execute(
                    "INSERT INTO dtc_events (code, description, vin, first_seen, cleared_at, notes) "
                    "VALUES (?, ?, ?, ?, NULL, '')",
                    (code, description, vin, now),
                )
        self._conn.commit()

    def active_events(self) -> list[dict]:
        cur = self._conn.execute(
            """
            SELECT e.id, e.code, e.description, e.vin, e.first_seen, e.cleared_at, e.notes,
                   v.make, v.model, v.year
            FROM dtc_events e
            LEFT JOIN vehicles v ON v.vin = e.vin
            WHERE e.cleared_at IS NULL
            ORDER BY e.first_seen
            """
        )
        return [dict(row) for row in cur.fetchall()]

    def clear_active_events(self) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute("UPDATE dtc_events SET cleared_at = ? WHERE cleared_at IS NULL", (now,))
        self._conn.commit()

    def set_notes(self, event_id: int, notes: str) -> bool:
        cur = self._conn.execute("UPDATE dtc_events SET notes = ? WHERE id = ?", (notes, event_id))
        self._conn.commit()
        return cur.rowcount > 0

    def vehicles_view(self) -> list[dict]:
        cur = self._conn.execute(
            """
            SELECT DISTINCT e.vin AS vin, v.make, v.model, v.year, v.decoded_at
            FROM dtc_events e
            LEFT JOIN vehicles v ON v.vin = e.vin
            WHERE e.vin IS NOT NULL
            """
        )
        return [dict(row) for row in cur.fetchall()]

    def upsert_vehicle(self, vin: str, make: str, model: str, year: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """
            INSERT INTO vehicles (vin, make, model, year, decoded_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(vin) DO UPDATE SET
                make = excluded.make,
                model = excluded.model,
                year = excluded.year,
                decoded_at = excluded.decoded_at
            """,
            (vin, make, model, year, now),
        )
        self._conn.commit()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_history_db.py -v`
Expected: PASS (8 passed)

- [ ] **Step 5: Commit**

```bash
git add jcan/history_db.py tests/test_history_db.py
git commit -m "feat: SQLite history store for DTC events and decoded vehicles"
```

---

### Task 7b: DTC reference data seeded from a repo-committed JSON file

**Scope note:** this covers standard SAE meanings plus documented manufacturer-specific (P1xxx-range) code meanings for Honda and Mitsubishi — the makes of the 2008 Honda Accord, 2018 Mitsubishi Outlander Sport, and 2023 Honda Pilot. No speculative common-cause/repair guidance is included, only documented code meanings. This environment's web search tool is not returning live results (verified: it echoes general knowledge instead of real search hits), so this data comes from general automotive reference knowledge rather than a freshly verified source — treat it as a starting point and cross-check against the vehicles' actual service manuals before relying on it for repairs.

**Design change from the original Task 7b:** the reference data now lives in a JSON file committed to the repo (`jcan/seed_data/dtc_codes.json`), not as Python dicts. `HistoryDB` loads it into a new `dtc_reference` table on every init (upsert, so editing the JSON file always takes effect on next run — the file is the source of truth, the DB table is a queryable cache of it). DTC event descriptions are no longer stored on `dtc_events` at insert time — they're derived at *read* time in `active_events()` by joining `dtc_events` → `vehicles` (for the decoded make) → `dtc_reference` (preferring a manufacturer-specific row, falling back to the generic row). This means a code recorded before its VIN was decoded automatically shows the correct manufacturer-specific meaning once decoding happens later, with no backfill step. This task modifies the already-completed Task 3 (`jcan/dtc.py` loses its description lookup — decoding is pure byte math only) and Task 7 (`jcan/history_db.py` loses the `description` column and gains the reference table + join-time lookup).

**Files:**
- Modify: `jcan/dtc.py` (remove `describe_dtc`/`DTC_DESCRIPTIONS` — descriptions move to the DB)
- Modify: `jcan/history_db.py` (add `dtc_reference` table + seeding, drop `description` column from `dtc_events`, change `record_active_codes` signature, derive description in `active_events`)
- Create: `jcan/seed_data/dtc_codes.json`
- Test: `tests/test_dtc.py` (remove the now-obsolete `describe_dtc` tests)
- Test: `tests/test_history_db.py` (update existing tests for the new `record_active_codes` signature, add new description-derivation tests)

- [ ] **Step 1: Remove the description lookup from dtc.py**

Replace `jcan/dtc.py` entirely with:
```python
_TYPE_CHARS = {0b00: "P", 0b01: "C", 0b10: "B", 0b11: "U"}


def decode_dtc(byte1: int, byte2: int) -> str:
    type_char = _TYPE_CHARS[(byte1 >> 6) & 0b11]
    first_digit = (byte1 >> 4) & 0b11
    second_digit = byte1 & 0b1111
    third_digit = (byte2 >> 4) & 0b1111
    fourth_digit = byte2 & 0b1111
    return f"{type_char}{first_digit}{second_digit:X}{third_digit:X}{fourth_digit:X}"


def decode_dtcs(data: bytes) -> list[str]:
    codes = []
    for i in range(0, len(data) - 1, 2):
        b1, b2 = data[i], data[i + 1]
        if b1 == 0 and b2 == 0:
            continue
        codes.append(decode_dtc(b1, b2))
    return codes
```

Replace `tests/test_dtc.py` entirely with (drops the `describe_dtc`/`DTC_DESCRIPTIONS` tests, keeps the byte-decoding tests):
```python
from jcan.dtc import decode_dtc, decode_dtcs


def test_decode_single_dtc_powertrain():
    assert decode_dtc(0x01, 0x33) == "P0133"


def test_decode_dtc_chassis_type():
    assert decode_dtc(0x41, 0x00) == "C0100"


def test_decode_dtcs_skips_zero_padding():
    data = bytes([0x01, 0x33, 0x00, 0x00])
    assert decode_dtcs(data) == ["P0133"]


def test_decode_dtcs_multiple():
    data = bytes([0x01, 0x33, 0x03, 0x01])
    assert decode_dtcs(data) == ["P0133", "P0301"]


def test_decode_dtcs_empty():
    assert decode_dtcs(b"") == []
```

Run: `pytest tests/test_dtc.py -v`
Expected: PASS (5 passed)

- [ ] **Step 2: Add the seed data file**

Create `jcan/seed_data/dtc_codes.json` (no `__init__.py` needed — this is read as a plain data file, not imported as a package):
```json
[
  {"code": "P0101", "make": "", "description": "Mass or Volume Air Flow Circuit Range/Performance Problem"},
  {"code": "P0102", "make": "", "description": "Mass or Volume Air Flow Circuit Low Input"},
  {"code": "P0113", "make": "", "description": "Intake Air Temperature Circuit High Input"},
  {"code": "P0128", "make": "", "description": "Coolant Thermostat (Coolant Temperature Below Thermostat Regulating Temperature)"},
  {"code": "P0133", "make": "", "description": "O2 Sensor Circuit Slow Response (Bank 1 Sensor 1)"},
  {"code": "P0135", "make": "", "description": "O2 Sensor Heater Circuit Malfunction (Bank 1 Sensor 1)"},
  {"code": "P0300", "make": "", "description": "Random/Multiple Cylinder Misfire Detected"},
  {"code": "P0301", "make": "", "description": "Cylinder 1 Misfire Detected"},
  {"code": "P0302", "make": "", "description": "Cylinder 2 Misfire Detected"},
  {"code": "P0303", "make": "", "description": "Cylinder 3 Misfire Detected"},
  {"code": "P0304", "make": "", "description": "Cylinder 4 Misfire Detected"},
  {"code": "P0401", "make": "", "description": "Exhaust Gas Recirculation Flow Insufficient Detected"},
  {"code": "P0420", "make": "", "description": "Catalyst System Efficiency Below Threshold (Bank 1)"},
  {"code": "P0440", "make": "", "description": "Evaporative Emission Control System Malfunction"},
  {"code": "P0442", "make": "", "description": "Evaporative Emission Control System Leak Detected (Small Leak)"},
  {"code": "P0455", "make": "", "description": "Evaporative Emission Control System Leak Detected (Large Leak)"},
  {"code": "P0500", "make": "", "description": "Vehicle Speed Sensor Malfunction"},
  {"code": "P0505", "make": "", "description": "Idle Control System Malfunction"},
  {"code": "P0507", "make": "", "description": "Idle Air Control System RPM Higher Than Expected"},
  {"code": "P1259", "make": "Honda", "description": "VTEC System Malfunction"},
  {"code": "P1456", "make": "Honda", "description": "Evaporative Emission System Leak (Fuel Tank System)"},
  {"code": "P1457", "make": "Honda", "description": "Evaporative Emission System Leak Detected (Fuel Tank System or Canister System)"},
  {"code": "P1446", "make": "Mitsubishi", "description": "Evaporative Emission Control System Vent Control Valve Malfunction"}
]
```
`make: ""` means a generic/SAE-standard code (applies regardless of manufacturer). A non-empty `make` is a manufacturer-specific override, only used when a DTC event's vehicle has been decoded to that exact make.

- [ ] **Step 3: Write the failing tests for history_db.py's new behavior**

Replace `tests/test_history_db.py` entirely with:
```python
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
```

Run: `pytest tests/test_history_db.py -v`
Expected: FAIL — `TypeError` (old `record_active_codes` still expects `(code, description)` tuples), missing `description` key errors, etc. This confirms the old implementation needs to change.

- [ ] **Step 4: Rewrite history_db.py**

Replace `jcan/history_db.py` entirely with:
```python
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SEED_DATA_PATH = Path(__file__).parent / "seed_data" / "dtc_codes.json"


class HistoryDB:
    def __init__(self, path: str):
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()
        self._seed_dtc_reference()

    def _init_schema(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS dtc_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL,
                vin TEXT,
                first_seen TEXT NOT NULL,
                cleared_at TEXT,
                notes TEXT NOT NULL DEFAULT ''
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS vehicles (
                vin TEXT PRIMARY KEY,
                make TEXT NOT NULL,
                model TEXT NOT NULL,
                year TEXT NOT NULL,
                decoded_at TEXT NOT NULL
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS dtc_reference (
                code TEXT NOT NULL,
                make TEXT NOT NULL DEFAULT '',
                description TEXT NOT NULL,
                PRIMARY KEY (code, make)
            )
            """
        )
        self._conn.commit()

    def _seed_dtc_reference(self) -> None:
        entries = json.loads(SEED_DATA_PATH.read_text())
        for entry in entries:
            self._conn.execute(
                """
                INSERT INTO dtc_reference (code, make, description)
                VALUES (?, ?, ?)
                ON CONFLICT(code, make) DO UPDATE SET description = excluded.description
                """,
                (entry["code"], entry.get("make", ""), entry["description"]),
            )
        self._conn.commit()

    def record_active_codes(self, codes: list[str], vin: str | None) -> None:
        now = datetime.now(timezone.utc).isoformat()
        existing = {
            row["code"]
            for row in self._conn.execute("SELECT code FROM dtc_events WHERE cleared_at IS NULL")
        }
        for code in codes:
            if code not in existing:
                self._conn.execute(
                    "INSERT INTO dtc_events (code, vin, first_seen, cleared_at, notes) "
                    "VALUES (?, ?, ?, NULL, '')",
                    (code, vin, now),
                )
                existing.add(code)
        self._conn.commit()

    def active_events(self) -> list[dict]:
        cur = self._conn.execute(
            """
            SELECT e.id, e.code, e.vin, e.first_seen, e.cleared_at, e.notes,
                   v.make, v.model, v.year,
                   COALESCE(specific.description, generic.description, 'Unknown DTC') AS description
            FROM dtc_events e
            LEFT JOIN vehicles v ON v.vin = e.vin
            LEFT JOIN dtc_reference specific ON specific.code = e.code AND specific.make = v.make
            LEFT JOIN dtc_reference generic ON generic.code = e.code AND generic.make = ''
            WHERE e.cleared_at IS NULL
            ORDER BY e.first_seen, e.id
            """
        )
        return [dict(row) for row in cur.fetchall()]

    def clear_active_events(self) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute("UPDATE dtc_events SET cleared_at = ? WHERE cleared_at IS NULL", (now,))
        self._conn.commit()

    def set_notes(self, event_id: int, notes: str) -> bool:
        cur = self._conn.execute("UPDATE dtc_events SET notes = ? WHERE id = ?", (notes, event_id))
        self._conn.commit()
        return cur.rowcount > 0

    def vehicles_view(self) -> list[dict]:
        cur = self._conn.execute(
            """
            SELECT DISTINCT e.vin AS vin, v.make, v.model, v.year, v.decoded_at
            FROM dtc_events e
            LEFT JOIN vehicles v ON v.vin = e.vin
            WHERE e.vin IS NOT NULL
            """
        )
        return [dict(row) for row in cur.fetchall()]

    def upsert_vehicle(self, vin: str, make: str, model: str, year: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """
            INSERT INTO vehicles (vin, make, model, year, decoded_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(vin) DO UPDATE SET
                make = excluded.make,
                model = excluded.model,
                year = excluded.year,
                decoded_at = excluded.decoded_at
            """,
            (vin, make, model, year, now),
        )
        self._conn.commit()
```

Note two small fixes folded in here versus the original Task 7 implementation, both already flagged by the Task 7 code quality review: `record_active_codes` now adds each inserted code to `existing` inside the loop (so duplicate codes within a single call don't both get inserted), and `active_events`'s `ORDER BY` now includes `e.id` as a tiebreaker for deterministic ordering when timestamps collide.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_dtc.py tests/test_history_db.py -v`
Expected: PASS (5 in `test_dtc.py`, 14 in `test_history_db.py`)

- [ ] **Step 6: Run the full suite to confirm no regressions**

Run: `pytest -v`
Expected: all tests pass. (Count will differ from a simple sum of prior totals since this task nets out at 5 dtc tests, down from 7, and 14 history_db tests, up from 10.)

- [ ] **Step 7: Commit**

```bash
git add jcan/dtc.py jcan/history_db.py jcan/seed_data/dtc_codes.json tests/test_dtc.py tests/test_history_db.py
git commit -m "feat: seed DTC reference data from repo JSON, derive descriptions at read time"
```

---

### Task 8: VIN decoder

**Files:**
- Create: `jcan/vin_decoder.py`
- Test: `tests/test_vin_decoder.py`

- [ ] **Step 1: Write the failing test**

`tests/test_vin_decoder.py`:
```python
import requests
import pytest

from jcan.vin_decoder import VinDecodeError, decode_vin


class FakeResponse:
    def __init__(self, json_data, status_code=200):
        self._json = json_data
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"status {self.status_code}")

    def json(self):
        return self._json


def test_decode_vin_success():
    def fake_get(url, timeout):
        return FakeResponse({"Results": [{"Make": "Honda", "Model": "Civic", "ModelYear": "2018"}]})

    result = decode_vin("1HGCM82633A004352", http_get=fake_get)
    assert result == {"make": "Honda", "model": "Civic", "year": "2018"}


def test_decode_vin_not_found_raises():
    def fake_get(url, timeout):
        return FakeResponse({"Results": [{"Make": "", "Model": "", "ModelYear": ""}]})

    with pytest.raises(VinDecodeError):
        decode_vin("00000000000000000", http_get=fake_get)


def test_decode_vin_network_error_raises():
    def fake_get(url, timeout):
        raise requests.ConnectionError("no network")

    with pytest.raises(VinDecodeError):
        decode_vin("1HGCM82633A004352", http_get=fake_get)


def test_decode_vin_http_error_raises():
    def fake_get(url, timeout):
        return FakeResponse({}, status_code=500)

    with pytest.raises(VinDecodeError):
        decode_vin("1HGCM82633A004352", http_get=fake_get)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_vin_decoder.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'jcan.vin_decoder'`

- [ ] **Step 3: Implement vin_decoder.py**

`jcan/vin_decoder.py`:
```python
import requests

NHTSA_URL = "https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValues/{vin}?format=json"


class VinDecodeError(Exception):
    pass


def decode_vin(vin: str, http_get=requests.get) -> dict:
    try:
        response = http_get(NHTSA_URL.format(vin=vin), timeout=5)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise VinDecodeError(f"VIN decode request failed: {exc}") from exc

    data = response.json()
    results = data.get("Results") or []
    if not results:
        raise VinDecodeError("No decode results returned")

    result = results[0]
    make = result.get("Make") or ""
    model = result.get("Model") or ""
    year = result.get("ModelYear") or ""
    if not make:
        raise VinDecodeError("VIN could not be decoded (no make returned)")

    return {"make": make, "model": model, "year": year}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_vin_decoder.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add jcan/vin_decoder.py tests/test_vin_decoder.py
git commit -m "feat: NHTSA vPIC VIN decoder"
```

---

### Task 8b: Store and display the full raw VIN decode response

**Design change:** NHTSA's vPIC API returns roughly 150 fields per VIN (trim, engine, body class, GVWR, etc.), not just make/model/year. Rather than discarding everything except those three summary fields, the full raw response is kept — stored in the database and shown in full on the Vehicles tab (Task 11). This modifies the already-shipped `jcan/vin_decoder.py` (Task 8) and `jcan/history_db.py` (Tasks 7/7b).

**Files:**
- Modify: `jcan/vin_decoder.py` (`decode_vin` also returns the raw result dict)
- Modify: `jcan/history_db.py` (`vehicles` table gains `raw_json`, `upsert_vehicle` accepts it, `vehicles_view` returns it)
- Test: `tests/test_vin_decoder.py` (update the success test)
- Test: `tests/test_history_db.py` (update vehicle-related tests)

- [ ] **Step 1: Update vin_decoder.py and its test**

Replace the `test_decode_vin_success` function in `tests/test_vin_decoder.py` with:
```python
def test_decode_vin_success():
    def fake_get(url, timeout):
        return FakeResponse({
            "Results": [{"Make": "Honda", "Model": "Civic", "ModelYear": "2018", "Trim": "EX"}]
        })

    result = decode_vin("1HGCM82633A004352", http_get=fake_get)
    assert result["make"] == "Honda"
    assert result["model"] == "Civic"
    assert result["year"] == "2018"
    assert result["raw"]["Trim"] == "EX"
```
(Leave the other 3 tests in that file untouched.)

In `jcan/vin_decoder.py`, change the final `return` statement in `decode_vin` from:
```python
    return {"make": make, "model": model, "year": year}
```
to:
```python
    return {"make": make, "model": model, "year": year, "raw": result}
```
No other changes to that file.

Run: `pytest tests/test_vin_decoder.py -v`
Expected: PASS (4 passed)

- [ ] **Step 2: Write the failing tests for history_db.py's raw_json handling**

In `tests/test_history_db.py`, update these three existing calls to `upsert_vehicle` to also pass a `raw_json` argument, and add one new test. Replace:
```python
def test_upsert_vehicle_then_view_shows_decoded_info():
    db = _db()
    db.record_active_codes(["P0301"], vin="VIN123")
    db.upsert_vehicle("VIN123", "Honda", "Civic", "2018")
    rows = db.vehicles_view()
    assert rows[0]["make"] == "Honda"
    assert rows[0]["model"] == "Civic"
    assert rows[0]["year"] == "2018"
```
with:
```python
def test_upsert_vehicle_then_view_shows_decoded_info():
    db = _db()
    db.record_active_codes(["P0301"], vin="VIN123")
    db.upsert_vehicle("VIN123", "Honda", "Civic", "2018", raw_json='{"Trim": "EX"}')
    rows = db.vehicles_view()
    assert rows[0]["make"] == "Honda"
    assert rows[0]["model"] == "Civic"
    assert rows[0]["year"] == "2018"
    assert rows[0]["raw_json"] == '{"Trim": "EX"}'


def test_vehicles_view_raw_json_is_none_when_undecoded():
    db = _db()
    db.record_active_codes(["P0301"], vin="VIN123")
    rows = db.vehicles_view()
    assert rows[0]["raw_json"] is None
```
Leave `test_upsert_vehicle_updates_existing_row` as-is (it doesn't pass `raw_json`, relying on the default).

Run: `pytest tests/test_history_db.py -v`
Expected: FAIL — `rows[0]["raw_json"]` doesn't exist yet (old `vehicles_view` doesn't select it), and `upsert_vehicle` doesn't accept a `raw_json` keyword yet.

- [ ] **Step 3: Update history_db.py**

In `jcan/history_db.py`, replace the `vehicles` table definition inside `_init_schema`:
```python
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS vehicles (
                vin TEXT PRIMARY KEY,
                make TEXT NOT NULL,
                model TEXT NOT NULL,
                year TEXT NOT NULL,
                raw_json TEXT NOT NULL DEFAULT '{}',
                decoded_at TEXT NOT NULL
            )
            """
        )
```

Replace `vehicles_view`:
```python
    def vehicles_view(self) -> list[dict]:
        cur = self._conn.execute(
            """
            SELECT DISTINCT e.vin AS vin, v.make, v.model, v.year, v.raw_json, v.decoded_at
            FROM dtc_events e
            LEFT JOIN vehicles v ON v.vin = e.vin
            WHERE e.vin IS NOT NULL
            """
        )
        return [dict(row) for row in cur.fetchall()]
```

Replace `upsert_vehicle` (note the new `raw_json` parameter, defaulted so existing callers that don't care about it still work):
```python
    def upsert_vehicle(self, vin: str, make: str, model: str, year: str, raw_json: str = "{}") -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """
            INSERT INTO vehicles (vin, make, model, year, raw_json, decoded_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(vin) DO UPDATE SET
                make = excluded.make,
                model = excluded.model,
                year = excluded.year,
                raw_json = excluded.raw_json,
                decoded_at = excluded.decoded_at
            """,
            (vin, make, model, year, raw_json, now),
        )
        self._conn.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_history_db.py tests/test_vin_decoder.py -v`
Expected: PASS (16 in `test_history_db.py` — 14 prior + 2 new, 4 in `test_vin_decoder.py`)

- [ ] **Step 5: Run the full suite to confirm no regressions**

Run: `pytest -v`
Expected: all tests pass (46 total: 44 before this task + 2 new).

- [ ] **Step 6: Commit**

```bash
git add jcan/vin_decoder.py jcan/history_db.py tests/test_vin_decoder.py tests/test_history_db.py
git commit -m "feat: store and expose full raw VIN decode response, not just make/model/year"
```

---

### Task 9: Background reader thread

**Files:**
- Create: `jcan/reader.py`
- Test: `tests/test_reader.py`

- [ ] **Step 1: Write the failing test**

`tests/test_reader.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_reader.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'jcan.reader'`

- [ ] **Step 3: Implement reader.py**

`jcan/reader.py`:
```python
import queue
import threading
import time
from dataclasses import dataclass
from typing import Callable

import can

from . import pids as pids_module
from .dtc import decode_dtcs
from .obd2 import Obd2Error, Obd2Session


@dataclass
class _Command:
    action: str
    result: "queue.Queue"


class Reader:
    def __init__(self, bus: can.BusABC, poll_interval_s: float, pid_timeout_s: float):
        self._bus = bus
        self._poll_interval_s = poll_interval_s
        self._pid_timeout_s = pid_timeout_s
        self._commands: "queue.Queue[_Command]" = queue.Queue()
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self.current_vin: str | None = None
        self.on_reading: Callable[[str, float, str], None] = lambda *_: None
        self.on_status: Callable[[str], None] = lambda *_: None

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._thread.join(timeout=2.0)

    def submit(self, action: str) -> "queue.Queue":
        result: "queue.Queue" = queue.Queue(maxsize=1)
        self._commands.put(_Command(action=action, result=result))
        return result

    def _run(self) -> None:
        try:
            session = Obd2Session(self._bus, timeout=self._pid_timeout_s)
        except Exception as exc:
            self.on_status(f"connect_failed: {exc}")
            return

        try:
            self.current_vin = session.read_vin()
        except Obd2Error:
            self.current_vin = None
            self.on_status("vin_read_failed")

        self.on_status("connected")
        last_poll = 0.0
        try:
            while not self._stop_event.is_set():
                self._drain_one_command(session)
                now = time.monotonic()
                if now - last_poll >= self._poll_interval_s:
                    self._poll_once(session)
                    last_poll = now
                else:
                    time.sleep(0.05)
        except Exception as exc:
            self.on_status(f"lost: {exc}")
        finally:
            session.close()

    def _drain_one_command(self, session: Obd2Session) -> None:
        try:
            command = self._commands.get_nowait()
        except queue.Empty:
            return
        try:
            if command.action == "read_dtcs":
                codes = decode_dtcs(session.read_dtcs())
                command.result.put(("ok", codes))
            elif command.action == "clear_dtcs":
                session.clear_dtcs()
                command.result.put(("ok", None))
        except Obd2Error as exc:
            command.result.put(("error", str(exc)))

    def _poll_once(self, session: Obd2Session) -> None:
        for pid_def in pids_module.LIVE_PIDS:
            try:
                raw = session.read_pid(pid_def.pid)
                value = pid_def.decode(raw)
                self.on_reading(pid_def.name, value, pid_def.unit)
            except Obd2Error:
                continue
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_reader.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add jcan/reader.py tests/test_reader.py
git commit -m "feat: background reader thread with VIN read, PID polling, DTC commands"
```

---

### Task 10: FastAPI web app

**Files:**
- Create: `jcan/web.py`
- Test: `tests/test_web.py`

- [ ] **Step 1: Write the failing test**

`tests/test_web.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_web.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'jcan.web'`

- [ ] **Step 3: Implement web.py**

`jcan/web.py`:
```python
import asyncio
import json
import queue as queue_module

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .history_db import HistoryDB
from .vin_decoder import VinDecodeError, decode_vin


class NotesUpdate(BaseModel):
    notes: str


async def _broadcast(clients: set, message: str) -> None:
    dead = []
    for ws in list(clients):
        try:
            await ws.send_text(message)
        except Exception:
            dead.append(ws)
    for ws in dead:
        clients.discard(ws)


def create_app(reader, db: HistoryDB, static_dir: str) -> FastAPI:
    app = FastAPI()
    clients: set = set()

    @app.on_event("startup")
    async def _on_startup():
        loop = asyncio.get_running_loop()

        def on_reading(name: str, value: float, unit: str) -> None:
            message = json.dumps({"type": "reading", "pid": name, "value": value, "unit": unit})
            asyncio.run_coroutine_threadsafe(_broadcast(clients, message), loop)

        def on_status(status: str) -> None:
            message = json.dumps({"type": "status", "status": status})
            asyncio.run_coroutine_threadsafe(_broadcast(clients, message), loop)

        reader.on_reading = on_reading
        reader.on_status = on_status
        reader.start()

    @app.on_event("shutdown")
    async def _on_shutdown():
        reader.stop()

    @app.websocket("/ws")
    async def ws_endpoint(websocket: WebSocket):
        await websocket.accept()
        clients.add(websocket)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            clients.discard(websocket)

    @app.get("/dtcs")
    async def get_dtcs():
        result_queue = reader.submit("read_dtcs")
        try:
            status, payload = await asyncio.to_thread(result_queue.get, True, 5.0)
        except queue_module.Empty:
            raise HTTPException(status_code=503, detail="No response from vehicle")
        if status == "error":
            raise HTTPException(status_code=503, detail=payload)
        db.record_active_codes(payload, reader.current_vin)
        return db.active_events()

    @app.post("/dtcs/clear")
    async def clear_dtcs():
        result_queue = reader.submit("clear_dtcs")
        try:
            status, payload = await asyncio.to_thread(result_queue.get, True, 5.0)
        except queue_module.Empty:
            raise HTTPException(status_code=503, detail="No response from vehicle")
        if status == "error":
            raise HTTPException(status_code=503, detail=payload)
        db.clear_active_events()
        return {"cleared": True}

    @app.patch("/dtcs/{event_id}/notes")
    async def update_notes(event_id: int, body: NotesUpdate):
        updated = db.set_notes(event_id, body.notes)
        if not updated:
            raise HTTPException(status_code=404, detail="Event not found")
        return {"id": event_id, "notes": body.notes}

    @app.get("/vehicles")
    async def get_vehicles():
        rows = db.vehicles_view()
        for row in rows:
            raw_json = row.pop("raw_json")
            row["raw"] = json.loads(raw_json) if raw_json else None
        return rows

    @app.post("/vehicles/{vin}/decode")
    async def decode_vehicle(vin: str):
        try:
            decoded = await asyncio.to_thread(decode_vin, vin)
        except VinDecodeError as exc:
            raise HTTPException(status_code=502, detail=str(exc))
        db.upsert_vehicle(
            vin, decoded["make"], decoded["model"], decoded["year"], json.dumps(decoded["raw"])
        )
        return {"vin": vin, "make": decoded["make"], "model": decoded["model"],
                "year": decoded["year"], "raw": decoded["raw"]}

    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/")
    async def index():
        return FileResponse(f"{static_dir}/index.html")

    return app
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_web.py -v`
Expected: PASS (8 passed)

- [ ] **Step 5: Commit**

```bash
git add jcan/web.py tests/test_web.py
git commit -m "feat: FastAPI app with WebSocket gauge stream and DTC/vehicle REST endpoints"
```

---

### Task 11: Frontend (Gauges / Diagnostics / Vehicles tabs)

**Files:**
- Modify: `jcan/static/index.html` (replace placeholder)
- Create: `jcan/static/app.js`
- Create: `jcan/static/style.css`

- [ ] **Step 1: Write the full HTML**

`jcan/static/index.html`:
```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>jcan</title>
  <link rel="stylesheet" href="/static/style.css">
</head>
<body>
  <header>
    <h1>jcan</h1>
    <nav>
      <button class="tab-button active" data-tab="gauges">Gauges</button>
      <button class="tab-button" data-tab="diagnostics">Diagnostics</button>
      <button class="tab-button" data-tab="vehicles">Vehicles</button>
    </nav>
    <div id="connection-banner" class="banner hidden"></div>
  </header>

  <section id="tab-gauges" class="tab active">
    <div id="gauges"></div>
  </section>

  <section id="tab-diagnostics" class="tab">
    <button id="refresh-dtcs">Refresh Codes</button>
    <button id="clear-dtcs">Clear Codes</button>
    <table id="dtc-table">
      <thead>
        <tr><th>Code</th><th>Description</th><th>VIN / Vehicle</th><th>First Seen</th><th>Notes</th></tr>
      </thead>
      <tbody></tbody>
    </table>
  </section>

  <section id="tab-vehicles" class="tab">
    <table id="vehicle-table">
      <thead>
        <tr><th>VIN</th><th>Make</th><th>Model</th><th>Year</th><th>Full Data</th><th></th></tr>
      </thead>
      <tbody></tbody>
    </table>
  </section>

  <dialog id="confirm-clear-dialog">
    <p>Clear all stored diagnostic codes from the vehicle?</p>
    <button id="confirm-clear-yes">Yes, clear codes</button>
    <button id="confirm-clear-no">Cancel</button>
  </dialog>

  <script src="/static/app.js"></script>
</body>
</html>
```

- [ ] **Step 2: Write the JS**

`jcan/static/app.js`:
```javascript
const PID_LABELS = {
  rpm: "RPM",
  speed: "Speed",
  coolant_temp: "Coolant Temp",
  throttle_position: "Throttle Position",
  engine_load: "Engine Load",
  intake_air_temp: "Intake Air Temp",
};

function setupTabs() {
  const buttons = document.querySelectorAll(".tab-button");
  buttons.forEach((button) => {
    button.addEventListener("click", () => {
      buttons.forEach((b) => b.classList.remove("active"));
      document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
      button.classList.add("active");
      document.getElementById(`tab-${button.dataset.tab}`).classList.add("active");
      if (button.dataset.tab === "diagnostics") loadDtcs();
      if (button.dataset.tab === "vehicles") loadVehicles();
    });
  });
}

function renderGauge(pid, value, unit) {
  let el = document.getElementById(`gauge-${pid}`);
  if (!el) {
    el = document.createElement("div");
    el.id = `gauge-${pid}`;
    el.className = "gauge";
    el.innerHTML = `<div class="gauge-label">${PID_LABELS[pid] || pid}</div><div class="gauge-value"></div>`;
    document.getElementById("gauges").appendChild(el);
  }
  el.dataset.lastUpdate = Date.now();
  el.querySelector(".gauge-value").textContent = `${value} ${unit}`;
  el.classList.remove("stale");
}

function markStaleGauges() {
  const now = Date.now();
  document.querySelectorAll(".gauge").forEach((el) => {
    if (now - Number(el.dataset.lastUpdate || 0) > 5000) {
      el.classList.add("stale");
    }
  });
}

function setupWebSocket() {
  const ws = new WebSocket(`ws://${location.host}/ws`);
  ws.onmessage = (event) => {
    const message = JSON.parse(event.data);
    if (message.type === "reading") {
      renderGauge(message.pid, message.value, message.unit);
    } else if (message.type === "status") {
      showConnectionStatus(message.status);
    }
  };
  setInterval(markStaleGauges, 1000);
}

function showConnectionStatus(status) {
  const banner = document.getElementById("connection-banner");
  if (status === "connected") {
    banner.classList.add("hidden");
    return;
  }
  banner.textContent = `Connection issue: ${status}`;
  banner.classList.remove("hidden");
}

function vehicleLabel(row) {
  if (row.make) {
    return `${row.year} ${row.make} ${row.model}`.trim();
  }
  return row.vin || "";
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

async function loadDtcs() {
  const response = await fetch("/dtcs");
  const events = await response.json();
  const tbody = document.querySelector("#dtc-table tbody");
  tbody.innerHTML = "";
  for (const event of events) {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td>${event.code}</td>
      <td>${event.description}</td>
      <td>${vehicleLabel(event)}</td>
      <td>${event.first_seen}</td>
      <td><textarea data-id="${event.id}">${event.notes || ""}</textarea></td>
    `;
    tbody.appendChild(row);
  }
  tbody.querySelectorAll("textarea").forEach((textarea) => {
    textarea.addEventListener("blur", async () => {
      await fetch(`/dtcs/${textarea.dataset.id}/notes`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ notes: textarea.value }),
      });
    });
  });
}

async function loadVehicles() {
  const response = await fetch("/vehicles");
  const vehicles = await response.json();
  const tbody = document.querySelector("#vehicle-table tbody");
  tbody.innerHTML = "";
  for (const vehicle of vehicles) {
    const row = document.createElement("tr");
    const decodedCell = vehicle.make
      ? ""
      : `<button class="decode-button" data-vin="${vehicle.vin}">Decode VIN</button>`;
    const rawCell = vehicle.raw
      ? `<details><summary>View</summary><pre>${escapeHtml(JSON.stringify(vehicle.raw, null, 2))}</pre></details>`
      : "";
    row.innerHTML = `
      <td>${vehicle.vin}</td>
      <td>${vehicle.make || ""}</td>
      <td>${vehicle.model || ""}</td>
      <td>${vehicle.year || ""}</td>
      <td>${rawCell}</td>
      <td>${decodedCell}</td>
    `;
    tbody.appendChild(row);
  }
  tbody.querySelectorAll(".decode-button").forEach((button) => {
    button.addEventListener("click", async () => {
      button.disabled = true;
      button.textContent = "Decoding...";
      const response = await fetch(`/vehicles/${button.dataset.vin}/decode`, { method: "POST" });
      if (response.ok) {
        await loadVehicles();
      } else {
        button.disabled = false;
        button.textContent = "Decode VIN (failed, retry)";
      }
    });
  });
}

function setupDiagnosticsControls() {
  document.getElementById("refresh-dtcs").addEventListener("click", loadDtcs);
  const dialog = document.getElementById("confirm-clear-dialog");
  document.getElementById("clear-dtcs").addEventListener("click", () => dialog.showModal());
  document.getElementById("confirm-clear-no").addEventListener("click", () => dialog.close());
  document.getElementById("confirm-clear-yes").addEventListener("click", async () => {
    dialog.close();
    await fetch("/dtcs/clear", { method: "POST" });
    await loadDtcs();
  });
}

setupTabs();
setupWebSocket();
setupDiagnosticsControls();
loadDtcs();
```

- [ ] **Step 3: Write the CSS**

`jcan/static/style.css`:
```css
body { font-family: system-ui, sans-serif; margin: 0; padding: 0 1rem; }
header { display: flex; align-items: center; gap: 1rem; flex-wrap: wrap; }
nav { display: flex; gap: 0.5rem; }
.tab-button { padding: 0.5rem 1rem; cursor: pointer; }
.tab-button.active { font-weight: bold; }
.tab { display: none; }
.tab.active { display: block; }
.banner { background: #c0392b; color: white; padding: 0.5rem; border-radius: 4px; }
.banner.hidden { display: none; }
#gauges { display: flex; flex-wrap: wrap; gap: 1rem; }
.gauge { border: 1px solid #ccc; border-radius: 8px; padding: 1rem; min-width: 150px; }
.gauge.stale { opacity: 0.4; }
.gauge-label { font-size: 0.9rem; color: #555; }
.gauge-value { font-size: 1.8rem; font-weight: bold; }
table { border-collapse: collapse; width: 100%; margin-top: 1rem; }
th, td { border: 1px solid #ccc; padding: 0.5rem; text-align: left; }
textarea { width: 100%; min-height: 3rem; }
#vehicle-table pre { max-width: 40rem; max-height: 20rem; overflow: auto; background: #f5f5f5; padding: 0.5rem; }
```

- [ ] **Step 4: Manually verify in a browser**

Run (terminal 1): `python -m jcan.simulator`
Run (terminal 2): `JCAN_BUS_TYPE=virtual JCAN_CHANNEL=jcan-sim python -m jcan.main` (Task 12 creates `main.py` — come back to this step after Task 12, or skip ahead and run it then)
Open: `http://127.0.0.1:8000/` and confirm: Gauges tab shows moving RPM/speed/etc., Diagnostics tab lists P0133/P0301 with editable notes and a working Clear Codes confirmation, Vehicles tab shows the VIN with a working Decode VIN button and, once decoded, an expandable "Full Data" section showing the complete raw NHTSA response.

- [ ] **Step 5: Commit**

```bash
git add jcan/static/index.html jcan/static/app.js jcan/static/style.css
git commit -m "feat: Gauges/Diagnostics/Vehicles frontend"
```

---

### Task 12: Entrypoint wiring

**Files:**
- Create: `jcan/main.py`

- [ ] **Step 1: Implement main.py**

`jcan/main.py`:
```python
import uvicorn

from .can_transport import create_bus
from .config import Config
from .history_db import HistoryDB
from .reader import Reader
from .web import create_app


def main() -> None:
    cfg = Config.from_env()
    bus = create_bus(cfg.bus_type, cfg.channel)
    db = HistoryDB(cfg.db_path)
    reader = Reader(bus, poll_interval_s=cfg.poll_interval_s, pid_timeout_s=cfg.pid_timeout_s)
    app = create_app(reader, db, static_dir="jcan/static")
    uvicorn.run(app, host=cfg.http_host, port=cfg.http_port)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Manually smoke-test end to end (no hardware)**

Run (terminal 1): `python -m jcan.simulator`
Run (terminal 2):
```bash
JCAN_BUS_TYPE=virtual JCAN_CHANNEL=jcan-sim python -m jcan.main
```
Open: `http://127.0.0.1:8000/` and confirm all three tabs work (same checks as Task 11 Step 4). `Ctrl+C` both terminals when done.

Note the fail-fast behavior for real hardware: `create_bus("slcan", "/dev/tty.nonexistent")` raises immediately from `can.Bus(...)` (pyserial's error names the bad port) before the web server ever starts — this is what gives the "fail fast with a clear error naming the configured port" behavior from the design's error handling section, with no extra code needed.

- [ ] **Step 3: Commit**

```bash
git add jcan/main.py
git commit -m "feat: service entrypoint wiring config, bus, db, reader, and web app"
```

---

### Task 13: Full integration test

**Files:**
- Create: `tests/test_integration.py`

- [ ] **Step 1: Write the integration test**

`tests/test_integration.py`:
```python
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
            time.sleep(0.5)  # let the reader connect and read the VIN

            with client.websocket_connect("/ws") as websocket:
                message = websocket.receive_json()
                assert message["type"] in ("reading", "status")

            dtcs_response = client.get("/dtcs")
            assert dtcs_response.status_code == 200
            events = dtcs_response.json()
            codes = {event["code"] for event in events}
            assert codes == {"P0133", "P0301"}
            assert all(event["vin"] == FAKE_VIN for event in events)

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
```

- [ ] **Step 2: Run the full test suite**

Run: `pytest -v`
Expected: all tests across every module pass, including this integration test (roughly 45+ passed).

- [ ] **Step 3: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: full end-to-end integration test against the simulator"
```

---

### Task 14: README

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write the README**

`README.md`:
```markdown
# jcan

Personal OBD-II diagnostic tool. Reads live engine data and trouble codes over
CAN, stores DTC history in SQLite, and serves a browser UI.

## Setup

    pip install -e ".[dev]"

## Run without hardware (simulator)

Terminal 1:

    python -m jcan.simulator

Terminal 2:

    JCAN_BUS_TYPE=virtual JCAN_CHANNEL=jcan-sim python -m jcan.main

Open http://127.0.0.1:8000/

## Run with real hardware

Flash a CAN-to-USB dongle (e.g. CANable 2.0) to slcan firmware, plug it into
the OBD-II port's CAN H/L pins (see `docs/hardware-obd2-wiring.md`), then:

    JCAN_BUS_TYPE=slcan JCAN_CHANNEL=/dev/tty.usbmodemXXXX python -m jcan.main

Replace `/dev/tty.usbmodemXXXX` with the actual serial device for your dongle
(check `ls /dev/tty.*` before and after plugging it in). If the port is wrong,
`jcan` fails immediately at startup with an error naming the bad path.

## Configuration (environment variables)

| Variable               | Default      | Meaning                              |
|-------------------------|--------------|---------------------------------------|
| `JCAN_BUS_TYPE`         | `virtual`    | `slcan` (real hardware) or `virtual`  |
| `JCAN_CHANNEL`          | `jcan-sim`   | Serial port (slcan) or channel name (virtual) |
| `JCAN_POLL_INTERVAL_S`  | `1.0`        | Seconds between live-gauge poll cycles |
| `JCAN_PID_TIMEOUT_S`    | `0.2`        | Per-request timeout waiting on the ECU |
| `JCAN_DB_PATH`          | `jcan.db`    | SQLite file path                      |
| `JCAN_HTTP_HOST`        | `127.0.0.1`  | HTTP bind address                     |
| `JCAN_HTTP_PORT`        | `8000`       | HTTP port                             |

## Tests

    pytest -v
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: README with setup and run instructions"
```
