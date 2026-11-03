# Car Diagnostic Tool (jcan) — Design

## Purpose

A self-built OBD-II diagnostic tool for personal use on a macOS laptop. Connects to the car via a CAN-to-USB dongle, runs as a local Python service with an HTTP interface, and shows live engine gauges plus diagnostic trouble code (DTC) info with the ability to clear codes.

## Scope

- Live gauges tab: standard SAE J1979 Mode 01 PIDs — RPM, vehicle speed, coolant temp, throttle position, engine load, intake air temp.
- Diagnostics tab: read stored DTCs (Mode 03), clear DTCs (Mode 04) behind a confirmation dialog.
- Vehicles tab: lists every distinct VIN seen across the DTC history. A VIN not yet decoded shows raw with a "Decode VIN" button; a decoded VIN shows make/model/year and decoded-at instead.
- DTC descriptions: a generic SAE J1979 code-to-meaning table, plus a small manufacturer-specific extension table (for proprietary P1xxx-range codes) covering known codes for Honda and Mitsubishi — the makes of the three vehicles this tool is used on. This reference data lives as a JSON file committed to the repo (`jcan/seed_data/dtc_codes.json`), not hardcoded in Python — it seeds a `dtc_reference` table in the SQLite database on every startup (upsert, so edits to the JSON file always take effect on next run). A DTC event's description is derived at *read* time, not stored at insert time: it's looked up by code, preferring a manufacturer-specific row matching the event's decoded vehicle make, falling back to the generic row. This means a DTC event recorded before its VIN was decoded automatically starts showing the manufacturer-specific meaning once decoding happens later — no backfill needed. Scope is standard/documented meanings only — no speculative common-cause or repair guidance.
- History: SQLite log of DTC events — code, first-seen timestamp, cleared-at timestamp, the VIN of the car it came from (read automatically, never manually entered), and an editable free-text notes field per event. Description is not stored on the event — it's derived at read time from the `dtc_reference` table (see above). No live-data logging in this scope.
- VIN decoding: the "Decode VIN" button lives on the Vehicles tab (not on individual DTC rows). Clicking it calls the NHTSA vPIC API and saves the result keyed by VIN. The full raw JSON response from NHTSA (not just make/model/year) is stored and displayed — NHTSA returns ~150 fields per VIN (trim, engine, body class, GVWR, etc.), and the Vehicles tab shows all of it, not just the three summary fields. Once decoded, any other view showing that VIN — e.g. Diagnostics tab rows — displays the decoded make/model/year instead of the raw VIN.
- Must be fully testable without real hardware via a built-in CAN bus simulator.

Out of scope (not building now): freeze frame data, manufacturer-specific PIDs, live-data trip logging, manual vehicle profile management (vehicles are only ever identified automatically via VIN, never hand-entered or switched by the user), auth/multi-user support, Windows/Linux-specific hardware paths (macOS only for now).

## Hardware & Protocol

- **Dongle:** CAN-to-USB adapter running `slcan` firmware (e.g. CANable in slcan mode) — chosen because `slcan` works identically across macOS/Linux/Windows via a plain serial port, unlike SocketCAN (Linux-only) or vendor-specific drivers.
- **Transport:** `python-can`, using the `slcan` backend for real hardware or the `virtual` backend for the simulator — same code path either way, selected by config.
- **OBD2 over CAN:** `can-isotp` handles ISO-TP transport (required for multi-frame responses, e.g. multiple stored DTCs). A hand-written module encodes/decodes standard SAE J1979 Mode 01/03/04 requests and responses — these PID formulas are public and simple (e.g. RPM = ((A×256)+B)/4). Also implements Mode 09 PID 02 (VIN request) — this one always returns a multi-frame response, which is exactly why `can-isotp` is in the stack rather than hand-rolling single-frame-only parsing.
- Request functional address: `0x7DF`. Response addresses: `0x7E8`–`0x7EF`.

## Architecture

Single Python process:

