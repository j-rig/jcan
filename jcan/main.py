import uvicorn

from .can_transport import create_bus
from .config import Config
from .history_db import HistoryDB
from .reader import Reader
from .simulator import Simulator
from .web import create_app


def main() -> None:
    cfg = Config.from_env()
    bus = create_bus(cfg.bus_type, cfg.channel)

    if cfg.bus_type == "virtual":
        simulator_bus = create_bus("virtual", cfg.channel)
        Simulator(simulator_bus).start()

    db = HistoryDB(cfg.db_path)
    reader = Reader(bus, poll_interval_s=cfg.poll_interval_s, pid_timeout_s=cfg.pid_timeout_s)
    app = create_app(reader, db, static_dir="jcan/static")
    uvicorn.run(app, host=cfg.http_host, port=cfg.http_port)


if __name__ == "__main__":
    main()
