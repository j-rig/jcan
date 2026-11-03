import can
import isotp

REQUEST_ID = 0x7DF

MODE_CURRENT_DATA = 0x01
MODE_STORED_DTCS = 0x03
MODE_CLEAR_DTCS = 0x04
MODE_VEHICLE_INFO = 0x09
PID_VIN = 0x02


class Obd2Error(Exception):
    pass


class Obd2Session:
    def __init__(self, bus: can.BusABC, response_id: int = 0x7E8, timeout: float = 0.2):
        addr = isotp.Address(isotp.AddressingMode.Normal_11bits, txid=REQUEST_ID, rxid=response_id)
        self._stack = isotp.CanStack(bus, address=addr)
        self._timeout = timeout
        self._stack.start()

    def close(self) -> None:
        self._stack.stop()

    def _request(self, payload: bytes) -> bytes:
        self._stack.send(payload)
        response = self._stack.recv(block=True, timeout=self._timeout)
        if response is None:
            raise Obd2Error(f"No response to request {payload.hex()}")
        return bytes(response)

    def read_pid(self, pid: int) -> bytes:
        response = self._request(bytes([MODE_CURRENT_DATA, pid]))
        if len(response) < 3 or response[0] != MODE_CURRENT_DATA + 0x40 or response[1] != pid:
            raise Obd2Error(f"Unexpected PID response: {response.hex()}")
        return response[2:]

    def read_dtcs(self) -> bytes:
        response = self._request(bytes([MODE_STORED_DTCS]))
        if len(response) < 2 or response[0] != MODE_STORED_DTCS + 0x40:
            raise Obd2Error(f"Unexpected DTC response: {response.hex()}")
        return response[2:]  # skip mode byte and DTC-count byte

    def clear_dtcs(self) -> None:
        response = self._request(bytes([MODE_CLEAR_DTCS]))
        if len(response) < 1 or response[0] != MODE_CLEAR_DTCS + 0x40:
            raise Obd2Error(f"Unexpected clear-DTC response: {response.hex()}")

    def read_vin(self) -> str:
        response = self._request(bytes([MODE_VEHICLE_INFO, PID_VIN]))
        if len(response) < 3 or response[0] != MODE_VEHICLE_INFO + 0x40 or response[1] != PID_VIN:
            raise Obd2Error(f"Unexpected VIN response: {response.hex()}")
        raw = response[3:]
        return raw.decode("ascii", errors="ignore").strip("\x00").strip()
