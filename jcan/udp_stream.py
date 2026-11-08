import json
import socket


class UdpStreamer:
    def __init__(self, host: str, port: int):
        self._addr = (host, port)
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._state: dict[str, dict[str, object]] = {}

    def send(self, pid: str, value: float, unit: str) -> None:
        self._state[pid] = {"value": value, "unit": unit}
        payload = json.dumps(self._state) + "\n"
        try:
            self._sock.sendto(payload.encode("utf-8"), self._addr)
        except OSError:
            pass  # best-effort telemetry; a send failure must not affect polling

    def close(self) -> None:
        self._sock.close()
