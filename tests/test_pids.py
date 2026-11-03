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
