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
