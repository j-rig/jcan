import time

import can
import serial

BAUDRATE = 115200

# Arduino boards reset when the serial port is opened (DTR toggling the
# bootloader) and print boot noise before jcan_can_bridge.ino's setup() runs.
# Giving it a moment avoids losing/misreading the first few requests.
BOOT_DELAY_S = 2.0


class ArduinoSerialBus(can.BusABC):
    """Talks to jcan_can_bridge.ino over USB serial.

    Wire protocol (newline-terminated ASCII lines, see arduino/jcan_can_bridge):
      Arduino -> host: "R,<id_hex>,<data_hex>\\n"  (a CAN frame it received)
      host -> Arduino: "S,<id_hex>,<data_hex>\\n"  (a CAN frame to transmit)
    """

    def __init__(self, channel: str, baudrate: int = BAUDRATE, boot_delay_s: float = BOOT_DELAY_S):
        self._serial = serial.serial_for_url(channel, baudrate=baudrate, timeout=0.1)
        if boot_delay_s:
            time.sleep(boot_delay_s)
        super().__init__(channel=channel)

    def send(self, msg: can.Message, timeout: float | None = None) -> None:
        line = f"S,{msg.arbitration_id:X},{msg.data.hex().upper()}\n"
        self._serial.write(line.encode("ascii"))

    def _recv_internal(self, timeout: float | None = None):
        if timeout is not None:
            self._serial.timeout = timeout
        line = self._serial.readline()
        if not line:
            return None, False
        return parse_frame(line), False

    def shutdown(self) -> None:
        self._serial.close()


def parse_frame(line: bytes) -> can.Message | None:
    text = line.decode("ascii", errors="ignore").strip()
    if not text.startswith("R,"):
        return None
    try:
        _, id_hex, data_hex = text.split(",", 2)
        return can.Message(
            arbitration_id=int(id_hex, 16), data=bytes.fromhex(data_hex), is_extended_id=False
        )
    except ValueError:
        return None  # malformed line (e.g. boot noise) — treated as no frame this read
