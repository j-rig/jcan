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