```
┌─────────────┐    queue    ┌──────────────┐   WebSocket   ┌──────────┐
│ reader thread│ ──────────▶ │ FastAPI app  │ ─────────────▶│ browser  │
│ (blocking IO)│             │ (uvicorn)    │               │ frontend │
└──────┬───────┘             └──────┬───────┘               └──────────┘
       │                            │ REST (DTC read/clear)
       ▼                            ▼
┌─────────────┐             ┌──────────────┐
│ can_transport│             │ history_db   │
│ + obd2 layer │             │ (SQLite)     │
└──────┬───────┘             └──────────────┘
       │
       ▼ (real HW)        or  ▼ (dev/test)
┌─────────────┐             ┌──────────────┐
│ slcan dongle │             │ simulator    │
│              │             │ (virtual bus)│
└─────────────┘             └──────────────┘
```

## Components

1. **`can_transport`** — creates the `python-can` bus from config: `slcan` + serial port (real) or `virtual` + channel name (simulated/test). Everything above this layer is identical in both modes.
2. **`obd2`** — built on `can-isotp` over the transport. Encodes Mode 01 PID requests, Mode 03/04 DTC requests, and a Mode 09 PID 02 VIN request; decodes responses; owns the PID formula table for the live gauge set.
3. **`simulator`** — standalone runnable module (`python -m jcan.simulator`) that opens a `virtual` bus channel and acts as a fake ECU: responds to PID requests with synthetic, moving values (RPM, speed, etc.), answers Mode 03 with a couple of fixed fake DTCs (Mode 04 clears them), and answers the VIN request with a fixed fake VIN. This is both the test harness and the day-to-day dev environment — no hardware required.
4. **`reader`** (background thread) — owns the `obd2` session. On connect, reads the VIN once and holds it as session state. Then polls the live PID list on a fixed interval, pushing `(pid, value, timestamp)` readings onto a thread-safe queue bridged into the asyncio event loop. Also performs on-demand DTC read/clear requests, tagging any DB writes with the session's VIN.
5. **`history_db`** — thin SQLite wrapper, two tables:
   - DTC events: `id`, `code`, `vin`, `first_seen`, `cleared_at`, `notes`. `vin` is stamped automatically from the reader's session state at insert time — never entered or edited by hand. `notes` starts empty and is the only field users edit directly. No `description` column — it's derived at read time (see `dtc_reference` below).
   - Vehicles: `vin` (primary key), `make`, `model`, `year`, `raw_json`, `decoded_at`. One row per distinct VIN ever decoded. `raw_json` holds the complete NHTSA vPIC response for that VIN (all ~150 fields, not just the three summary ones) so no decoded data is ever discarded. Absence of a row for a given VIN means "not decoded yet."
   - DTC reference: `code`, `make` (empty string = generic/SAE-standard, non-empty = manufacturer-specific override), `description`. Primary key `(code, make)`. Seeded from `jcan/seed_data/dtc_codes.json` on every `HistoryDB` init (upsert — the JSON file is the source of truth).
