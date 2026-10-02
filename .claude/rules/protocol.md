---
paths:
  - "docs/SPEC.md"
  - "firmware/**"
  - "pc/**"
---

# Serial Protocol Rules (the contract)

## `docs/SPEC.md` is the single source of truth
The section "Serielles Protokoll" in `docs/SPEC.md` defines every command, response,
error code, and event. Firmware and PC tool are two implementations of that contract.
Until PROJ-2 has written that section, **no protocol code is written** — and the draft in
this file is only a starting point for the spec, not a contract.

## Change together, or not at all (MANDATORY)
Any change to the wire format — new command, new argument, changed response, new error
code, new event, changed scale/unit of a value, changed limit — is ONE change that
touches, in the same feature and ideally the same commit series:
1. `docs/SPEC.md` (the table and the error/event lists)
2. Firmware parser/handler
3. PC tool client (and CLI/GUI if user-visible)
4. Tests: host tests with the fake device in `pc/tests/` + the hardware checklist
5. `FW_VERSION` bump when the firmware behaviour on the wire changes

A protocol change is always a **material decision** → user approval before implementation.

## Compatibility
- Prefer additive changes (new command, new optional argument, new trailing field).
  Changing or removing an existing response shape breaks older PC-tool installations
- The PC tool checks `PING` → `OK PONG Umgebungssensoren <fwVersion>` on connect and warns
  (German message) if the firmware version is older than what it needs
- Unknown `EVT` types and unknown trailing fields are ignored by the PC tool (logged, not
  fatal) so the firmware can add events without breaking old tools

## Wire format rules (keep exact once SPEC.md defines them)
- 115200 baud, 8N1, ASCII, `\n` line end; incoming `\r` ignored
- Max line length 80 **bytes**; longer lines → discarded, `ERR 2 …`
- Commands case-insensitive; arguments separated by one or more spaces; empty lines ignored
- Every response starts with `OK` or `ERR <code> <text>`; lists end with `END`
- `EVT …` lines can arrive **at any time, even between a response's lines** — the PC
  client must route them to the event handler and keep collecting the response
- **Measurements are scaled integers**, never floats on the wire (the AVR has no `%f`):
  temperature 0.01 °C, humidity 0.01 %rH, pressure 0.1 hPa, gas resistance Ω. The scales
  are part of the contract; the PC tool converts for display. Missing/invalid value → a
  defined marker in SPEC (e.g. `-`), never `0`
- Error codes (draft, final table lives in SPEC.md): 1 unknown command/subcommand,
  2 bad arguments/format, 3 invalid ID/value out of range, 4 not supported/full,
  5 busy, 6 invalid name, 7 wrong state, plus a SPEC-defined code for "sensor not
  available". The `ERR` text is free-form; only the code matters

## Draft command set (to be fixed in PROJ-2 / SPEC.md)
`PING` → `OK PONG Umgebungssensoren <fw>` · `STATUS` (sensor present, interval, alarm state,
uptime) · `READ` (current values) · `CFG GET|SET <key> [value]` (interval, thresholds,
units; persisted in EEPROM) · `TIME <hh:mm:ss>` · `RESET CONFIG` · events `EVT DATA`
(periodic, interval-limited), `EVT ALARM <metric> <0|1>`, `EVT BOOT <fw>`. Diagnostics
(`DEBUG …`, `TESTPATTERN`, raw sensor dump) are **not** part of the stable contract.

## Opening the port does NOT reset the Uno (by design)
The PC client opens the port with **DTR/RTS off** (`reset_on_open=False`). A reset would
discard the RAM-only history and clock and would take ~2–3 s. Ready check
(`Device.wait_ready`):
- short wait (~0.3 s) for `EVT BOOT`; if none, send a blank line (flushes a stray byte),
  then a quick `PING`
- fallback: if the quick `PING` gets no answer, the board did reset anyway (driver
  dependent) → wait for `EVT BOOT`, then `PING` with retries
- an `EVT BOOT` in the middle of a session = "device restarted → history gone, clock
  unset" → re-read `STATUS`, re-send `TIME`
- always a read timeout; a missing `END` or response is a timeout error, not a hang

## Only one owner of COM9
Windows allows one process per COM port. `arduino-cli upload`, `arduino-cli monitor`,
the PC CLI, the GUI, and hardware tests all compete for it. Close the others first; an
"Access denied"/"port busy" error means another process holds it.

## Testing the contract
- `pc/tests/` contains a **fake device** (scripted serial double) that replays SPEC
  exchanges, including an `EVT DATA` interleaved inside a list response, `ERR` lines,
  "sensor missing" and timeouts
- Hardware tests (`@pytest.mark.hardware`) run the same exchanges against the real
  device on COM9 (port overridable via env var `UMWELT_PORT`); value checks use plausibility
  ranges (e.g. −20…60 °C, 0…100 %rH, 800…1100 hPa), never exact numbers
- When a SPEC example changes, both test sets change with it
