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


def test_intake_manifold_pressure_decode():
    assert _decode("intake_manifold_pressure", [0x64]) == 100.0


def test_timing_advance_decode():
    assert _decode("timing_advance", [0x8C]) == 6.0


def test_maf_rate_decode():
    assert _decode("maf_rate", [0x01, 0x90]) == 4.0


def test_run_time_decode():
    assert _decode("run_time", [0x00, 0x3C]) == 60.0


def test_fuel_level_decode():
    assert _decode("fuel_level", [0x80]) == 50.2


def test_distance_since_codes_cleared_decode():
    assert _decode("distance_since_codes_cleared", [0x00, 0x0A]) == 10.0


def test_control_module_voltage_decode():
    assert _decode("control_module_voltage", [0x32, 0x14]) == 12.82


def test_ambient_air_temp_decode():
    assert _decode("ambient_air_temp", [0x5A]) == 50.0


def test_time_since_codes_cleared_decode():
    assert _decode("time_since_codes_cleared", [0x00, 0x05]) == 5.0


def test_engine_oil_temp_decode():
    assert _decode("engine_oil_temp", [0x6E]) == 70.0


def test_o2_voltage_decode():
    from jcan.pids import OPTIONAL_O2_PIDS
    assert OPTIONAL_O2_PIDS[0x14].decode(bytes([0x96, 0x80])) == 0.75
