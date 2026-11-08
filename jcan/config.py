import os
from dataclasses import dataclass


@dataclass
class Config:
    bus_type: str
    channel: str
    poll_interval_s: float
    pid_timeout_s: float
    db_path: str
    http_host: str
    http_port: int
    udp_host: str | None
    udp_port: int

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            bus_type=os.environ.get("JCAN_BUS_TYPE", "virtual"),
            channel=os.environ.get("JCAN_CHANNEL", "jcan-sim"),
            poll_interval_s=float(os.environ.get("JCAN_POLL_INTERVAL_S", "1.0")),
            pid_timeout_s=float(os.environ.get("JCAN_PID_TIMEOUT_S", "0.2")),
            db_path=os.environ.get("JCAN_DB_PATH", "jcan.db"),
            http_host=os.environ.get("JCAN_HTTP_HOST", "127.0.0.1"),
            http_port=int(os.environ.get("JCAN_HTTP_PORT", "8000")),
            udp_host=os.environ.get("JCAN_UDP_HOST") or None,
            udp_port=int(os.environ.get("JCAN_UDP_PORT", "20110")),
        )
