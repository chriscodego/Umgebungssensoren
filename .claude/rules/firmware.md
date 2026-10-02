---
paths:
  - "firmware/**"
---

# Firmware Rules (Arduino Uno R3 / ATmega328P)

## The budget is the design constraint
| Resource | Size | Rule |
|---|---|---|
| SRAM | 2048 B | Globals + statics ≤ **1536 B (75 %)** as reported by `arduino-cli compile`; the rest is stack. Adafruit GFX/ST7735 and the Serial buffers already take a noticeable share |
| Flash | 32256 B usable | Measure the baseline at the first compile and record it in the handbook. The reference project (GloveboxControl) ended at ~95 % with display + touch + protocol — adding a sensor driver on top will be tight. > 95 % is an architecture topic, not a footnote |
| EEPROM | 1024 B | Layout documented in `docs/SPEC.md` + `docs/eeprom-layout-history.md` |

Read the "Sketch uses … / Global variables use …" lines after **every** compile and
note the numbers in the spec's implementation notes when they change noticeably.
Low-memory symptoms on AVR are silent: random resets, garbage on the display, corrupted
serial output. If you see those, suspect RAM first.

## Memory discipline (MANDATORY)
- **No `String`** (Arduino String class) — heap fragmentation kills a 2 KB device. Use
  fixed `char` buffers, `strncpy`/`snprintf` with explicit sizes, always NUL-terminate
- **No `malloc`/`new`/STL containers** — all storage is static and sized by `config.h`
  limits (`LINE_MAX = 80`, `MAX_TOKENS`, history ring size …) — read `config.h` for the current set
- **Constant strings in flash:** `Serial.print(F("..."))`, `PROGMEM` tables for menus and
  error texts, `strcmp_P`/`strncasecmp_P` for keyword matching
- No recursion; keep local arrays small (stack shares the 2 KB)
- **`snprintf` on AVR has no `%f`** — keep measurements as scaled integers (see below) and
  format with integer division/modulo. No `float` math where integer math does it (flash!)
- Any measurement history (graph/min/max) is a fixed ring buffer with its size in `config.h`

## Sensor (BME680, I2C)
- Own module `sensor.*` is the only one that knows the BME680 and `Wire`. Address 0x76 or
  0x77 (SDO pin) in `config.h`; probe at boot and handle "sensor missing" as a normal state
  (display `--`, protocol error/flag, no crash, no endless retry that blocks the loop)
- The BME680 measurement is a **state machine**: trigger forced mode → wait for the
  measurement duration (non-blocking, `millis()`) → read → compensate. Never
  `delay()` for the conversion
- Gas heater profile (typically 320 °C / 150 ms) dominates the duration and power draw and
  self-heats the sensor: temperature needs an offset/compensation; **do not read the gas
  value more often than the configured interval** and document the chosen profile
- No BSEC on AVR: expose **temperature, humidity, pressure, gas resistance** and (optional)
  a relative trend. Never present a made-up "IAQ" number as an absolute index
- Values travel as scaled integers: temperature in 0.01 °C (`int16_t`), humidity in
  0.01 %rH, pressure in 0.1 hPa (or Pa/10), gas resistance in Ω (`uint32_t`). Define the
  scales once in `config.h`/`SPEC.md`
- The BME680 module's supply/logic level must be verified before wiring to the Uno's 5 V
  (many breakouts have a regulator + level shifter, bare chips are 3.3 V only) — see
  `docs/hardware.md`
- The library-vs-own-driver decision is an architecture decision (flash, user approval).
  Wire's default 32-byte buffer and the blocking `Wire` calls are fine for the short reads here

## Non-blocking main loop (MANDATORY)
- `loop()` is a dispatcher: poll serial → poll input → run sensor state machine → evaluate
  alarms → redraw what is dirty → signal. Every step returns quickly (target < 10 ms,
  hard limit 50 ms per pass)
- **No `delay()`** outside `setup()`. Timing via `millis()` state machines
- Alarm blinking, buzzer patterns, page changes, debouncing are state machines, not loops
  with delays; long drawing jobs run in steps
- Buzzer (if present): own minimal Timer2 driver as in the reference project — never
  `tone()` if flash is tight, never busy-wait for a tone to finish
- Time math is overflow-safe: `if ((uint32_t)(now - start) >= interval)` — never
  `if (now >= start + interval)`. `millis()` wraps after ~49.7 days, and this device
  runs for months
