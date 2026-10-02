# General Project Rules

## What this project is
Two small programs bound by one contract:
- **Firmware** (`firmware/Umgebungssensoren/`): Arduino Uno R3, C++, BME680 environmental
  sensor (I2C), ST7735 touchscreen display (resistive touch, XPT2046, own driver), EEPROM
  persistence, optional piezo alarm. Runs **autonomously** — the device must be fully
  usable without a PC.
- **PC tool** (`pc/`, package `umwelt_ctl`): Python 3.11+, pyserial, CLI + `monitor`
  (CSV measurement log) + Tkinter GUI.
- **Contract:** the serial protocol in `docs/SPEC.md` (see `.claude/rules/protocol.md`).

Never introduce web-app or server patterns here: no web server, no REST API, no
database server, no cloud service/MQTT, no Qt/PySide outside the Control Panel (PROJ-8, `umwelt_panel`, user decision 2026-10-02; the CLI stays Tk-/stdlib-only).
If a task seems to need one of these, it is the wrong task for this project — ask the user.

## New Project Detection (MANDATORY)
Before starting ANY work, check if the project has been initialized:
1. Read `docs/PRD.md` — if it still contains placeholder text like "_Describe what you are building_", the project is NOT initialized
2. Read `features/INDEX.md` — if the features table is empty, no features have been defined

**If the project is not initialized:**
- Do NOT write any code
- Tell the user: "Dieses Projekt ist noch nicht aufgesetzt. Führe `/init` mit einer Beschreibung aus."
- If the user already described their idea in the current message, run `/init` automatically

**If the project is initialized but the user requests a feature not yet in INDEX.md:**
- Guide them to run `/write-spec` first to create the feature spec before any implementation

## Existing device firmware (MANDATORY)
The Arduino on COM9 already runs a firmware nobody has documented. Until the handbook
chapter "Bestandsgerät" says otherwise:
- Do not upload anything without explicit user approval — the upload replaces the existing
  firmware irreversibly (reading flash back with avrdude is possible but must be done
  *before* the first upload, if the user wants a backup)
- Finding out what is on it is allowed and encouraged: `arduino-cli board list`, opening
  the port read-only (DTR/RTS off) and observing its output, asking the user for the
  original source

## Architecture (MANDATORY)
```
firmware/Umgebungssensoren/
  Umgebungssensoren.ino  setup()/loop() only — thin dispatcher
  config.h               every pin, limit, timing constant, FW_VERSION
  modules (.h/.cpp)      sensor (BME680) · storage (EEPROM) · display · ui · input (touch) ·
                         protocol (serial parser + responses/events) · signal (buzzer)
pc/src/umwelt_ctl/
  protocol.py            command/response parsing, EVT dispatch → no Tk, no argparse
  device.py              serial connection, port detection, reset/boot handling
  cli.py                 argparse front-end incl. `monitor` (live events)
  messlog.py             CSV measurement log
  gui.py                 Tkinter front-end → calls device/protocol, never parses lines itself
```
- Firmware modules talk through small C++ interfaces; the protocol module never draws on
  the display, the display module never reads Serial, only `sensor` touches the BME680 / `Wire`.
- The PC protocol client is testable without a real port (inject a fake serial object)
  and without a Tk window.
- If you find yourself parsing protocol lines in the GUI or drawing from the protocol
  parser, the logic is in the wrong module.

## Feature Tracking
- All features are tracked in `features/INDEX.md` — read it before starting any work
- Feature specs live in `features/PROJ-X-feature-name.md`
- Feature IDs are sequential: check INDEX.md for the next available number
- One feature per spec file (Single Responsibility)
- Never combine multiple independent functionalities in one spec

## Git Conventions
- Commit format: `type(PROJ-X): description`
- Types: feat, fix, refactor, test, docs, build, chore
- Check existing features before creating new ones: `ls features/ | grep PROJ-`
- Check existing firmware modules before building: `git ls-files firmware/`
- Check existing PC modules before building: `git ls-files pc/`
- Remote: `origin` = https://github.com/chriscodego/Umgebungssensoren.git
- Never push, tag, or rewrite history without explicit user approval

