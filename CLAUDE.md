# Umgebungssensoren

> Arduino-Anzeige für Umgebungssensoren: zeigt Temperatur, Luftfeuchte, Luftdruck und
> Luftqualität (Gaswiderstand) eines **BME680** auf einem Touch-Display, warnt bei
> Schwellwertverletzung und liefert die Messwerte an ein kleines Python-PC-Tool über
> USB-Serial (CLI, Live-`monitor`, CSV-Messprotokoll, Tkinter-GUI). Entwickelt mit einem
> AI-Workflow aus spezialisierten Skills (Spec, Architektur, Firmware, PC-Tool, QA, Release).
> Struktur und Workflow sind von GloveboxControl übernommen.

## What this is
Two programs that share **one contract**:
1. **Firmware** for an Arduino Uno R3 (ATmega328P — 2 KB RAM, 32 KB flash, 1 KB EEPROM)
   with a Joy-IT 1.8" 160×128 ST7735 **touchscreen module** (RB-TFT1.8-T, resistive touch,
   **XPT2046**, own minimal driver) and a **BME680** environmental sensor on I2C
   (A4 = SDA, A5 = SCL, address 0x76/0x77). The firmware runs **autonomously**; a PC is
   optional. Flash is scarce — every feature must pay for its code.
2. **PC tool** (`pc/`, Python package `umwelt_ctl`): pyserial CLI, live `monitor` with
   CSV measurement log, and a small Tkinter GUI.

The contract between them is the line-based serial protocol in **`docs/SPEC.md`**. Not a
web app, no server, no database, no cloud.

**Current state:** the device on **COM9** already runs an unknown, pre-existing firmware.
Before the first upload it must be analysed and documented (`docs/ENTWICKLERHANDBUCH.md`,
chapter "Bestandsgerät") — never overwrite it blindly (see "Flashing" in `general.md`).

## Tech Stack

- **Firmware:** Arduino C++ (AVR, `arduino:avr:uno`), built and flashed with `arduino-cli`
  (`C:\Program Files\Arduino CLI\arduino-cli.exe`, not in PATH on this machine)
- **Display:** Adafruit ST7735 + Adafruit GFX (SPI, rotation 1 → 160×128)
- **Touch:** XPT2046 on the shared SPI bus (T_CS D4, T_IRQ D2), own minimal driver in
  `input.cpp` (no touch library)
- **Sensor:** BME680 over I2C (`Wire`). No BSEC on AVR → temperature, humidity, pressure,
  gas resistance and a trend only. The driver choice (Adafruit BME680 library vs. own
  minimal driver) is an **architecture decision needing user approval** (flash!)
- **Persistence (firmware):** EEPROM with magic + layout version + CRC: interval,
  thresholds, units, touch calibration
- **PC tool:** Python 3.11+, `pyserial`, `argparse` CLI, Tkinter GUI (stdlib)
- **Tests:** pytest (host-side, fake serial) + hardware-in-the-loop tests over COM9
  (marker `hardware`, opt-in)
- **Quality:** compiler warnings (`--warnings all`), ruff for `pc/`

## Project Structure

```
firmware/Umgebungssensoren/   Arduino sketch (folder name == .ino name)
  Umgebungssensoren.ino       setup()/loop() — thin, delegates to modules
  config.h                    ALL pins, limits, timings, FW_VERSION
  *.h / *.cpp                 modules (sensor, storage, display, ui, input, protocol, signal …)
pc/                           Python PC tool (pyproject.toml, src layout, console script `umwelt`)
  src/umwelt_ctl/
    protocol.py               line parsing, responses, EVT dispatch (no Tk, no argparse)
    device.py                 serial connection, port detection (VID 0x2341 / UMWELT_PORT)
    cli.py                    argparse CLI incl. `monitor`
    messlog.py                CSV measurement log (default ~/umwelt_messwerte.csv)
    gui.py                    Tkinter GUI
  tests/                      pytest with a scripted fake device; hardware tests @pytest.mark.hardware
.github/workflows/ci.yml      Firmware compile + PC host tests (no hardware)
docs/
  SPEC.md                     Hardware, data model, display, SERIAL PROTOCOL (contract)
  PRD.md                      Product Requirements Document
  ENTWICKLERHANDBUCH.md       Binding conventions, known pitfalls, development chronicle
  hardware.md                 Wiring, components, troubleshooting
  configuration.md            Port, log location, environment variables
  eeprom-layout-history.md    Every EEPROM layout version and what it did to stored config
  release-notes.md            Per-version notes (firmware + PC tool)
features/                     Feature specifications (PROJ-X-name.md)
  INDEX.md                    Feature status overview
  archive/                    Specs of released features
.claude/                      rules/, skills/, agents/, settings.json
```

## Architecture Rules (MANDATORY)
- **`docs/SPEC.md` is the contract.** A protocol change updates SPEC.md, the firmware,
  the PC tool, and the tests **in the same change** — never one side alone.
- **Firmware:** non-blocking `loop()` (no `delay()` in the main path), `millis()` with
  overflow-safe subtraction, no `String`, no `malloc`/`new`, constant strings in flash
  (`F()` / `PROGMEM`), all pins and limits in `config.h`. Sensor reads are state machines
  (BME680 forced mode: trigger → wait → read), never blocking waits. Touch input goes
  through one small input module; the UI hit-tests taps against the drawn rectangles.
