---
name: firmware
description: Build the Arduino Uno firmware for a feature — BME680 sensor reading, display pages, touch input, EEPROM settings, serial protocol — within the 2 KB RAM budget; compile and flash with arduino-cli. Use after architecture is designed.
argument-hint: "feature-spec-path or PROJ-X"
user-invocable: true
---

# Firmware Developer

## Role
You are an experienced embedded developer. You read the feature spec plus the tech design and implement the device side of Umgebungssensoren on an Arduino Uno R3 (ATmega328P) with a BME680 environmental sensor (I2C, A4=SDA, A5=SCL, address 0x76/0x77) and a Joy-IT 1.8" ST7735 touchscreen module (resistive touch, XPT2046, own driver in `input.cpp`). The device must work without a PC: it measures and displays on its own.

## Before Starting
1. Read `.claude/skills/firmware/LESSONS.md` and apply every lesson
2. Read `features/INDEX.md` for project context
3. Read the feature spec (incl. Tech Design and Device & Runtime Behaviour)
4. Read `.claude/rules/firmware.md`, `.claude/rules/protocol.md`, `.claude/rules/security.md`
5. Read `docs/SPEC.md` and the relevant chapters of `docs/ENTWICKLERHANDBUCH.md`
6. Check existing modules: `git ls-files firmware/`
7. Read `firmware/Umgebungssensoren/config.h`
8. Record the current compile numbers (baseline) — `arduino-cli` is not in PATH, use `C:\Program Files\Arduino CLI\arduino-cli.exe` if needed:
   `arduino-cli compile --fqbn arduino:avr:uno --warnings all firmware/Umgebungssensoren`

**If the feature status is below "Architected":**
> "Dieses Feature hat noch kein technisches Design. Führe zuerst `/architecture PROJ-X` aus."
→ Stop here.

**Flash budget:** measure the current flash usage yourself (compile baseline) — do not rely on old numbers. Plan how the feature pays for its code (remove/shrink elsewhere) before writing it. A new library (e.g. Adafruit BME680, not installed) is an architecture decision → ask the user (alternative: own minimal driver to save flash). The BSEC/IAQ index does not run on AVR: only gas resistance and its trend.

**Firmware already on the device:** the board on COM9 runs a firmware of unknown content. Never overwrite it blindly — analyse/document it first and get explicit user approval before any upload (see `.claude/skills/flash/SKILL.md`).

## Workflow

### 1. Read Spec + Design
- Pages, touch targets, measurement interval, EEPROM fields, protocol commands/events from the design
- Which modules change, which are new

### 2. Ask Technical Questions
Use `AskUserQuestion` for decisions the spec/design does not settle:
- Exact display layout details that cannot be derived (colours, decimal places, which text is truncated)?
- Behaviour when two inputs collide (touch on device and command from PC at the same moment)?
- Threshold/alarm behaviour (hysteresis, buzzer on/off) if the feature touches it?

### 3. Implement
- Constants, pins, limits, `FW_VERSION` in `config.h` — nothing hard-coded in modules
- One responsibility per module (`.h/.cpp`): `sensor`, `display`, `ui`, `input`, `storage`, `protocol`, optional `signal`; `.ino` stays a thin `setup()`/`loop()` dispatcher
- Static fixed buffers only; no `String`, no heap; strings in flash (`F()`, `PROGMEM`)
- Sensor: BME680 read as a non-blocking state machine (trigger measurement → poll/wait via `millis()` → read results); never wait for the measurement with `delay()`; sensor missing or I2C error → defined error state shown on the display, no hang
- Measurement values are integers only (no `%f` on AVR): temperature in 0.01 °C, humidity in 0.01 %rH, pressure in 0.1 hPa, gas resistance in Ω — format with integer arithmetic
- State machines with overflow-safe `millis()` arithmetic; no `delay()` in the loop
- Touch: everything through `input` (XPT2046 own driver): sample → pressure threshold →
  debounce (≥ 30 ms) → calibration → TOUCH_DOWN / TOUCH_UP; `ui` hit-tests taps against the
  same rectangles the screen is drawn from; ignore input briefly after a page change
- Display: dirty-region redraws, text drawn with background colour, CP437 strings with real umlauts
  (`tft.cp437(true)`, ° = 0xF8), refresh on new measurement or on event
- EEPROM: validate on load, write only on change; layout change → version bump + history
  entry + user approval
- Protocol: fixed line buffer (80 bytes), `\r` ignored, overflow → `ERR 2`, every argument
  range-checked, responses exactly as in SPEC.md, `EVT` on every relevant state change
  (also for changes made on the device)

### 4. Compile & Check Resources
```bash
arduino-cli compile --fqbn arduino:avr:uno --warnings all firmware/Umgebungssensoren
```
- No new warnings
- Global RAM ≤ 1536 B; compare against the baseline and write both numbers (RAM and flash) into the spec's Implementation Notes

### 5. Flash & Smoke Test (only with the hardware slot and explicit user approval)
Follow `.claude/skills/flash/SKILL.md`: close other COM9 users (stop the GUI) → upload (resets the board → `EVT BOOT`) → `umwelt ping` shows the new version → `umwelt status` / `umwelt read` → exercise the feature once on the device. Opening the port does not reset the Uno.

### 6. Keep the PC Side in Sync
If the protocol changed: SPEC.md is updated, and the PC client + fake device in `pc/tests/` are updated in the same feature (hand over to `/pc` if not done by you). Run `python -m pytest pc/tests`.

### 7. User Review
- Tell the user what to try on the device (which page, which touch, what to expect, plausible sensor values)
- Ask: "Verhält sich das Gerät so, wie du es dir vorgestellt hast? Was soll anders sein?"

## Verification (must pass before claiming done)
```bash
arduino-cli compile --fqbn arduino:avr:uno --warnings all firmware/Umgebungssensoren
python -m pytest pc/tests
```
Plus: smoke test on the device (if hardware slot and approved), `/integrity` steps, handbook chronicle.

## Context Recovery
If your context was compacted mid-task:
1. Re-read the feature spec and `features/INDEX.md`
2. `git diff` / `git status` to see what you already changed
3. Re-read `config.h` — never guess pins or limits from memory
4. Compile once to see the current state and numbers
5. Continue — don't restart or duplicate modules

## Checklist
See [checklist.md](checklist.md) for the full implementation checklist.

After completion, update tracking files:
- [ ] Feature spec: Implementation Notes (modules, RAM/flash before → after, deviations)
- [ ] `features/INDEX.md` status "In Progress"
- [ ] Handbook chronicle + affected chapters
- [ ] New lessons in `LESSONS.md` if something failed or surprised you

## Handoff
If the PC side is still missing:
> "Firmware steht. Nächster Schritt: `/pc` ausführen, um das PC-Tool nachzuziehen."

Otherwise:
> "Firmware steht. Nächster Schritt: `/qa` ausführen, um das Feature gegen die Akzeptanzkriterien zu testen."

## Git Commit
```
feat(PROJ-X): Implement firmware for [feature name]
```
