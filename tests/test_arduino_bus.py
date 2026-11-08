import can

from jcan.arduino_bus import ArduinoSerialBus, parse_frame


def _bus():
    # loop:// is pyserial's built-in in-memory loopback, for tests without real hardware.
    return ArduinoSerialBus("loop://", boot_delay_s=0)


def test_send_writes_expected_line():
    bus = _bus()
    try:
        bus.send(can.Message(arbitration_id=0x7DF, data=bytes([0x02, 0x01, 0x0C]), is_extended_id=False))
        line = bus._serial.readline()
    finally:
        bus.shutdown()
    assert line == b"S,7DF,02010C\n"


def test_recv_parses_frame_written_by_arduino():
    bus = _bus()
    try:
        bus._serial.write(b"R,7E8,410C1AF8\n")
        received = bus.recv(timeout=1.0)
    finally:
        bus.shutdown()
    assert received is not None
    assert received.arbitration_id == 0x7E8
    assert bytes(received.data) == bytes([0x41, 0x0C, 0x1A, 0xF8])


def test_recv_ignores_boot_noise_then_times_out():
    bus = _bus()
    try:
        bus._serial.write(b"random boot garbage\r\n")
        received = bus.recv(timeout=0.3)
    finally:
        bus.shutdown()
    assert received is None


def test_parse_frame_rejects_non_frame_lines():
    assert parse_frame(b"random boot garbage\r\n") is None
    assert parse_frame(b"S,7DF,0201\n") is None  # a command line, not a received frame
    assert parse_frame(b"R,not-hex,0201\n") is None


def test_parse_frame_accepts_zero_length_data():
    msg = parse_frame(b"R,7E8,\n")
    assert msg.arbitration_id == 0x7E8
    assert bytes(msg.data) == b""
