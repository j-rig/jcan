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


def _decode_two_byte_count(data: bytes) -> float:
    return float((data[0] * 256) + data[1])


def _decode_voltage(data: bytes) -> float:
    return round(((data[0] * 256) + data[1]) / 1000, 3)


def _decode_manifold_pressure(data: bytes) -> float:
    return float(data[0])


def _decode_timing_advance(data: bytes) -> float:
    return data[0] / 2 - 64


def _decode_maf_rate(data: bytes) -> float:
    return round(((data[0] * 256) + data[1]) / 100, 2)


LIVE_PIDS = [
    PidDef(0x0C, "rpm", "rpm", _decode_rpm),
    PidDef(0x0D, "speed", "km/h", _decode_speed),
    PidDef(0x05, "coolant_temp", "C", _decode_temp),
    PidDef(0x11, "throttle_position", "%", _decode_percent),
    PidDef(0x04, "engine_load", "%", _decode_percent),
    PidDef(0x0F, "intake_air_temp", "C", _decode_temp),
    PidDef(0x0B, "intake_manifold_pressure", "kPa", _decode_manifold_pressure),
    PidDef(0x0E, "timing_advance", "deg", _decode_timing_advance),
    PidDef(0x10, "maf_rate", "g/s", _decode_maf_rate),
    PidDef(0x1F, "run_time", "s", _decode_two_byte_count),
    PidDef(0x2F, "fuel_level", "%", _decode_percent),
    PidDef(0x31, "distance_since_codes_cleared", "km", _decode_two_byte_count),
    PidDef(0x42, "control_module_voltage", "V", _decode_voltage),
    PidDef(0x46, "ambient_air_temp", "C", _decode_temp),
    PidDef(0x4E, "time_since_codes_cleared", "min", _decode_two_byte_count),
    PidDef(0x5C, "engine_oil_temp", "C", _decode_temp),
]

PIDS_BY_ID = {p.pid: p for p in LIVE_PIDS}