## Human-in-the-Loop
- Always ask for user approval before finalizing deliverables
- Present options using clear choices rather than open-ended questions
- Never proceed to the next workflow phase without user confirmation
- Show the plan before changing anything (`.claude/rules/plan-approval-artifact.md`)
- **Uploading firmware to the device on COM9 always needs explicit approval** while there is
  only one board (it is dev board and production device at once). Once a separate dev board
  exists, only the production flash (`/release`) needs it

## Status Updates (MANDATORY - Write-Then-Verify)
After completing work on any feature, you MUST update tracking files. Follow this exact sequence:

1. **Read** the feature spec (`features/PROJ-X-*.md`) and `features/INDEX.md` BEFORE editing
2. **Write** your changes using the Edit tool — do NOT just describe what you would write
3. **Re-read** the file AFTER editing to verify the changes are actually present
4. **If changes are missing**, repeat step 2 — never claim updates were made without verifying

**What to update in the feature spec:**
- Status field in the header (Planned → In Progress → In Review → Released)
- Implementation notes: what was built, what changed, any deviations from the original spec
- Bug fixes or design changes discovered during implementation

**What to update in `features/INDEX.md`:**
- Feature status column must match the feature spec header
- Valid statuses: Roadmap → Planned → Architected → In Progress → In Review → Approved → Released
  - **Roadmap**: after `/init` — feature identified, no spec file yet
  - **Planned**: after `/write-spec`
  - **Architected**: after `/architecture`
  - **In Progress**: after `/firmware` or `/pc` starts
  - **In Review**: after `/qa` starts
  - **Approved**: after `/qa` passes (no critical/high bugs)
  - **Released**: after `/release` (flashed on the device, PC tool installed, tagged)

**NEVER do this:**
- Do NOT say "I've updated the feature spec" without actually calling the Edit tool
- Do NOT summarize changes in chat as a substitute for writing them to the file
- Do NOT skip updates because "it's obvious" or "minor"

## Quality Gates (run before claiming any implementation is done)
```bash
arduino-cli compile --fqbn arduino:avr:uno --warnings all firmware/Umgebungssensoren
python -m pytest pc/tests
ruff check pc
```
- Firmware: compiles, **no new warnings**, global RAM ≤ 1536 B (75 %) — see `firmware.md`
- PC: all host tests pass, ruff clean
- Anything that changed firmware behaviour: flashed (with approval) and smoke-tested
  over COM9 (`/flash`)
A feature is not "done" while any of these fails.

## File Handling
- ALWAYS read a file before modifying it — never assume contents from memory
- After context compaction, re-read files before continuing work
- When unsure about current project state, read `features/INDEX.md` first
- Run `git diff` to verify what has already been changed in this session
- Never guess at function names, pin numbers, sensor registers, protocol keywords or error
  codes — verify by reading `config.h`, `docs/SPEC.md` and the sensor datasheet notes in
  `docs/hardware.md`

## Language
- Code, identifiers, comments, and commit messages: **English**
- Specs, acceptance criteria, PC-tool UI strings, CLI help texts: **German** with real
  UTF-8 umlauts (ä/ö/ü/ß), never ae/oe/ue
- **TFT display texts: real umlauts too** (GFX classic font in CP437 mode) —
  write „Zurück“, „Größe“ (CP437 bytes); the degree sign is 0xF8
- Protocol keywords (`OK`, `ERR`, `EVT`, `READ` …) stay exactly as in SPEC.md
- Talk to the user in German

## Handoffs Between Skills
- After completing a skill, suggest the next skill to the user
- Format: "Nächster Schritt: `/skillname` ausführen, um [Aktion]"
- Handoffs are always user-initiated, never automatic
