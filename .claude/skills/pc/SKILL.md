---
name: pc
description: Build the Python PC tool for a feature — pyserial protocol layer, port detection, CLI, monitor with CSV measurement log, Tkinter GUI. Use after architecture is designed (and after /firmware if the protocol changed).
argument-hint: "feature-spec-path or PROJ-X"
user-invocable: true
---

# PC Tool Developer

## Role
You are an experienced Python developer. You read the feature spec plus the tech design and implement the PC side of Umgebungssensoren in `pc/` (package `umwelt_ctl`, src layout, console command `umwelt`). The tool is optional for the device — it must never be required for the device to measure and display.

## Before Starting
1. Read `.claude/skills/pc/LESSONS.md` and apply every lesson
2. Read `features/INDEX.md` for project context
3. Read the feature spec (incl. Tech Design and Device & Runtime Behaviour)
4. Read `.claude/rules/pc.md`, `.claude/rules/protocol.md`, `.claude/rules/security.md`
5. Read `docs/SPEC.md` (protocol section) and the relevant chapters of `docs/ENTWICKLERHANDBUCH.md`
6. Check existing modules and tests: `git ls-files pc/`
7. Run the suite once for a baseline: `python -m pytest pc/tests`

**If the feature status is below "Architected":**
> "Dieses Feature hat noch kein technisches Design. Führe zuerst `/architecture PROJ-X` aus."
→ Stop here.

**If the feature changes the protocol and the firmware side is not done yet:** say so and suggest `/firmware` first — the device defines behaviour on the wire. Never implement a command the SPEC does not contain.

## Workflow

### 1. Read Spec + Design
- Which commands/events the feature uses, which CLI commands and GUI views change
- Whether the measurement log (CSV) is affected (columns, units, location)

### 2. Ask Technical Questions
Use `AskUserQuestion` for decisions the spec does not settle:
- Output format of a CLI command (human-readable only, or also machine-readable)?
- Where should a new file be written by default (the CSV log defaults to `~/umwelt_messwerte.csv`; the location stays the user's decision)?
- GUI placement: new tab, dialog, or part of the main view (e.g. live values vs. history chart)?

### 3. Implement
- Protocol parsing only in `protocol.py`; serial/port handling only in `device.py`; CSV writing only in `messlog.py`; CLI and GUI call those layers
- Measurement values arrive as integers (0.01 °C, 0.01 %rH, 0.1 hPa, Ω): convert to physical units in one place (`protocol.py`), never parse or scale in `cli.py`/`gui.py`
- `EVT` lines (e.g. `EVT DATA`, `EVT ALARM`) may arrive inside a multi-line response → route to callbacks, keep collecting
- Read timeouts everywhere; ports closed reliably; opening the port must **not** reset the Uno (DTR/RTS off, `reset_on_open=False`) → short wait for `EVT BOOT`, blank line, quick `PING`; only if that fails wait for `EVT BOOT` (see `protocol.md`)
- `ERR <code>` → German messages from one mapping table; no tracebacks for expected failures
- Tkinter: reader thread + `queue.Queue` + `root.after` polling; never touch widgets from the thread; confirm destructive actions
- CLI: German help texts, exit code ≠ 0 on error
- No new runtime dependency without user approval (a plot library for the GUI is such a decision — Tkinter canvas first)

### 4. Write Tests
In `pc/tests/` with the scripted fake device from `conftest.py`:
- Happy path per new/changed command (`PING`, `READ`, `STATUS`, `CFG`, `TIME`, …)
- Every `ERR` code path the feature can hit
- `EVT` interleaved in a response
- Timeout / device missing / port busy → clean German error
- Value conversion (integer wire value → °C / %rH / hPa / Ω), incl. negative temperatures and boundary values
- CSV log rows (if touched): header, semicolon separator, ISO timestamps with offset, UTF-8 with BOM, append without second header
Hardware variants of the same exchanges go into tests marked `@pytest.mark.hardware` (run only with the hardware slot).

### 5. Try It (hardware slot only)
`umwelt ping`, `umwelt status`, `umwelt read`, the new command(s), `monitor --csv`, `gui` against the device on COM9 (connecting does not reset the board). Check the values for plausibility and the CSV file for correct content. Close everything before handing the port to someone else.

### 6. User Review
- Tell the user which commands to run / what to click in the GUI, and where the CSV file lands
- Ask: "Passt das PC-Tool so? Was soll anders sein?"

## Verification (must pass before claiming done)
```bash
python -m pytest pc/tests
ruff check pc
```
Plus: hardware run if you had the slot, `/integrity` steps, handbook chronicle.

## Context Recovery
If your context was compacted mid-task:
1. Re-read the feature spec and `features/INDEX.md`
2. `git diff` / `git status` to see what you already changed
3. Re-read `docs/SPEC.md` protocol section — never guess keywords or error codes
4. Run `python -m pytest pc/tests`
5. Continue — don't restart or duplicate modules

## Checklist
See [checklist.md](checklist.md) for the full implementation checklist.

After completion, update tracking files:
- [ ] Feature spec: Implementation Notes (modules, commands, deviations)
- [ ] `features/INDEX.md` status "In Progress"
- [ ] Handbook chronicle + affected chapters (CLI commands, configuration)
- [ ] New lessons in `LESSONS.md` if something failed or surprised you

## Handoff
> "PC-Tool steht. Nächster Schritt: `/qa` ausführen, um das Feature gegen die Akzeptanzkriterien zu testen."

## Git Commit
```
feat(PROJ-X): Implement PC tool for [feature name]
```
