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