- Alarm thresholds need **hysteresis** and a minimum duration so a value flickering around
  the limit does not toggle the alarm

## Pins and constants
- Every pin, timing, limit, and `FW_VERSION` lives in `config.h` — no magic numbers
  in modules
- Display SPI: CS D10, DC D9, RST D8, MOSI D11, SCK D13. D11/D12/D13 are the hardware SPI
  bus — anything else on SPI needs its own CS and must release the bus
- Touch (XPT2046): T_CS D4, T_IRQ D2 (active LOW, no AVR pull-up), MISO D12; buzzer D5
- BME680: I2C on A4 (SDA) / A5 (SCL) — no conflict with the above; do not reuse A4/A5

## Touch input (XPT2046, own driver)
Same design as the reference project: `input` is the only module that knows the
controller:
```
IRQ gate → raw sample → pressure/plausibility threshold → debounce
        → calibrate → screen x/y → events TOUCH_DOWN / TOUCH_UP; hit-testing in ui.cpp
```
- Own CS pin, SPI clock lower than the display (2 MHz), bus released between transactions
- Calibration in its own EEPROM block with CRC; defaults measured on the module apply until
  calibrated on the device (reachable on the device without a PC)
- Debounce: press stable ≥ 30 ms, release stable ≥ 60 ms; ignore touches ~150 ms after a
  screen change
- Hit targets ≥ ~24×24 px, larger where space allows; draw and hit-test from the **same**
  rectangle table in `config.h`/`ui.cpp`
- A new touch library is an architecture decision → ask the user

## Display (ST7735, Adafruit GFX)
- Rotation 1 → 160 wide × 128 high. `initR(...)` tab variant depends on the panel batch;
  wrong colours or a garbage border mean the wrong variant — record the working one in
  `config.h` and the handbook
- **Redraw only what changed** (dirty flags per value field); never `fillScreen()` in
  `loop()` — it flickers and takes ~50 ms+. Full clear only on a page change
- Overwrite text with background colour set (`setTextColor(fg, bg)`) instead of clearing
  rectangles where possible; right-align or fix the width of changing numbers so no stale
  digits remain (e.g. `9.9` → `10.1`)
- Update the sensor values when a new measurement arrives, not every pass
- Text uses CP437 (`tft.cp437(true)`) so umlauts and `°` render
- Colour carries meaning (value in range / warning / alarm) but must not be the only
  signal — add a symbol or text for colour-blind readers

## EEPROM
- Layout (from address 0): magic + layout version + config (measurement interval,
  thresholds, units, offsets …) + CRC-8, then touch calibration with its own CRC-8.
  Details: `docs/eeprom-layout-history.md`
- On invalid magic/version/CRC → load defaults (SPEC.md), do not crash, do not half-read
- **Write only on change**, never in `loop()` on every pass — 100 000 write cycles per
  cell. **Never write measurement history to EEPROM** (ring buffers live in RAM)
- Changing the struct layout **bumps the layout version**, documents it in
  `docs/eeprom-layout-history.md`, and — because old configs fall back to defaults — is a
  user-approved decision
- The device clock (`TIME`) is RAM only; no RTC → timestamps are added by the PC

## Serial
- 115200 8N1; read non-blocking into a fixed line buffer (`LINE_MAX` = 80 bytes); on overflow
  discard until `\n` and answer `ERR 2 …`; ignore `\r`
- Never block on `Serial.print` in a way that stalls the loop — keep responses short;
  the TX buffer is 64 B. Periodic `EVT DATA` lines are rate-limited by the measurement interval
- Protocol details: `.claude/rules/protocol.md`

## Code style
- C++ as supported by avr-gcc in the Arduino core (C++11/14 subset); no exceptions, no RTTI
- `static` for module-private state; `const`/`constexpr` for constants; fixed-width
  integer types where range matters
- Compile with `--warnings all`; a new warning is treated as a failing gate
- Comments in English; display strings in German with real umlauts (CP437 bytes in PROGMEM)

## What NOT to do here
- No `String`, no heap, no `delay()` in the loop, no blocking `while (!Serial.available())`
- No hard-coded pins or I2C addresses outside `config.h`
- No `float` printing, no BSEC/IAQ claims, no raw sensor values shown as "Luftqualität"
- No Serial debug spam in release builds — debug output must not collide with the protocol
