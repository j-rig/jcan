from jcan.config import Config


def test_from_env_uses_defaults(monkeypatch):
    for key in [
        "JCAN_BUS_TYPE", "JCAN_CHANNEL", "JCAN_POLL_INTERVAL_S",
        "JCAN_PID_TIMEOUT_S", "JCAN_DB_PATH", "JCAN_HTTP_HOST", "JCAN_HTTP_PORT",
    ]:
        monkeypatch.delenv(key, raising=False)
    cfg = Config.from_env()
    assert cfg.bus_type == "virtual"
    assert cfg.channel == "jcan-sim"
    assert cfg.poll_interval_s == 1.0
    assert cfg.pid_timeout_s == 0.2
    assert cfg.db_path == "jcan.db"
    assert cfg.http_host == "127.0.0.1"
    assert cfg.http_port == 8000


def test_from_env_reads_overrides(monkeypatch):
    monkeypatch.setenv("JCAN_BUS_TYPE", "slcan")
    monkeypatch.setenv("JCAN_CHANNEL", "/dev/tty.usbmodem1")
    cfg = Config.from_env()
    assert cfg.bus_type == "slcan"
    assert cfg.channel == "/dev/tty.usbmodem1"
