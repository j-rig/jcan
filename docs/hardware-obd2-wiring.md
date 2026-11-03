# OBD-II Wiring & USB-CAN Dongle Reference

Reference notes for connecting a CAN-to-USB dongle to a car's OBD-II port, to support the [design spec](superpowers/specs/2026-11-02-car-diagnostic-tool-design.md).

## OBD-II Connector (SAE J1962)

16-pin, D-shaped, trapezoidal connector, keyed so it only fits one way. Looking at the connector face (pins on the car side, female socket), pins are numbered left-to-right, top row then bottom row:

```
 ┌─────────────────────────────┐
 │  1   2   3   4   5   6   7   8  │
 │  9  10  11  12  13  14  15  16  │
 └─────────────────────────────┘
```

### Pins relevant to this project (CAN)

| Pin | Signal | Notes |
|-----|--------|-------|
| 6 | CAN High (CAN_H) | ISO 15765-4 / SAE J2284. Required on all US vehicles 2008+ (most others worldwide by ~2008-2010 too). |
| 14 | CAN Low (CAN_L) | Paired twisted conductor with pin 6. |
| 4 | Chassis ground | Tie dongle ground here or pin 5. |
| 5 | Signal ground | Often the cleaner ground reference; either 4 or 5 is fine in practice. |
| 16 | Battery+ (12V) | Usually always-on (not switched by ignition) — useful if you want the dongle powered without the key on, but means it can drain the battery if left plugged in long-term. |

### Pins NOT relevant here (legacy/other protocols — do not connect)

| Pin | Signal |
|-----|--------|
| 2, 10 | SAE J1850 (older GM/Ford) |
| 7, 15 | ISO 9141-2 / KWP2000 K-Line, L-Line |
| 3, 11 | Manufacturer-specific, sometimes a second CAN bus (e.g. chassis/body CAN on some vehicles) |

Only pins 6, 14, 4/5, and 16 matter for standard OBD2-over-CAN. Most CAN-to-USB dongles sold with an OBD2 cable already wire this correctly — you generally don't need to do your own wiring unless you're building a custom harness or breakout.

### Termination

The vehicle's own ECUs provide the required 120Ω (x2, one near each end of the bus) termination — you do **not** add termination resistors on the dongle side. Adding a terminating resistor on your adapter in addition to the car's own termination will degrade the bus, not help it.

### Power

- If your dongle draws power over USB (virtually all do), you don't need pin 16 at all — just CAN H (6), CAN L (14), and ground (4 or 5).
- Ignore pin 16 unless you specifically want the dongle to power up without a laptop connected (not a concern for this project — it's USB-powered from the laptop).

## USB-CAN Dongle Options

Given the design's choice of `python-can` + the **slcan** backend (works identically on macOS/Linux/Windows over a plain serial port, no SocketCAN or vendor driver needed), the dongle needs to either ship with slcan firmware or support flashing it.

| Option | Firmware | macOS support | Notes |
|--------|----------|----------------|-------|
| **CANable 2.0 (genuine, canable.io)** (Recommended) | Ships with `candlelight` (gs_usb) by default, but official `slcan` firmware is a simple DFU reflash | Good once reflashed to slcan | Open-source hardware/firmware, active maintenance, best documentation, OBD2 cable often sold alongside it. This is the one to buy. |
| **CANable clones (AliExpress/Amazon, unbranded)** | Varies — many ship with candlelight or an old slcan build | Variable | Much cheaper, same open-source firmware can usually be reflashed, but transceiver quality and ESD protection are inconsistent. Fine for a hobby budget if you're comfortable reflashing firmware and debugging flaky units. |
| **PEAK PCAN-USB** | Vendor firmware (not slcan) | Requires PEAK's macOS driver/kernel extension | Rock-solid, well supported by python-can's dedicated `pcan` backend — but notarized kernel extensions on recent macOS can be a hassle, and it's 3-5x the price of a CANable. Overkill for this project. |
| **Innomaker USB2CAN** | Candlelight-based | Linux-oriented (gs_usb backend), poor macOS story | Skip for macOS — this one leans on SocketCAN/gs_usb, which isn't the path we're taking. |

### Recommendation

Buy a **genuine CANable 2.0**, flash it to the official `slcan` firmware image (one-time, via DFU over USB — documented on canable.io), and use `python-can`'s `slcan` backend pointed at the resulting serial device (e.g. `/dev/tty.usbmodemXXXX` on macOS). This matches the `can_transport` config in the design doc exactly — the same `slcan` code path, just swapping a `virtual` channel name for a real serial port.

If budget is the main constraint, a clone will likely work after reflashing, but expect to spend some time troubleshooting if signal integrity is poor at higher bus loads — not a concern for polling a handful of standard PIDs at a slow rate, but worth knowing if you ever want to sniff full bus traffic.