- **PC tool:** protocol logic is importable and testable without a serial port or a
  Tk window; the GUI never blocks its mainloop on serial I/O.

## Development Workflow

1. `/init` — PRD + feature map
2. `/write-spec` — Full feature spec for one feature
3. `/architecture` — Technical approach (PM-friendly, no code): screens, EEPROM, RAM budget, protocol impact
4. `/firmware` — Build the Arduino side
5. `/pc` — Build the PC tool side (CLI, monitor, GUI)
6. `/qa` — Test against acceptance criteria: host tests + hardware-in-the-loop checklist
7. `/release` — Version bump, flash the device, install PC tool, tag
8. `/archive` — Archive released specs, reset INDEX.md for the next cycle

`/flash` builds, uploads to COM9 and smoke-tests at any time. `/integrity` checks
structure, protocol consistency and regressions after every feature/fix (runs
automatically, see `.claude/rules/code-integrity.md`). `/autonom` runs steps 3–6 for all
planned features autonomously, asking only about material decisions. `/refine PROJ-X`
revisits an existing spec. `/help` tells you where you stand.

**Plan first:** every task that changes code, config, firmware on the device or git
history starts with a plan shown to the user and an explicit go-ahead
(`.claude/rules/plan-approval-artifact.md`).

**Binding handbook:** `docs/ENTWICKLERHANDBUCH.md` is read before work and updated
(chronicle + affected chapters) after every change (`.claude/rules/developer-handbook.md`).

**Ordering rule for steps 4 and 5:** if the feature changes the protocol, `/firmware`
goes first (it defines the behaviour on the wire), then `/pc`. PC-only features skip `/firmware`.

## Feature Tracking

All features tracked in `features/INDEX.md`. Every skill reads it at start and updates it
when done. Feature specs live in `features/PROJ-X-name.md`; released specs move to
`features/archive/`.

## Key Conventions

- **Feature IDs:** PROJ-1, PROJ-2, ... (sequential)
- **Commits:** `feat(PROJ-X): description`, `fix(PROJ-X): description`, `build(PROJ-X): ...`
- **Single Responsibility:** One feature per spec file
- **Human-in-the-loop:** all workflows have user approval checkpoints
- **Lessons learned:** every skill reads its `LESSONS.md` first and appends a lesson after
  a failure or correction (`.claude/rules/lessons-learned.md`)
- **No test weakening:** a red test is a bug or a user-approved behaviour change, never
  something to delete
- **Only one process owns COM9.** Close monitor/GUI before `arduino-cli upload`. Opening
  the port does **not** reset the Uno (the PC tool opens with DTR/RTS off); an upload does
  reset it (→ `EVT BOOT`)
- **Language:** code, comments, identifiers and commits in English; acceptance criteria,
  specs and PC-tool UI strings in German with real umlauts (ä/ö/ü/ß); **display texts on
  the TFT also use real umlauts** via the GFX classic font in CP437 mode (`tft.cp437(true)`;
  ä=0x84 ö=0x94 ü=0x81 Ä=0x8E Ö=0x99 Ü=0x9A ß=0xE1, ° = 0xF8)
- **Talk to the user in German**

## Build, Flash & Test Commands

`arduino-cli` is not in PATH here; use `& "C:\Program Files\Arduino CLI\arduino-cli.exe"`
(PowerShell) or add the folder to PATH.

```bash
# Firmware (one-time setup; GFX/ST7735/BusIO are already installed)
arduino-cli core install arduino:avr
arduino-cli lib install "Adafruit GFX Library" "Adafruit ST7735 and ST7789 Library"
# BME680 driver: only after the architecture decision (library vs. own driver)

# Firmware (daily)
arduino-cli compile --fqbn arduino:avr:uno --warnings all firmware/Umgebungssensoren
arduino-cli board list                                   # find the port (currently COM9)
arduino-cli upload -p COM9 --fqbn arduino:avr:uno firmware/Umgebungssensoren   # needs approval, see general.md
arduino-cli monitor -p COM9 -c baudrate=115200           # raw serial console

# PC tool
pip install -e "pc[dev]"                 # editable install incl. pytest
python -m umwelt_ctl --help              # CLI (also installed as `umwelt`)
python -m umwelt_ctl ping                # connection + firmware version
python -m umwelt_ctl monitor --csv messwerte.csv   # live events + CSV measurement log
python -m umwelt_ctl gui                 # Tkinter GUI
python -m pytest pc/tests                # host tests (no hardware needed)
python -m pytest pc/tests -m hardware    # hardware-in-the-loop, device on COM9
ruff check pc                            # lint (add ruff to the dev extras)
```

Quality gates before any feature counts as done: firmware compiles **without new
warnings** and within the RAM budget (see `.claude/rules/firmware.md`), `python -m pytest
pc/tests` passes, `ruff check pc` passes. Features touching the device additionally need
the hardware smoke test (`/flash`) on COM9.

## Product Context

@docs/PRD.md

## Feature Overview

@features/INDEX.md
