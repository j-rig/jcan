import queue
import threading
import time
from dataclasses import dataclass
from typing import Callable

import can

from . import pid_discovery
from . import pids as pids_module
from .dtc import decode_dtcs
from .obd2 import Obd2Error, Obd2Session


@dataclass
class _Command:
    action: str
    result: "queue.Queue"


class Reader:
    def __init__(self, bus: can.BusABC, poll_interval_s: float, pid_timeout_s: float):
        self._bus = bus
        self._poll_interval_s = poll_interval_s
        self._pid_timeout_s = pid_timeout_s
        self._commands: "queue.Queue[_Command]" = queue.Queue()
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self.current_vin: str | None = None
        self.live_pids: list[pids_module.PidDef] = list(pids_module.LIVE_PIDS)
        self.on_reading: Callable[[str, float, str], None] = lambda *_: None
        self.on_status: Callable[[str], None] = lambda *_: None

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def submit(self, action: str) -> "queue.Queue":
        result: "queue.Queue" = queue.Queue(maxsize=1)
        self._commands.put(_Command(action=action, result=result))
        return result

    def _run(self) -> None:
        try:
            session = Obd2Session(self._bus, timeout=self._pid_timeout_s)
        except Exception as exc:
            self.on_status(f"connect_failed: {exc}")
            return

        try:
            self.current_vin = session.read_vin()
        except Obd2Error:
            self.current_vin = None
            self.on_status("vin_read_failed")

        try:
            supported = self._discover_supported_pids(session)
            self.live_pids = [p for p in pids_module.LIVE_PIDS if p.pid in supported]
        except Obd2Error:
            supported = set()
            self.live_pids = list(pids_module.LIVE_PIDS)

        if 0x13 in supported:
            try:
                o2_present = pid_discovery.decode_o2_sensors_present(session.read_pid(0x13))
                self.live_pids = self.live_pids + [
                    pids_module.OPTIONAL_O2_PIDS[pid]
                    for pid in sorted(o2_present)
                    if pid in pids_module.OPTIONAL_O2_PIDS
                ]
            except Obd2Error:
                pass  # O2 sensor read failed; keep the already-discovered live_pids as-is

        self.on_status("connected")
        last_poll = 0.0
        try:
            while not self._stop_event.is_set():
                self._drain_one_command(session)
                now = time.monotonic()
                if now - last_poll >= self._poll_interval_s:
                    self._poll_once(session)
                    last_poll = now
                else:
                    time.sleep(0.05)
        except Exception as exc:
            self.on_status(f"lost: {exc}")
        finally:
            session.close()

    def _drain_one_command(self, session: Obd2Session) -> None:
        try:
            command = self._commands.get_nowait()
        except queue.Empty:
            return
        try:
            if command.action == "read_dtcs":
                codes = decode_dtcs(session.read_dtcs())
                command.result.put(("ok", codes))
            elif command.action == "clear_dtcs":
                session.clear_dtcs()
                command.result.put(("ok", None))
        except Obd2Error as exc:
            command.result.put(("error", str(exc)))

    def _discover_supported_pids(self, session: Obd2Session) -> set[int]:
        supported = pid_discovery.decode_supported_pids(0x00, session.read_pid(0x00))
        for base in (0x20, 0x40):
            if base not in supported:
                break
            supported |= pid_discovery.decode_supported_pids(base, session.read_pid(base))
        return supported

    def _poll_once(self, session: Obd2Session) -> None:
        for pid_def in self.live_pids:
            try:
                raw = session.read_pid(pid_def.pid)
                value = pid_def.decode(raw)
                self.on_reading(pid_def.name, value, pid_def.unit)
            except Obd2Error:
                continue
