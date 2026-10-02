---
paths:
  - "pc/**"
---

# PC Tool Rules (Python / pyserial / Tkinter)

## Scope
A small operator tool, not an application platform: Python ≥ 3.11, package
`umwelt_ctl` in `pc/`, one runtime dependency (`pyserial`). Tkinter comes with Python.
Adding any further runtime dependency (matplotlib, pandas, numpy …) is an architecture
decision → ask the user. A live chart is drawn with a Tk `Canvas`, not a plotting library.

## Structure (src layout: `pc/src/umwelt_ctl/`, tests in `pc/tests/`)
- `protocol.py`: collect `OK`/`ERR`/list-until-`END`, parse value rows, dispatch `EVT`
  lines to callbacks, convert scaled integers to physical units. **No Tk, no argparse,
  no print()** in here
- `device.py`: open port, line I/O, ready check, time sync; port detection via
  `serial.tools.list_ports` matching USB VID `0x2341`, overridable by `--port` and env var
  `UMWELT_PORT`. Refuses firmware older than `protocol.MIN_FW_VERSION` (`FirmwareTooOld`)
- `cli.py` (`python -m umwelt_ctl …` / console script `umwelt`): `argparse` subcommands
  mirroring the protocol — `ping`, `status`, `ports`, `read`, `config`, `time [sync]`,
  `monitor`, `gui` (draft; read `cli.py` for the current set before adding commands)
- `messlog.py`: CSV measurement log, used by `monitor --csv` and the GUI
- `gui.py`: Tkinter front-end over the same device/protocol layer

## Serial handling
- Always set a read timeout; never block forever on `readline()`
- Encode/decode UTF-8 (`errors="replace"` on read); strip `\r\n`
- **No reset on connect:** DTR/RTS off before opening (see `protocol.md`)
- **Device clock:** the device has no RTC; the PC sends `TIME` after connect/`EVT BOOT` and
  periodically while connected. Log timestamps always come from the PC
- Close the port reliably (`with` / `try/finally`) — a leaked handle blocks uploads
- Translate `ERR <code>` into a domain exception with a German message; map all codes from
  SPEC.md in one table

## Tkinter: never block the mainloop (CRITICAL)
- Serial reading runs in a **background thread** that puts lines/events into a
  `queue.Queue`; the GUI polls the queue with `root.after(50–100 ms, …)`
- **Never touch a Tk widget from the reader thread**
- Commands that wait for a response run via the worker/queue as well
- Handle the four states for every view: not connected / loading / error / populated
  (plus "Sensor nicht erreichbar" as its own state)
- Confirm destructive actions (`RESET CONFIG`, clearing a log) with `messagebox.askyesno`
- Live chart: fixed-size ring of the last N points, redraw only on a new value

## CLI conventions
- Exit code 0 on success, non-zero on `ERR`, timeout, or missing device
- Human-readable German output by default (units with `°C`, `% rF`, `hPa`, decimal comma);
  machine-friendly output (`--json`, `--csv`) only if a spec asks
- No tracebacks for expected failures (port busy, device not found, `ERR` responses) —
  German one-line message saying what to do

## Measurement log (CSV)
- Absolute timestamps come from the PC, ISO 8601 with local offset,
  e.g. `2026-10-02T14:03:12+02:00`
- Semicolon-separated, UTF-8 with BOM + header row on a new/empty file (German Excel);
  append mode without a second BOM/header; **machine-readable values with a dot or
  comma decided once in SPEC** (recommend: dot-free scaled units in the file are *not*
  user-friendly → write physical units, decimal comma, documented in `docs/configuration.md`)
- Columns (draft): `zeit;temperatur_c;feuchte_proz;druck_hpa;gas_ohm;alarm`; invalid
  values stay empty, never `0`
- Default location is the user's home directory (`~/umwelt_messwerte.csv`, see
  `messlog.default_log_path()`), outside the repo; the file grows unbounded — tell the user
  where it is written, retention is their decision
- Flush after each row so a crash does not lose data

## Control Panel (PROJ-8, user decision 2026-10-02)
Analog to the sibling project `RFB Controll Panel` (`C:/Users/gerkench/OneDrive/Documents/15_Code/RFB Controll Panel`) the user wants a
desktop GUI that logs the data. Approved additions, **only for the panel** (the CLI/`umwelt_ctl` stays pyserial-only;
panel dependencies live in the optional extra `panel`): **PySide6** (GUI), SQLite via stdlib `sqlite3` (no SQLAlchemy/Alembic),
`platformdirs` (data/log paths). Package `umwelt_panel` (`pc/src/umwelt_panel/`) with the RFB layering: `core/` and `data/` import no Qt;
`ui/` only calls services; reuse `umwelt_ctl.protocol`/`device` for the serial link (no second protocol parser). Serial I/O off
the GUI thread (QThread/worker + signals). The Tk GUI (`umwelt_ctl.gui`) stays until the panel replaces it (user decision).

## Code quality
- Type hints on public functions; `ruff check pc` clean
- `logging` instead of `print()` in library code (CLI output via `print` only in the CLI layer)
- Tests in `pc/tests/` with the fake serial device — no test may require hardware unless
  marked `@pytest.mark.hardware`
- UI strings and CLI help in German with real umlauts
