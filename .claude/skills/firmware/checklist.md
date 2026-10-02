# Firmware Implementation Checklist

## Memory
- [ ] No `String`, no `malloc`/`new`, no STL
- [ ] All buffers fixed-size from `config.h` limits; every copy bounded and NUL-terminated
- [ ] Constant strings in flash (`F()`, `PROGMEM`, `*_P` functions)
- [ ] No recursion, no large local arrays (history/trend buffers sized from `config.h`, counted in the RAM budget)
- [ ] Global RAM ≤ 1536 B after compile; before/after numbers noted in the spec
- [ ] Flash usage re-measured (not copied from old notes) and noted; growth must be paid for elsewhere, ≥ 100 % blocks

## Loop & Timing
- [ ] No `delay()` outside `setup()`; no busy-wait loops
- [ ] All timing via `(uint32_t)(now - start) >= interval`
- [ ] Sensor measurement cycle, alarm blink, buzzer, page switching, debounce are state machines
- [ ] One `loop()` pass stays well under 50 ms (display redraw and I2C read included)
- [ ] Threshold alarms and `EVT` events fire exactly once per violation (hysteresis, no flapping)

## Sensor (BME680)
- [ ] I2C address 0x76/0x77 from `config.h`; sensor absent / read error → defined error state, no hang, no stale value shown as valid
- [ ] Measurement triggered and collected non-blocking; interval from `config.h`/EEPROM, range-checked
- [ ] Values kept as integers (0.01 °C, 0.01 %rH, 0.1 hPa, Ω); no `%f`, no `float` formatting on AVR
- [ ] Gas resistance shown as value + trend only (no IAQ index — BSEC does not run on AVR); warm-up/burn-in noted for the user
- [ ] Calibration offsets (if any) range-checked and stored in EEPROM
- [ ] No new sensor library without user approval (own minimal driver is the flash-saving alternative)

## Structure
- [ ] Every pin, limit, timing, `FW_VERSION` in `config.h`
- [ ] `.ino` is a thin dispatcher; one responsibility per module
- [ ] Checked existing modules before adding new ones (`git ls-files firmware/`)
- [ ] No duplicated tables (hit-test rectangles, error texts, keyword lists)

## Touch & Display
- [ ] Touch goes through the input module only; no controller specifics outside it
- [ ] No new library (XPT2046 and buzzer drivers are our own) unless approved by the user
- [ ] Pressure threshold + debounce ≥ 30 ms; input ignored briefly after page change
- [ ] Targets ≥ ~24×24 px (SPEC), larger where space allows; drawing and hit-testing use the same rectangle table
- [ ] Touch calibration stored in EEPROM and reachable on the device
- [ ] Redraw only dirty regions (changed value, not whole page); no `fillScreen()` in `loop()`; no flicker
- [ ] Display strings with real umlauts (CP437), units °C (0xF8 + `C`), %, hPa; everything fits the 160 px width

## EEPROM
- [ ] Magic + layout version + CRC + field ranges validated on load; invalid → defaults
- [ ] Writes only on change, never every loop pass (no logging of measurements into EEPROM)
- [ ] Layout change → version bump, `docs/eeprom-layout-history.md`, user approval

## Protocol & Input Validation
- [ ] Commands, responses, error codes, events exactly as in `docs/SPEC.md`
- [ ] Line buffer 80 bytes, overflow → discard to `\n` + `ERR 2`; `\r` ignored; empty lines ignored; case-insensitive
- [ ] Every numeric argument range-checked before use (measurement interval, thresholds, `0|1` flags, config index, `TIME` hh 00–23 / mm, ss 00–59)
- [ ] State checks as defined in SPEC.md (e.g. `READ` while sensor error / not yet measured → defined error code, not a bogus value)
- [ ] Measurement values on the wire are integers in the units fixed in SPEC.md
- [ ] Device-side and serial changes emit the matching `EVT` (after the `OK`); `EVT BOOT` on every start
- [ ] Protocol change? → SPEC.md, PC client, fake device tests updated in the same feature

## Verification (run before marking complete)
- [ ] `arduino-cli compile --fqbn arduino:avr:uno --warnings all firmware/Umgebungssensoren` — no new warnings
- [ ] `python -m pytest pc/tests` passes
- [ ] Flashed (with explicit user approval, existing firmware gets overwritten) and smoke-tested (`umwelt ping` shows the new version, `status`, `read`, feature once) — if hardware slot
- [ ] Sensor values plausible on the device (room temperature, humidity, pressure ~ local level)
- [ ] All acceptance criteria addressed on the device side
- [ ] `/integrity` steps executed
- [ ] Handbook chronicle updated
- [ ] `features/INDEX.md` status "In Progress"

## Completion
- [ ] User has tried the feature on the device and approved
- [ ] Code committed to git
