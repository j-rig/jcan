from jcan.readiness import decode_readiness


def test_decode_readiness_mil_off_all_ready():
    # A=0x00 (MIL off, 0 DTCs), B=0x07 (misfire/fuel/components supported+ready),
    # C=0x01 (catalyst supported), D=0x00 (catalyst ready)
    result = decode_readiness(bytes([0x00, 0x07, 0x01, 0x00]))
    assert result["mil_on"] is False
    assert result["dtc_count"] == 0
    assert result["monitors"] == [
        {"name": "misfire", "ready": True},
        {"name": "fuel_system", "ready": True},
        {"name": "components", "ready": True},
        {"name": "catalyst", "ready": True},
    ]


def test_decode_readiness_mil_on_with_dtcs_and_incomplete_monitor():
    # A=0x82 (MIL on, 2 DTCs), B=0x47 (misfire/fuel ready, components supported+NOT ready),
    # C=0xE5 (catalyst/evaporative/o2/o2-heater/egr supported), D=0x04 (evaporative NOT ready)
    result = decode_readiness(bytes([0x82, 0x47, 0xE5, 0x04]))
    assert result["mil_on"] is True
    assert result["dtc_count"] == 2
    assert result["monitors"] == [
        {"name": "misfire", "ready": True},
        {"name": "fuel_system", "ready": True},
        {"name": "components", "ready": False},
        {"name": "catalyst", "ready": True},
        {"name": "evaporative_system", "ready": False},
        {"name": "oxygen_sensor", "ready": True},
        {"name": "oxygen_sensor_heater", "ready": True},
        {"name": "egr_system", "ready": True},
    ]


def test_decode_readiness_unsupported_monitors_are_omitted():
    result = decode_readiness(bytes([0x00, 0x00, 0x00, 0xFF]))
    assert result["monitors"] == []
