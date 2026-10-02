# Umgebungssensoren — Agent Instructions

> For coding agents other than Claude Code (e.g. Codex). Claude Code reads `CLAUDE.md`.
> Both describe the same project; `CLAUDE.md` and `.claude/` are the source of truth.

## Project
Arduino Uno R3 firmware (C++, arduino-cli, BME680 on I2C, ST7735 touchscreen, EEPROM) in
`firmware/Umgebungssensoren/` plus a Python PC tool (pyserial CLI + Tkinter GUI) in
`pc/src/umwelt_ctl/`, bound by the serial protocol in `docs/SPEC.md`.

## Must-read before changing code
- `CLAUDE.md` — overview, commands, conventions
- `docs/SPEC.md` — the contract (hardware, data model, protocol)
- `.claude/rules/general.md`, `firmware.md`, `protocol.md`, `pc.md`, `security.md`
- `docs/ENTWICKLERHANDBUCH.md` — conventions and known pitfalls
- `features/INDEX.md` and the spec of the feature you work on

## Workflow
Specs in `features/PROJ-X-*.md` → architecture → firmware / PC tool → QA → release.
Skill descriptions live in `.claude/skills/*/SKILL.md` and can be followed manually.

## Commands
```bash
arduino-cli compile --fqbn arduino:avr:uno --warnings all firmware/Umgebungssensoren
python -m pytest pc/tests
ruff check pc
```

## Hard rules
- Protocol changes: SPEC.md, firmware, PC tool and tests together, with user approval
- Firmware: no `String`/heap/`delay()` in the loop; pins and limits only in `config.h`
- Only one process may use the serial port (COM9); never upload to the device without approval
  (a pre-existing firmware is on it)
- Commits: `type(PROJ-X): description`; never push or force-push without approval
