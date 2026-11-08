# jcan_can_bridge

Turns an Arduino + MCP2515 CAN shield into a USB-serial CAN interface that
jcan can drive directly (`JCAN_BUS_TYPE=arduino`) — no slcan firmware needed.

## Hardware assumed

- Arduino Uno/Nano (or any board with the standard SPI pins) + an MCP2515-based
  CAN shield (Seeed CAN-BUS Shield, Sparkfun CAN-Bus Shield, or a generic
  MCP2515 module wired to SPI).
- CS (chip-select) pin wired to Arduino pin 9 — change `CAN_CS_PIN` in the
  sketch if your shield uses a different pin (10 is also common).
- Shield's crystal oscillator — most are 16 MHz (`MCP_16MHZ`, the sketch's
  default); some clones use 8 MHz (`MCP_8MHZ`). If `CAN.begin()` never
  succeeds (the onboard LED/serial never gets past setup), try switching this.
- CAN H/L wired to the OBD-II port's CAN H/L pins — see
  `../../docs/hardware-obd2-wiring.md`.

## Library

Install **"mcp_can" by coryjfowler** via the Arduino IDE's Library Manager
(Sketch → Include Library → Manage Libraries → search "mcp_can").

## Flashing

Open `jcan_can_bridge.ino` in the Arduino IDE, select your board/port, Upload.

## Wire protocol

Plain ASCII lines over USB serial at 115200 baud, standard (11-bit) CAN IDs
only — matches OBD-II's `0x7DF` request / `0x7E8`-`0x7EF` response range.

- Arduino → host, for every CAN frame received: `R,<id_hex>,<data_hex>\n`
  e.g. `R,7E8,410C1AF8\n`
- Host → Arduino, to transmit a frame: `S,<id_hex>,<data_hex>\n`
  e.g. `S,7DF,02010C000000000000\n`

`id_hex` has no leading zeros or `0x` prefix. `data_hex` is the frame's data
bytes concatenated as two-hex-digit-per-byte (no separators, no length
prefix — length is just `len(data_hex) / 2`).

This is jcan's own minimal protocol, not LAWICEL/slcan — it only needs to
satisfy `jcan/arduino_bus.py`'s `ArduinoSerialBus`, so it stays simple enough
to hand-roll on an 8-bit Arduino without a full AT-command parser.

## Using it with jcan

    JCAN_BUS_TYPE=arduino JCAN_CHANNEL=/dev/tty.usbmodemXXXX python -m jcan.main

Same `JCAN_CHANNEL` convention as the `slcan` backend — point it at whatever
serial device the Arduino shows up as.
