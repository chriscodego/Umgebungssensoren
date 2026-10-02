# PC Tool Implementation Checklist

## Structure
- [ ] Checked existing modules and tests (`git ls-files pc/`) before adding new ones
- [ ] Protocol parsing only in `protocol.py`; serial/port handling only in `device.py`; CSV only in `messlog.py`
- [ ] CLI (`cli.py`) and GUI (`gui.py`) never parse raw protocol lines themselves
- [ ] No new runtime dependency (only `pyserial`) unless approved by the user
- [ ] No `print()` outside the CLI layer — `logging` instead

## Protocol & Serial
- [ ] Commands, responses, error codes exactly as in `docs/SPEC.md`
- [ ] `EVT` lines inside multi-line responses handled; unknown `EVT` types ignored (logged)
- [ ] Integer wire values converted to °C / %rH / hPa / Ω in one place only; no float drift in stored values (rounding defined)
- [ ] Read timeouts set; no unbounded `readline()` waits
- [ ] Port closed reliably (`with` / `finally`) — no leaked handle blocking `arduino-cli upload`
- [ ] Port opened with DTR/RTS off (no reset on connect); ready check = short `EVT BOOT` wait + blank line + quick `PING`, fallback wait for `EVT BOOT` if the board reset anyway; mid-session `EVT BOOT` → re-read `STATUS` (and re-send `TIME`)
- [ ] `PING` version check on connect with a German warning for too-old firmware
- [ ] Port detection via VID 0x2341, `--port` and `UMWELT_PORT` honoured

## CLI
- [ ] German help texts with real umlauts
- [ ] Exit code 0 on success, non-zero on `ERR`/timeout/no device
- [ ] Expected failures print one German line, no traceback
- [ ] Commands that change device settings or overwrite data (`config set`, reset of settings, overwriting an existing CSV) ask or require an explicit flag
- [ ] `monitor` stops cleanly on Ctrl+C (port closed, CSV flushed)

## GUI (Tkinter)
- [ ] Serial I/O in a background thread; queue + `root.after` polling
- [ ] No widget touched from the reader thread
- [ ] Mainloop never frozen (> ~100 ms)
- [ ] States: not connected / loading / error (sensor error) / populated
- [ ] Destructive actions confirmed with `messagebox.askyesno`
- [ ] Window usable at small sizes; texts and units not clipped

## Measurement Log (CSV, if touched)
- [ ] PC timestamps ISO 8601 with offset; semicolon-separated; UTF-8 with BOM; header row on new/empty file only; append mode
- [ ] Columns and units documented in `docs/SPEC.md`/handbook (temperature, humidity, pressure, gas resistance)
- [ ] Sensor error / missing value → empty cell or defined marker, never a fake number
- [ ] Default path `~/umwelt_messwerte.csv` outside the repo; user told where it is written; no automatic retention/deletion
- [ ] Log files not committed (`.gitignore`)

## Tests
- [ ] Fake-device tests for every new/changed command, incl. `ERR` paths
- [ ] Interleaved `EVT` test
- [ ] Value conversion tests (negative temperature, boundaries)
- [ ] Timeout / no device / port busy tests
- [ ] Hardware variants marked `@pytest.mark.hardware` (not run by default)
- [ ] Existing tests not weakened or deleted

## Verification (run before marking complete)
- [ ] `python -m pytest pc/tests` passes
- [ ] `ruff check pc` passes
- [ ] Tried against the device on COM9 (if hardware slot)
- [ ] All acceptance criteria addressed on the PC side
- [ ] `/integrity` steps executed; handbook chronicle updated
- [ ] `features/INDEX.md` status "In Progress"

## Completion
- [ ] User has tried the CLI/GUI and approved
- [ ] Code committed to git
