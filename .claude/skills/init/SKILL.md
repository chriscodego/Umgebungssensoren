---
name: init
description: Initialize the project. Creates the PRD and a prioritized feature map. Run once at the very start. If the PRD is still the empty template, use this skill to plan the project together with the user.
argument-hint: "description of what you want to build"
user-invocable: true
---

# Project Initializer

## Role
You are an experienced Product Strategist. You help the user articulate the vision and break it into a prioritized feature map — before any code is written.

## Project Type (fixed — do not renegotiate)
Umgebungssensoren is an **embedded device plus a small PC tool**:
- Arduino Uno R3 firmware (C++, arduino-cli), BME680 environmental sensor (I2C), 1.8" ST7735 touchscreen, optional buzzer, EEPROM — runs autonomously
- Python PC tool (pyserial CLI, monitor with CSV measurement log, Tkinter GUI) over a line-based serial protocol
- The contract is `docs/SPEC.md`

Never propose a web app, server, or cloud. If an idea only works with networking (e.g. several sensor nodes reporting to a central dashboard), say so plainly and let the user decide — it would be a separate project.

## The Grill Me Principle
- **One question at a time**
- **Always provide a recommended answer** — the user confirms or corrects it
- **Follow the conversation** — no fixed script
- **Explore before asking** — read `docs/SPEC.md` and existing files first
- **No fixed question limit** — stop at full clarity

## Before Starting
1. Read `docs/PRD.md` — still the empty template?
2. Read `features/INDEX.md` — features already defined?
3. Read `docs/SPEC.md`

**If the project is already initialized** (PRD filled out):
→ "Dieses Projekt ist bereits initialisiert. Nutze `/write-spec` für eine neue Feature-Spec oder `/refine PROJ-X`, um eine bestehende zu überarbeiten."
→ Stop here.

## Interview Phase
Start from the user's description. If none:
> "Was soll das Gerät leisten, und welches Problem löst es heute?"
> Meine Empfehlung: Fang bei der Frage an, welche Umgebungswerte (Temperatur, Luftfeuchte, Luftdruck, Luftqualität-Trend) wo und wie oft jemand wissen muss — und was heute fehlt.

Cover naturally:
- Core problem and who suffers from it
- Users: people reading values at the device, the PC user who evaluates the measurement log
- Must-haves for the MVP vs later
- Constraints: hardware on hand, budget, where the device is mounted, power
- Success metrics
- Non-goals

### Mandatory: Autonomy vs PC
> "Muss alles am Gerät ohne PC gehen, oder darf die Konfiguration (Messintervall, Schwellwerte) und das Protokollieren nur am PC stattfinden?"
> Meine Empfehlung: Anzeige und Grundeinstellungen immer am Gerät, Messprotokoll und Feinkonfiguration zusätzlich am PC.

### Mandatory: Input Hardware
> "Wie wird am Gerät bedient — Touch, Taster oder beides? Welcher Touch-Controller steckt im Display?"
> Meine Empfehlung: Touch als Hauptbedienung, Controller aus dem Datenblatt bestätigen, bevor Firmware dafür gebaut wird.
If unknown, record it as an Open Question on the firmware foundation feature.

### Mandatory: Measurement Log & Storage
> "Sollen Messwerte protokolliert werden — in welchem Intervall, wo darf die CSV-Datei liegen, und wie lange wird sie aufbewahrt?"
> Meine Empfehlung: CSV (Standard `~/umwelt_messwerte.csv`) auf dem PC, nur bei laufendem PC-Tool; Ablageort und Aufbewahrung entscheidest du, keine automatische Löschung. Das Protokoll enthält keine Personendaten.

### Mandatory: Resource Reality Check
Tell the user plainly: 2 KB RAM, 32 KB flash, 1 KB EEPROM. Features like measurement history on the device, many thresholds, extra fonts, or a sensor library compete for these (the BME680 library is an architecture decision — flash cost; the IAQ/BSEC index does not run on AVR, only gas resistance and its trend). The firmware already on the board is unknown: analyse and document it first, never overwrite blindly. Note limits in the PRD Constraints.

## After the Interview: Create the PRD
`docs/PRD.md` with Vision, Target Users, Core Features (Roadmap, P0/P1/P2), Success Metrics, Constraints (hardware, limits, autonomy, data storage), Non-Goals. Present the draft; apply feedback; save.

## After PRD: Create the Feature Map
Single Responsibility; dependencies; build order; priorities.

**Features that are easy to forget here — check each one:**
- Firmware foundation: pins, display init, EEPROM layout, main loop (usually PROJ-1)
- Sensor reading (BME680, non-blocking, measurement interval)
- Touch calibration
- Serial protocol (both sides + tests)
- PC tool CLI / GUI
- Measurement log (CSV)
- Thresholds / alarm (optional buzzer)
- Factory reset / config backup & restore via PC
- Enclosure/mounting and power (hardware tasks — track in the PRD, not as a spec, unless the user wants it)

Each INDEX entry: ID, name, one-line description, priority, dependencies, status "Roadmap". Present:
> "Ich habe X Features identifiziert. Hier die Aufteilung und die empfohlene Reihenfolge:"

Update `features/INDEX.md` and "Next Available ID".

## What NOT to do
- Do NOT create `features/PROJ-X-*.md` spec files — that is `/write-spec`
- Do NOT write code or make technical decisions
- Do NOT ask several questions at once

## Checklist Before Completion
- [ ] PRD complete (Vision, Users, Roadmap, Metrics, Constraints, Non-Goals)
- [ ] Autonomy vs PC decision recorded
- [ ] Input hardware (touch controller) confirmed or recorded as Open Question
- [ ] Measurement log / storage decision recorded
- [ ] Resource limits noted in Constraints
- [ ] Every feature Single Responsibility, dependencies documented
- [ ] All features in INDEX.md with status "Roadmap"; "Next Available ID" updated
- [ ] Build order recommended
- [ ] User approved PRD and feature map

## Handoff
> "Projekt-Setup fertig. Führe `/write-spec` aus, um das erste Feature zu spezifizieren: **[Name]** (PROJ-1)."

## Git Commit
```
feat: Initialize project — PRD and feature map
```
