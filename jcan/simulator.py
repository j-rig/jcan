import sys
import threading
import time

import can
import isotp

SIM_RESPONSE_ID = 0x7E8
SIM_REQUEST_ID = 0x7DF

FAKE_VIN = "1HGCM82633A004352"
FAKE_DTCS = [(0x01, 0x33), (0x03, 0x01)]  # P0133, P0301


class Simulator:
    def __init__(self, bus: can.BusABC):
        addr = isotp.Address(isotp.AddressingMode.Normal_11bits, txid=SIM_RESPONSE_ID, rxid=SIM_REQUEST_ID)
        self._stack = isotp.CanStack(bus, address=addr)
        self._dtcs_cleared = False
        self._rpm_phase = 0
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._stack.start()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=1.0)
        self._stack.stop()

    def _run(self) -> None:
        while not self._stop_event.is_set():
            request = self._stack.recv(block=True, timeout=0.2)
            if request is None:
                continue
            response = self._handle(bytes(request))
            if response is not None:
                self._stack.send(response)

    def _handle(self, request: bytes) -> bytes | None:
        if not request:
            return None
        mode = request[0]
        if mode == 0x01 and len(request) >= 2:
            return self._handle_pid(request[1])
        if mode == 0x03:
            return self._handle_read_dtcs()
        if mode == 0x04:
            self._dtcs_cleared = True
            return bytes([0x44])
        if mode == 0x09 and len(request) >= 2 and request[1] == 0x02:
            return self._handle_vin()
        return None

    def _handle_pid(self, pid: int) -> bytes | None:
        if pid == 0x00:
            return bytes([0x41, pid, 0x18, 0x3F, 0xB8, 0x03])
        if pid == 0x20:
            return bytes([0x41, pid, 0x00, 0x02, 0x80, 0x01])
        if pid == 0x40:
            return bytes([0x41, pid, 0x44, 0x04, 0x00, 0x10])
        if pid == 0x13:
            return bytes([0x41, pid, 0xC0])
        if pid == 0x14:
            return bytes([0x41, pid, 0x96, 0x80])
        if pid == 0x15:
            return bytes([0x41, pid, 0x8C, 0x80])
        if pid == 0x0C:
            self._rpm_phase += 1
            rpm_raw = 3000 + (self._rpm_phase % 10) * 100
            a, b = divmod(rpm_raw * 4, 256)
            return bytes([0x41, pid, a, b])
        if pid == 0x0D:
            return bytes([0x41, pid, 60])
        if pid == 0x05:
            return bytes([0x41, pid, 40 + 90])
        if pid == 0x0F:
            return bytes([0x41, pid, 40 + 25])
        if pid in (0x11, 0x04):
            return bytes([0x41, pid, 128])
        if pid == 0x0B:
            return bytes([0x41, pid, 101])
        if pid == 0x0E:
            return bytes([0x41, pid, 148])
        if pid == 0x10:
            return bytes([0x41, pid, 4, 226])
        if pid == 0x1F:
            return bytes([0x41, pid, 0, 125])
        if pid == 0x2F:
            return bytes([0x41, pid, 191])
        if pid == 0x31:
            return bytes([0x41, pid, 0, 0])
        if pid == 0x42:
            return bytes([0x41, pid, 55, 120])
        if pid == 0x46:
            return bytes([0x41, pid, 62])
        if pid == 0x4E:
            return bytes([0x41, pid, 0, 0])
        if pid == 0x5C:
            return bytes([0x41, pid, 135])
        return None

    def _handle_read_dtcs(self) -> bytes:
        if self._dtcs_cleared:
            return bytes([0x43, 0x00])
        payload = bytearray([0x43, len(FAKE_DTCS)])
        for b1, b2 in FAKE_DTCS:
            payload += bytes([b1, b2])
        return bytes(payload)

    def _handle_vin(self) -> bytes:
        return bytes([0x49, 0x02, 0x01]) + FAKE_VIN.encode("ascii")


def main() -> None:
    channel = sys.argv[1] if len(sys.argv) > 1 else "jcan-sim"
    bus = can.Bus(interface="virtual", channel=channel, receive_own_messages=False)
    sim = Simulator(bus)
    sim.start()
    print(f"Simulator running on virtual channel '{channel}'. Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        sim.stop()
        bus.shutdown()


if __name__ == "__main__":
    main()
