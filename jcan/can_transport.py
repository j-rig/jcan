import can

from .arduino_bus import ArduinoSerialBus


def create_bus(bus_type: str, channel: str) -> can.BusABC:
    if bus_type == "slcan":
        return can.Bus(interface="slcan", channel=channel, bitrate=500000)
    if bus_type == "virtual":
        return can.Bus(interface="virtual", channel=channel, receive_own_messages=False)
    if bus_type == "arduino":
        return ArduinoSerialBus(channel)
    raise ValueError(f"Unknown bus_type: {bus_type!r} (expected 'slcan', 'virtual', or 'arduino')")