6. **`vin_decoder`** — thin wrapper around the NHTSA vPIC API (`DecodeVinValues`, free, no API key). Given a VIN, returns make/model/year plus the full raw decoded response dict, or raises on failure/no-match.
7. **`web`** (FastAPI + uvicorn) — WebSocket endpoint streams queued readings to the Gauges tab and connection-status messages. REST endpoints: `GET /dtcs` (triggers a Mode 03 read, diffs against `history_db`, inserts newly-seen codes stamped with the current VIN, returns current codes each left-joined with any decoded `vehicles` row for its VIN), `POST /dtcs/clear` (sends Mode 04, stamps `cleared_at` on matching rows), `PATCH /dtcs/{id}/notes` (updates only the `notes` field on one event), `GET /vehicles` (distinct VINs from `history_db`'s DTC events, left-joined with the `vehicles` table, including the parsed raw JSON), `POST /vehicles/{vin}/decode` (calls `vin_decoder`, upserts make/model/year plus the full raw JSON into `vehicles`, returns all of it). Serves the static frontend.
8. **frontend** — static HTML/CSS/JS, no framework. Three tabs (Gauges, Diagnostics, Vehicles) toggled client-side, one shared WebSocket connection. Gauges tab: simple numeric readouts with a small bar per PID, "stale" indicator if a PID hasn't updated recently. Diagnostics tab: DTC list, each row showing its VIN (raw, or decoded make/model/year if available — read-only, no button here), an editable notes textarea (saved via `PATCH /dtcs/{id}/notes` on blur), and a "Clear Codes" button that opens a confirmation dialog before calling `POST /dtcs/clear`. Vehicles tab: calls `GET /vehicles`, lists every distinct VIN seen; a row with no decoded `vehicles` entry shows the raw VIN plus a "Decode VIN" button, clicking it calls `POST /vehicles/{vin}/decode` and on success re-renders that row with make/model/year plus an expandable section showing the complete raw decoded data (all ~150 NHTSA fields, not just the summary three) — and since the Diagnostics tab's VIN display reads from the same `vehicles` data, re-fetching/re-rendering it after a decode shows the update there too.

## Data Flow

1. On startup, app reads config (bus mode + connection target), opens the transport, starts the reader thread.
2. Reader's first action on connect: send the Mode 09 PID 02 VIN request, decode it, hold it in memory as the session's `current_vin`. This happens once per connection, before the poll loop starts.
3. Reader loop: for each PID in the live set, send a Mode 01 request, wait for the isotp response (short timeout, ~200ms), decode, push `{pid, value, ts}` to the queue via `loop.call_soon_threadsafe`.
4. WebSocket handler awaits the queue, forwards each reading as JSON to all connected clients.
5. Diagnostics tab calls `GET /dtcs` on demand (not part of the continuous poll loop) — triggers a one-off Mode 03 request, decodes, diffs against `history_db`, and any newly-inserted rows are stamped with `current_vin`.
6. `POST /dtcs/clear` sends Mode 04, then stamps `cleared_at` on matching history rows.
7. Editing notes on an existing event calls `PATCH /dtcs/{id}/notes` directly — no bus interaction, just a `history_db` update.
8. Vehicles tab calls `GET /vehicles` to list distinct VINs left-joined with decoded data. Clicking "Decode VIN" on an undecoded row calls `POST /vehicles/{vin}/decode` — no bus interaction, just an outbound HTTP call to NHTSA vPIC and a `vehicles` upsert — then re-renders that row with the decoded result. Any Diagnostics tab rows sharing that VIN pick up the decoded info next time that view fetches `GET /dtcs`.

## Error Handling

- **No adapter / bad serial port at startup:** fail fast with a clear error naming the configured port — no silent retry loop.
- **VIN read fails or times out on connect:** don't block startup on it — log a warning, set `current_vin` to `NULL`, and proceed to the normal poll loop. Gauges and DTC read/clear still work; any DTC events logged during that session simply have a `NULL` vin until a successful reconnect picks one up.
- **PID request timeout:** skip that PID for the current poll cycle, keep polling the rest. UI shows a stale indicator if a PID hasn't updated within N seconds.
- **Bus/transport dies mid-run** (adapter unplugged): reader thread catches the exception, marks connection state "lost," broadcasts a connection-status message over WebSocket so the frontend shows a banner instead of silently frozen gauges.
- **Clear DTCs while bus is down:** `POST /dtcs/clear` returns an error status; frontend surfaces it in the confirmation-dialog flow rather than claiming success.
- **VIN decode fails** (network down, NHTSA unreachable, or VIN not found in their database): `POST /vehicles/{vin}/decode` returns an error status, no `vehicles` row is written, and the Vehicles tab row's "Decode VIN" button simply stays visible with an inline error so the user can retry — no crash, no partial/garbage data saved.

## Testing

- Unit tests for PID decode formulas and DTC byte-decoding — pure functions, no bus needed.
- Unit tests for `vin_decoder` against a mocked HTTP client (success, not-found, network-error cases) — no real network calls in the test suite.
- Integration tests run the full app against the `virtual` bus with the `simulator` module as the fake ECU — covers the full request/response/WebSocket/DB path with zero hardware. This is also the primary day-to-day dev loop.
- Manual smoke test against real hardware once the dongle is in hand, using the same config pointed at `slcan` instead of `virtual`.
