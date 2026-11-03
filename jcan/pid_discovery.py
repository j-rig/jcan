def decode_supported_pids(base_pid: int, data: bytes) -> set[int]:
    bits = int.from_bytes(data[:4], "big")
    return {base_pid + i + 1 for i in range(32) if bits & (1 << (31 - i))}


def decode_o2_sensors_present(data: bytes) -> set[int]:
    a = data[0]
    return {0x14 + i for i in range(8) if a & (1 << (7 - i))}
