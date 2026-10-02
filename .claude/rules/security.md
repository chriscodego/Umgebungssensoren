---
paths:
  - "firmware/**"
  - "pc/**"
---

# Security & Data Rules

The threat model is small: a device on a desk/wall and a PC tool on a laptop. No network,
no accounts. What matters is **robustness against bad input**, **robustness against bad
sensor data**, and a sane handling of the measurement log.

## Untrusted input on the device
Everything arriving over Serial is untrusted (a typo, a wrong baud rate, a different
program writing to the port):
- Fixed-size line buffer, hard length limit (80 bytes), overflow → discard rest of line,
  `ERR 2`
- Every numeric argument range-checked before use (threshold ranges, interval limits,
  `0|1` flags, `TIME` fields) — non-numeric → `ERR 2`, out of range → `ERR 3`
- Config values that come in must be plausible (e.g. interval 1…3600 s, thresholds within
  the sensor's physical range, low < high) before they reach EEPROM
- State-dependent commands checked against the device state
- Never trust EEPROM contents either: validate magic, version, CRC, and every field range
  on load; on mismatch → defaults
- No path where malformed input can stall `loop()`

## Untrusted sensor data
- I2C failures (NACK, timeout, wrong chip id) are normal: bounded retries, then a defined
  "sensor missing" state — never an endless loop, never stale values shown as current
- Values outside the physical range or a failed measurement (gas heater not stable, status
  flags of the BME680) are marked invalid, not displayed or logged as real numbers
- Alarms must not be silenced by a missing sensor: "no data" is its own state and is visible

## PC tool
- No `eval`/`exec`/`pickle` on anything read from the port or from files
- `subprocess` (if ever needed) with an argument list, never `shell=True`
- No secrets exist in this project; never add any to the repo
- Parse incoming values defensively: an `EVT DATA` with garbage fields is logged and
  skipped, not a crash and not a CSV row

## Measurement log
The CSV records environmental values over time. It carries no names, but it can reveal
presence/habits of whoever is in the room (temperature/CO2-like trends) and is local data:
- Never commit logs (`.gitignore` covers `pc/logs/`, `*.log`, `*messwerte*.csv`); the
  default path `~/umwelt_messwerte.csv` is outside the repo
- Tell the user where the file is written; local, not a shared drive, unless the user decides otherwise
- Deletion/retention is the user's decision — ask before building automatic retention
- Do not put the log's contents into artifacts, issues or commit messages

## Dependencies & supply chain
- Firmware libraries only from the Arduino Library Manager with a pinned version noted
  in the handbook; PC dependencies pinned with a lower bound in `pc/pyproject.toml`
- Run `pip-audit` before a release
- A new library/dependency (e.g. Adafruit BME680) is an architecture decision — ask the user first

## Review triggers (require explicit user approval)
- **Any upload to the device** while it still holds the unknown pre-existing firmware
- Any EEPROM layout change (stored settings fall back to defaults)
- Any protocol change (see `protocol.md`)
- Any change to where the measurement log is written or what it contains
- Any new dependency
