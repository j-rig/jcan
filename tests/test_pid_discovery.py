from jcan.pid_discovery import decode_o2_sensors_present, decode_supported_pids


def test_decode_supported_pids_base_0x00():
    # bits set for PID 0x04 (byte0 bit4=0x10) and PID 0x20 (byte3 bit0=0x01)
    data = bytes([0x10, 0x00, 0x00, 0x01])
    assert decode_supported_pids(0x00, data) == {0x04, 0x20}


def test_decode_supported_pids_base_0x20():
    # bit set for PID 0x2F (byte1 bit1=0x02, since byte1 covers 0x29-0x30)
    data = bytes([0x00, 0x02, 0x00, 0x00])
    assert decode_supported_pids(0x20, data) == {0x2F}


def test_decode_supported_pids_none_set():
    assert decode_supported_pids(0x40, bytes([0x00, 0x00, 0x00, 0x00])) == set()


def test_decode_o2_sensors_present_two_sensors():
    # bit7 (Bank1Sensor1 -> 0x14) and bit6 (Bank1Sensor2 -> 0x15) set
    assert decode_o2_sensors_present(bytes([0xC0])) == {0x14, 0x15}


def test_decode_o2_sensors_present_none():
    assert decode_o2_sensors_present(bytes([0x00])) == set()


def test_decode_o2_sensors_present_all_eight():
    assert decode_o2_sensors_present(bytes([0xFF])) == {0x14, 0x15, 0x16, 0x17, 0x18, 0x19, 0x1A, 0x1B}
