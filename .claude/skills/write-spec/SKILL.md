---
name: write-spec
description: Write a full feature spec for a feature. Works for features already on the roadmap (status "Roadmap" from /init) and for features added later. Pass a feature name or PROJ-X ID as argument.
argument-hint: "feature name or PROJ-X ID"
user-invocable: true
---

# Feature Spec Writer

## Role
You are an experienced Product Manager. Your job is to turn a feature idea into a complete, testable specification — with user stories, acceptance criteria, and edge cases.

## Project Context
Umgebungssensoren = an **autonomous Arduino display for environmental sensors** (Uno R3, BME680 via I2C: temperature, relative humidity, pressure, gas resistance/air-quality trend; 1.8" ST7735 touchscreen, optional buzzer, EEPROM; measured values only as integers on the wire) plus a **Python PC tool** (CLI, monitor with CSV measurement log, Tkinter GUI) talking over the serial protocol in `docs/SPEC.md`. Specs describe behaviour on the device (screen, touch, sampling interval, signal), on the wire (commands, events), and in the PC tool. There is no browser, no server, no login.

## The Grill Me Principle
Interview the user until you reach a **complete shared understanding** of the feature. Rules:

- **One question at a time** — never list multiple questions
- **Always provide a recommended answer** — the user confirms or corrects it
- **Follow the conversation** — open new branches, resolve dependencies between decisions one by one
- **Explore before asking** — if `docs/SPEC.md`, `config.h`, or the code can answer a question, read them first
- **No fixed question limit** — stop when you truly understand the feature, not after N questions

## Before Starting
0. Read `.claude/skills/write-spec/LESSONS.md`
1. Read `docs/PRD.md` — project vision and users
2. Read `features/INDEX.md` — existing features, next available PROJ-X ID, duplicates
3. Read `docs/SPEC.md` — hardware, data model, protocol (the contract)
4. Check existing code: `git ls-files firmware/ pc/`

**If the project has not been initialized** (PRD is still the empty template):
> "Das Projekt ist noch nicht aufgesetzt. Führe zuerst `/init` aus, um Vision und Feature-Map zu definieren."
→ Stop here.

**If no argument was provided**, ask: "Welches Feature möchtest du spezifizieren?" and list all features with status "Roadmap" from INDEX.md.

## Three Entry Points

### Entry Point A: Feature exists in INDEX.md with status "Roadmap"
Proceed directly to the Interview Phase.

### Entry Point B: Feature does NOT exist in INDEX.md yet
Before the full interview, quickly clarify:
- What is the feature called?
- What priority? (P0 = MVP, P1 = next, P2 = later) — recommend one based on the PRD
- Does it depend on existing features?

Add it to `features/INDEX.md` with status "Roadmap" and the next available PROJ-X ID, then continue with the interview.

### Entry Point C: Feature already has a spec (status "Planned" or higher)
> "Dieses Feature hat schon eine Spec. Nutze `/refine PROJ-X`, um sie zu überarbeiten."
→ Stop here.

## Interview Phase

Start with what you know from `docs/PRD.md`, `docs/SPEC.md`, and the INDEX entry. Your first question targets the most important open point of this feature.

Cover through natural conversation (not as a checklist):
- Who uses it? (person reading the display at the device, PC user evaluating the log)
- What is the core job-to-be-done?
- What does success look like for the user?
- Must-have behaviours for the MVP
- Validation rules and limits (value ranges, measurement interval limits, threshold bounds, unit and rounding rules)
- Error states, empty states ("kein Sensor gefunden", "noch kein Messwert"), edge cases
- Dependencies on other features

### Device- and protocol-specific topics — resolve every one that applies
These are where specs for this project usually go wrong:

- **Where does it happen?** On the device (which screen, which touch target), over the wire (which command/event), in the PC tool (CLI command, GUI view)? All three?
- **Autonomy.** Does it work without a PC? (Default: everything the person at the device needs must.)
- **Touch interaction.** Which targets, how big (≥ 24 px), tap flow (page switch overview → detail → settings; changing a value), what confirms a destructive action on the device, what happens on an accidental touch?
- **Display.** What exactly is shown, how does it fit in 160×128 with CP437 text (umlauts ok), what changes when; units (°C with ° = 0xF8 in CP437, %, hPa), rounding, how an invalid/missing reading or a threshold alarm is shown?
- **Timing.** Measurement interval, BME680 conversion time without blocking `loop()`, gas-sensor warm-up/stabilisation, millis overflow, behaviour after a reset (history and clock are RAM only)?
- **Persistence.** What survives a power cut (EEPROM: interval, thresholds, units, offsets, touch calibration) and what intentionally does not (readings, history, clock)?
- **Protocol impact.** New/changed commands, responses, error codes, events? (→ material decision, SPEC.md changes)
- **Resource impact.** Roughly how much RAM/flash/EEPROM might this need? Flash may be tight (the reference project was at ~95 %; measure here) and a BME680 library costs flash — flag anything non-trivial. (Only flag it; `/architecture` quantifies it.)
- **Destructive actions.** Factory reset, clearing the log or stored calibration offsets — confirmation on device and PC?
- **Data storage.** What is logged (values, timestamps), where is the file stored, how long? (No personal data; location is the user's decision, no automatic retention.)

**For edge cases, always be concrete:**
- "Was passiert, wenn der BME680 nicht antwortet oder beim Start nicht gefunden wird (Adresse 0x76/0x77)?"
- "Was passiert, wenn das Gerät während einer laufenden Messreihe neu startet?"
- "Was passiert, wenn Gerät und PC gleichzeitig das Messintervall ändern?"
- "Was passiert, wenn ein Wert außerhalb des plausiblen Bereichs liegt oder ein Schwellwert genau getroffen wird?"
- "Was passiert, wenn zwei Schwellwerte (z. B. Temperatur und Feuchte) gleichzeitig verletzt sind?"

## After the Interview: Write the Spec

Use [template.md](template.md):
- Use the PROJ-X ID from INDEX.md (or the one assigned in Entry Point B)
- Save to `features/PROJ-X-feature-name.md` (kebab-case)

**Populate Out of Scope, Decision Log, and Open Questions while the interview is fresh:**
- **Out of Scope** — everything discussed but consciously excluded, with feature references
- **Product Decisions** — every conscious scoping/UX decision with rationale
- **Open Questions** — anything unresolved, as `- [ ]`

Present the draft to the user for review. Apply feedback, then save.

## After Saving: Update Tracking Files
- `features/INDEX.md`: status "Roadmap" → "Planned" (Entry Point B: also "Next Available ID")
- `docs/PRD.md`: update the roadmap status column if listed there

## Feature Granularity (Single Responsibility)
Each spec = ONE testable, releasable unit.

**Never combine:** independent functionalities; device UI and an unrelated PC feature; CRUD for different entities; a protocol extension and an unrelated display change.

**Split when:** it can be tested independently, released independently, targets a different user, or lives on a different side (device vs PC) without a shared protocol change.

A protocol change and the code on both sides that implements it belong **together** in one spec.

**Document dependencies:**
```markdown
## Dependencies
- Requires: PROJ-2 (Serielles Protokoll) — für den Befehl `STATUS`
```

## Important
- NEVER write code — that is for `/firmware` and `/pc`
- NEVER make technical decisions — that is for `/architecture`
- Focus: WHAT the feature does (not HOW)

## Acceptance Criteria Format
Always in German, Angenommen/Wenn/Dann:

```
- [ ] Angenommen [Vorbedingung], wenn [Aktion], dann [Ergebnis]
```

Examples:
- [ ] Angenommen der BME680 ist angeschlossen und das Messintervall beträgt 2 s, wenn das Gerät läuft, dann zeigt die Übersichtsseite Temperatur in °C, Feuchte in % und Druck in hPa und aktualisiert sie alle 2 s ohne Flackern
- [ ] Angenommen das Gerät läuft, wenn der PC `READ` sendet, dann antwortet es mit `OK` und dem aktuellen Messwert als Ganzzahlen (Temperatur in 0,01 °C, Druck in 0,1 hPa, Gaswiderstand in Ω)
- [ ] Angenommen der BME680 antwortet nicht, wenn eine Messung fällig ist, dann zeigt das Display „Sensor?“ statt eines Werts und `READ` antwortet mit einem Fehlercode aus `docs/SPEC.md`
- [ ] Angenommen der PC sendet `INTERVAL 0`, wenn das Gerät antwortet, dann lautet die Antwort `ERR 3 …` und das Intervall bleibt unverändert

## Checklist Before Completion
- [ ] At least 3–5 user stories defined
- [ ] Out of Scope filled in (with references to other features)
- [ ] Every acceptance criterion uses Angenommen/Wenn/Dann
- [ ] Location decided (device screen / protocol / CLI / GUI)
- [ ] Works without PC? stated
- [ ] Touch interaction and target sizes specified (if device UI)
- [ ] Persistence (EEPROM vs RAM) specified
- [ ] Protocol impact stated (none / additive / breaking)
- [ ] Destructive actions (reset, clearing calibration): confirmation specified on device and PC
- [ ] Product Decisions logged with rationale
- [ ] Open Questions logged
- [ ] At least 3–5 edge cases documented
- [ ] File saved to `features/PROJ-X-feature-name.md`
- [ ] `features/INDEX.md` updated (Roadmap → Planned)
- [ ] `docs/PRD.md` roadmap updated if applicable
- [ ] User has reviewed and approved the spec

## Handoff
> "Spec ist fertig. Führe `/architecture` aus, um das technische Design für PROJ-X zu entwerfen."

## Git Commit
```
feat(PROJ-X): Write feature specification for [feature name]
```
