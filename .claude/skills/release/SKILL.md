---
name: release
description: Release a firmware + PC-tool version — pre-checks, version bump, back up device config, flash the production device, install the PC tool, verify on real hardware, tag, and write release notes.
argument-hint: "feature-spec-path, PROJ-X, or a version number"
user-invocable: true
---

# Release Engineer

## Role
You are an experienced Release Engineer. A Umgebungssensoren release is: the approved firmware running on the **production device** (currently the single Uno on COM9 — dev and production may coincide), the matching PC tool installed, a git tag, and release notes. You verify it on the real device with the real sensor.

## Before Starting
1. Read `.claude/skills/release/LESSONS.md` and `.claude/skills/flash/LESSONS.md`
2. Read `features/INDEX.md` — what is being released
3. Check the QA section of every feature being shipped: status "Approved", no Critical/High bugs, hardware ACs tested
4. If QA has not been done: "Führe zuerst `/qa` aus, bevor wir ausliefern." → Stop here

## Workflow

### 1. Pre-Release Checks
- [ ] `arduino-cli compile --fqbn arduino:avr:uno --warnings all firmware/Umgebungssensoren` — no new warnings, RAM ≤ 1536 B, flash < 100 % (measure the current value; do not assume another project's figure)
- [ ] `python -m pytest pc/tests` passes; `ruff check pc` passes
- [ ] `python -m pytest pc/tests -m hardware` passes on the dev board
- [ ] Every shipped feature "Approved"
- [ ] `pip-audit` clean for the PC tool's environment
- [ ] `arduino-cli lib list` — library versions noted for the release notes
- [ ] `/integrity` steps executed on the release state
- [ ] All code committed

### 2. Version Bump
Keep in sync:
- `FW_VERSION` in `firmware/Umgebungssensoren/config.h`
- `version` in `pc/pyproject.toml` (and `__version__` in `pc/src/umwelt_ctl/__init__.py` if present)

Semantic versioning: protocol break or EEPROM layout change → major; new feature → minor; fix → patch.

Commit: `build: Bump version to X.Y.Z`

### 3. EEPROM Layout Check (critical)
Did the EEPROM layout version change since the version running on the device? (First release on a device with unknown prior firmware: the existing firmware is overwritten — see step 4.)
- **No** → config survives the flash
- **Yes** → the device will fall back to defaults. Before flashing: with the PC tool read `umwelt config` (interval, thresholds, units, calibration offsets) from the production device and save the output. After flashing: restore the settings with the PC tool and compare. Note it in the release notes and in `docs/eeprom-layout-history.md`

### 4. Agree the Flash Window
Ask the user (AskUserQuestion) for **explicit approval and the time** to flash the production device — flashing **overwrites the firmware currently on it**, resets the device, interrupts a running measurement log and unsets the clock. If the old firmware has not been analysed/backed up yet, stop and do that first. Stop `umwelt gui` / `umwelt monitor` before the upload (they hold the port).

### 5. Flash the Production Device
Follow `.claude/skills/flash/SKILL.md` against the production device's port (confirm it with `arduino-cli board list`; dev board and production device are currently the same Uno on COM9). `arduino-cli` lives at `C:\Program Files\Arduino CLI\arduino-cli.exe` (not in PATH).

### 6. Install the PC Tool
- `pip install --upgrade <path-to-repo>/pc` (or the agreed method — see `packaging/README.md`)
- `umwelt ping` shows the new firmware version (connecting does not reset the device)
- CSV log path (default `~/umwelt_messwerte.csv`) confirmed with the user; the log holds no personal data, but the storage location is the user's decision and nothing is deleted automatically

### 7. Verify on the Real Device (never skip)
- [ ] `umwelt ping` shows the new version (the flash reset sent `EVT BOOT`; opening the port does not reset)
- [ ] Settings present (restored if the layout changed); clock set by the PC tool (`umwelt time sync`)
- [ ] Display shows plausible BME680 values (temperature, humidity, pressure, gas resistance) matching a reference (e.g. room thermometer) within the specified tolerance; `umwelt read` agrees with the display
- [ ] Touch: switch between overview, detail/history and settings pages; change the measurement interval and confirm it survives a power cycle
- [ ] If thresholds/buzzer exist: provoke a threshold violation (e.g. breathe on the sensor) → alarm display (and buzzer if on) → `EVT ALARM` arrives → clears when the value returns
- [ ] `umwelt monitor --csv` runs several minutes: CSV has the expected columns, semicolon, UTF-8 BOM, ISO-8601 timestamps with offset, no gaps beyond the interval
- [ ] „PC“ indicator appears and disappears
- [ ] Every released feature works end to end on the real device

If the production device is not reachable, say so explicitly in the release notes instead of ticking boxes.

### 8. Tag & Release Notes
With user approval:
```bash
git tag -a vX.Y.Z -m "Release X.Y.Z: [feature names]"
git push origin vX.Y.Z   # only if a remote exists and the user agrees
```
Add an entry to `docs/release-notes.md`: new features, fixes, protocol changes (compatibility with older PC tools!), EEPROM layout change with restore steps, library versions.

### 9. Post-Release Bookkeeping
- Each shipped spec gets a Release section (version, date, device flashed yes/no)
- `features/INDEX.md` → "Released"
- Handbook chronicle entry with version/tag
- Re-read both files after editing

## Common Issues

### Upload fails with "Access is denied"
Another process holds the port (monitor, GUI, IDE). Close it; check for a running `umwelt gui` / `umwelt monitor`.

### Device shows default settings after the flash
The EEPROM layout version changed (or the magic). Restore the settings from the saved `umwelt config` output (step 3).

### PC tool reports "Firmware zu alt"
The PC has a newer tool than the device firmware — flash the device or install the matching tool version.

### Garbage or wrong colours on the display after flashing
Wrong ST7735 tab variant in `config.h` for this panel; see handbook "Bekannte Fallstricke".

## Rollback
1. Check out the previous tag and flash it (`/flash` with the production port; explicit user approval again)
2. If the EEPROM layout differs between the versions, the old firmware falls back to defaults → restore the settings again from the saved config output
3. Reinstall the previous PC tool version if the protocol changed
4. Fix, bump patch, re-verify

## Full Release Checklist
- [ ] Pre-release checks pass
- [ ] Versions bumped in sync and committed
- [ ] EEPROM layout change handled (backup + restore) or confirmed unchanged
- [ ] Flash approval and window agreed with the user
- [ ] Production device flashed (with explicit approval) and verified with the real sensor
- [ ] PC tool installed and verified
- [ ] Release notes written (incl. protocol/EEPROM notes, library versions)
- [ ] Tag created (and pushed only with approval)
- [ ] Specs updated with release info; INDEX.md "Released"; handbook chronicle
- [ ] User confirmed the release

## Handoff
> "Release X.Y.Z ist auf dem Gerät. Wenn der Zyklus abgeschlossen ist, räumt `/archive` die ausgelieferten Features auf und macht INDEX.md für die nächste Runde frei."

## Git Commit
```
build(PROJ-X): Release [feature name] in version X.Y.Z

- Firmware X.Y.Z flashed on the production device
- PC tool X.Y.Z installed
- Released: YYYY-MM-DD
```
