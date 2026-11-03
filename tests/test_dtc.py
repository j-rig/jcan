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
