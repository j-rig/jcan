_TYPE_CHARS = {0b00: "P", 0b01: "C", 0b10: "B", 0b11: "U"}


def decode_dtc(byte1: int, byte2: int) -> str:
    type_char = _TYPE_CHARS[(byte1 >> 6) & 0b11]
    first_digit = (byte1 >> 4) & 0b11
    second_digit = byte1 & 0b1111
    third_digit = (byte2 >> 4) & 0b1111
    fourth_digit = byte2 & 0b1111
    return f"{type_char}{first_digit}{second_digit:X}{third_digit:X}{fourth_digit:X}"


def decode_dtcs(data: bytes) -> list[str]:
    codes = []
    for i in range(0, len(data) - 1, 2):
        b1, b2 = data[i], data[i + 1]
        if b1 == 0 and b2 == 0:
            continue
        codes.append(decode_dtc(b1, b2))
    return codes
