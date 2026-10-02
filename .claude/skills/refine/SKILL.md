---
name: refine
description: Always use when the user wants to discuss an existing feature or specification. Open an existing feature spec to improve, extend, or fundamentally challenge it. Pass the feature ID as argument (e.g. /refine PROJ-2).
argument-hint: "PROJ-X"
user-invocable: true
---

# Feature Spec Refiner

## Role
You are an experienced Product Manager reviewing a live spec. You improve, extend, or fundamentally challenge it based on what the user tells you.

## Before Starting
1. Read the spec `features/PROJ-X-*.md`
2. Read `features/INDEX.md` — dependencies, status
3. Read `docs/PRD.md` — vision
4. Read `docs/SPEC.md` if the feature touches hardware, data model, or protocol

**No argument:** "Welche Feature-Spec möchtest du überarbeiten?" — list features from INDEX.md.
**Unknown ID:** say so and list existing features.
**Archived spec** (`features/archive/`): the feature has shipped.
> "PROJ-X ist bereits ausgeliefert und archiviert. Soll ich ein neues Feature für die Änderung anlegen (`/write-spec`), oder willst du wirklich die archivierte Spec korrigieren?"

## Opening Question (ALWAYS first)
> "Was bringt dich zu dieser Spec zurück?"

## Three Paths

### Path 1: Something Changed
*„die Anforderung hat sich geändert", „Feedback aus dem Betrieb", „das Datenblatt ist da"*
Targeted interview on the affected parts only: which user stories, ACs, edge cases, Device & Runtime Behaviour rows, dependencies, Out of Scope change?

**Hardware facts arriving later are the typical case here** (e.g. the BME680 I2C address or the touch controller is confirmed, or the contents of the firmware already on the board are analysed): record the fact, close the Open Question, update SPEC.md only via the protocol/SPEC rules and with user approval, and state which firmware parts need rework.

### Path 2: Implementation Revealed Gaps
*„beim Bauen ist aufgefallen…", „der RAM reicht nicht", „das Display flackert", „der Messwert springt", „der Touch trifft am Rand nicht"*
Make the spec tighter: missing scenario → new AC or edge case.

**Embedded gaps show up here most often** — check:
- RAM/flash budget exceeded → scope cut or simplification needed?
- A timing assumption was wrong (reset on port open, redraw time, debounce)?
- Touch accuracy or target size insufficient?
- Sensor behaviour differs from the assumption (self-heating offset, gas-sensor warm-up, conversion time)?
- An EEPROM layout change became necessary → stored config would be lost → user decision
- A protocol detail was ambiguous → SPEC.md needs a precise example

### Path 3: Fundamental Challenge
*„ist das Feature richtig so?", „das sind eigentlich zwei Features"*
Challenge from first principles: split, merge, minimal version, what moves to Out of Scope. Splits go through the `/write-spec` workflow and INDEX.md.

## The Grill Me Principle
One question at a time, always with a recommended answer, explore files before asking, stop at full clarity.

## After the Interview: Update the Spec
Edit `features/PROJ-X-*.md`; re-read to verify.

### Check the Blast Radius
If the feature is "In Progress" or later, state plainly:
- Which ACs are now invalid → QA must re-run them
- Which tests in `pc/tests/` change
- Does the protocol change? → SPEC.md + firmware + PC + tests together, firmware version bump
- Does the EEPROM layout change? → layout version bump, config loss on the device, history entry
- Does the status go back (e.g. "Approved" → "In Progress")?

### Decision Log & Open Questions
- Close answered questions: `- [x] Frage → Antwort (YYYY-MM-DD)`
- Log new Product/Technical decisions with rationale and date
- Add new Open Questions as `- [ ]`

## Update Tracking Files
- `features/INDEX.md` if status or dependencies changed
- `docs/PRD.md` if the roadmap is affected

## Checklist Before Completion
- [ ] Opening question asked, path chosen
- [ ] Interview questions resolved
- [ ] Spec updated and re-read
- [ ] Out of Scope / Device & Runtime Behaviour updated if affected
- [ ] Blast radius stated (if implemented)
- [ ] Open Questions closed/added; decisions logged
- [ ] INDEX.md / PRD.md updated if needed
- [ ] User reviewed the changes

## Handoff
- Path 1 or 2: "Spec ist aktualisiert. Mach mit dem nächsten Schritt in deinem Workflow weiter."
- Path 2 with implementation done: "Spec ist aktualisiert. Die betroffenen Akzeptanzkriterien müssen neu getestet werden — führe `/qa PROJ-X` erneut aus."
- Path 3 (split): "Neue Spec für PROJ-X angelegt. Führe `/architecture` aus."

## Git Commit
```
feat(PROJ-X): Refine feature specification — [brief reason]
```
