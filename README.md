# jcan

Personal OBD-II diagnostic tool. Reads live engine data and trouble codes over
CAN, stores DTC history in SQLite, and serves a browser UI.

## Setup

    pip install -e ".[dev]"

## Run without hardware (simulator)

One terminal — `main.py` embeds the simulator automatically whenever
`JCAN_BUS_TYPE=virtual` (the default):

    python -m jcan.main

Open http://127.0.0.1:8000/

Note: the Vehicles tab's "Decode VIN" button calls NHTSA's vPIC API over the
network — everything else works fully offline, but that one button needs
internet access.

## Run with real hardware

Flash a CAN-to-USB dongle (e.g. CANable 2.0) to slcan firmware, plug it into
the OBD-II port's CAN H/L pins (see `docs/hardware-obd2-wiring.md`), then:

    JCAN_BUS_TYPE=slcan JCAN_CHANNEL=/dev/tty.usbmodemXXXX python -m jcan.main

Replace `/dev/tty.usbmodemXXXX` with the actual serial device for your dongle
(check `ls /dev/tty.*` before and after plugging it in). If the port is wrong,
`jcan` fails immediately at startup with an error naming the bad path.

## Run with an Arduino + CAN shield

No slcan dongle needed — flash `arduino/jcan_can_bridge/jcan_can_bridge.ino`
onto an Arduino with an MCP2515 CAN shield (see that folder's README for
wiring and the required library), then:

    JCAN_BUS_TYPE=arduino JCAN_CHANNEL=/dev/tty.usbmodemXXXX python -m jcan.main

## Configuration (environment variables)

| Variable               | Default      | Meaning                              |
|-------------------------|--------------|---------------------------------------|
| `JCAN_BUS_TYPE`         | `virtual`    | `slcan`, `arduino` (real hardware), or `virtual` |
| `JCAN_CHANNEL`          | `jcan-sim`   | Serial port (slcan/arduino) or channel name (virtual) |
| `JCAN_POLL_INTERVAL_S`  | `1.0`        | Seconds between live-gauge poll cycles |
| `JCAN_PID_TIMEOUT_S`    | `0.2`        | Per-request timeout waiting on the ECU |
| `JCAN_DB_PATH`          | `jcan.db`    | SQLite file path                      |
| `JCAN_HTTP_HOST`        | `127.0.0.1`  | HTTP bind address                     |
| `JCAN_HTTP_PORT`        | `8000`       | HTTP port                             |
| `JCAN_UDP_HOST`         | unset (disabled) | If set, stream each gauge reading as a JSONL UDP datagram to this host, for integration with other tools |
| `JCAN_UDP_PORT`         | `20110`      | UDP port to stream readings to (only used if `JCAN_UDP_HOST` is set) |

Each UDP datagram is one JSON object followed by `\n`, keyed by PID name, holding every PID read so far: `{"rpm": {"value": 850.0, "unit": "rpm"}, "speed": {"value": 0.0, "unit": "km/h"}, ...}`.
A new datagram is sent every time any single PID is read — at the same rate readings reach the web UI — but each one carries the full accumulated snapshot of all PIDs, not just the one that just changed. Best-effort: a send failure is silently dropped, never affects polling.

## Tests

    pytest -v
