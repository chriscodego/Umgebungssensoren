---
name: flash
description: Compile the firmware, upload it to the Arduino on COM9 with arduino-cli, and smoke-test it over serial (PING, STATUS, READ; the upload reset sends EVT BOOT). Use during development whenever the device should run the current code — only with explicit user approval, because the existing firmware is overwritten.
argument-hint: "optional: port (default COM9)"
user-invocable: true
allowed-tools: Read, Glob, Grep, Bash
---

# Flash & Smoke Test

## Role
You put the current firmware onto the Arduino and prove it boots, reads the sensor and speaks the protocol. You do not change code. Currently there is only one device (COM9), so development and production board are the same: **every upload overwrites the firmware that is on the device now** and needs explicit user approval beforehand. A release flash (`/release`) additionally follows the release steps.

## Before Starting
1. Read `.claude/skills/flash/LESSONS.md`
2. Port: argument, else `UMWELT_PORT`, else COM9 — confirm with `arduino-cli board list` (Uno = VID 2341 / PID 0043)
3. Make sure nothing else holds the port: no `arduino-cli monitor`, no `umwelt monitor`/`umwelt gui` (stop the GUI before uploading), no Arduino IDE serial monitor, no running hardware tests. If a subagent might hold it, ask the orchestrator (only one agent may use COM9)
4. **Existing firmware:** if the firmware currently on the device has not been analysed/documented yet (first upload), do that first (e.g. read the serial output, `arduino-cli`/avrdude flash read-back as backup if the user wants it) and ask the user for approval to overwrite. Ask "Die vorhandene Firmware auf COM9 wird überschrieben — freigeben?" before step 3 (Upload)

## Steps

### 1. Toolchain (one-time, only if missing)
`arduino-cli` lives at `C:\Program Files\Arduino CLI\arduino-cli.exe` and is not in PATH — call it by absolute path if needed.
```bash
arduino-cli core install arduino:avr
arduino-cli lib install "Adafruit GFX Library" "Adafruit ST7735 and ST7789 Library"
```
Installed: Adafruit GFX 1.12.6, Adafruit ST7735/ST7789 1.11.0, Adafruit BusIO 1.17.4. No touch library: the XPT2046 driver is part of the firmware (`input.cpp`). The BME680 library (Adafruit BME680) is **not** installed — installing it is an architecture decision that needs user approval (alternative: own minimal driver).

### 2. Compile
```bash
arduino-cli compile --fqbn arduino:avr:uno --warnings all firmware/Umgebungssensoren
```
Report "Sketch uses … bytes (…%)" and "Global variables use … bytes (…%)". Stop if global RAM > 1536 B, flash ≥ 100 % or new warnings appeared — report instead of flashing (mention any flash growth against the last recorded number).

### 3. Upload
```bash
arduino-cli upload -p COM9 --fqbn arduino:avr:uno firmware/Umgebungssensoren
```
Typical failures:
- `Access is denied` / `port busy` → another process holds COM9 (step "Before Starting" 3)
- `avrdude: stk500_recv(): programmer is not responding` → wrong port, cable, or board not powered; re-check `arduino-cli board list`

### 4. Smoke Test
The upload itself resets the board: the new firmware sends `EVT BOOT <FW_VERSION>` ~2.75 s after the upload, usually before any tool has the port open. Opening the port with the PC tool does **not** reset the Uno (DTR/RTS off), so do not expect another `EVT BOOT` — the `PING` version proves the new firmware runs. Use the PC tool (preferred — it handles the ready check: short `EVT BOOT` wait, blank line, quick `PING`):
```bash
umwelt --port COM9 ping
umwelt --port COM9 status
umwelt --port COM9 read
```
Expected: `OK PONG Umgebungssensoren <FW_VERSION>` with the version from `config.h`, a sane `STATUS`, and a `READ` with plausible values (room temperature, humidity 20–80 %rH, pressure ~ 950–1050 hPa, gas resistance in the kΩ range; right after boot the gas value may still be settling). If the sensor is not found, the firmware must report a defined sensor error — check wiring (A4/A5, address 0x76/0x77, 3.3 V vs. 5 V module) before blaming the code. If the PC tool is not usable, a minimal pyserial one-liner via `python -c` is acceptable: set `dtr=False`/`rts=False` **before** opening, send `\n`, then `PING\n`, and print the reply lines. (Only if you explicitly want to see `EVT BOOT`: open with DTR — that resets the board — and wait ~3 s.)

### 5. Look at the Device
Ask the user to confirm the display shows the start page (overview with temperature, humidity, pressure, gas value, no garbage, values match `READ`) — you cannot see it.

## Output
```
Flash COM9: OK / FEHLER
Build: Flash xxxxx B (xx %) · RAM xxx B (xx %) · Warnungen: 0
Boot: PING OK (FW x.y.z) · READ plausibel / Sensorfehler
Anzeige: vom Nutzer bestätigt / offen
```

## Important
- Never upload without explicit user approval — the firmware currently on the device is overwritten (single device: dev = production); settings in EEPROM survive an upload unless the layout version changed
- Never leave the port open after the smoke test
- Write a lesson to `LESSONS.md` when something about ports, reset timing, sensor wiring, or the toolchain surprised you
