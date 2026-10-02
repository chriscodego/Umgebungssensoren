---
name: help
description: Context-aware guide that tells you where you are in the workflow and what to do next. Use anytime you're unsure.
argument-hint: "optional question"
user-invocable: true
---

# Project Help Guide

You are a helpful project assistant for **Umgebungssensoren** (Arduino Uno firmware with BME680 sensor and touchscreen + Python PC tool, bound by the serial protocol in `docs/SPEC.md`). Your job is to analyze the current project state and tell the user exactly where they are and what to do next.

## When Invoked

### Step 1: Analyze Current State

1. **PRD:** Read `docs/PRD.md` — empty template → not initialized; filled → set up
2. **Feature Index:** Read `features/INDEX.md` — features and statuses
3. **Feature Specs:** for each active feature check whether these sections exist:
   Tech Design (`/architecture`), Implementation Notes (`/firmware`, `/pc`), QA Test Results (`/qa`), Release (`/release`)
4. **Codebase:** quick scan
   - `git ls-files firmware/` → firmware modules
   - `git ls-files pc/` → PC tool modules and tests
   - `arduino-cli board list` → is a board connected (which port)?
5. **Open hardware questions:** Open Questions in the active specs (hardware, pinout) — still open?

### Step 2: Determine Next Action

**If PRD is empty template:**
> Dein Projekt ist noch nicht initialisiert. Führe `/init` mit einer Beschreibung aus.

**If PRD exists but no features:**
> Führe `/write-spec` aus, um die erste Feature-Spec zu schreiben.

**If features have status "Planned":**
> PROJ-X ist bereit für das technische Design. Führe `/architecture PROJ-X` aus.

**If features have status "Architected":**
> PROJ-X ist bereit zur Umsetzung. Bei Protokoll- oder Geräteänderungen zuerst `/firmware`, dann `/pc`; reine PC-Features direkt `/pc`.
> Alternativ: `/autonom` setzt alle geplanten Features autonom um und fragt nur bei wesentlichen Entscheidungen nach.

**If features are "In Progress" (implemented, no QA):**
> PROJ-X ist umgesetzt. `/flash` bringt den Stand aufs Dev-Board, danach `/qa PROJ-X`.

**If features passed QA ("Approved"):**
> PROJ-X ist bereit zur Auslieferung. Führe `/release` aus (Produktivgerät flashen — nur nach expliziter Freigabe, die vorhandene Firmware wird überschrieben —, PC-Tool installieren).

**If all features are released:**
> Alles ausgeliefert. Du kannst `/archive` ausführen, `/write-spec` für ein neues Feature, oder `docs/PRD.md` auf Roadmap-Punkte ohne Spec prüfen.

**If flash usage is close to the limit (measure with the last compile) and a feature adds firmware code:**
> Hinweis: Der Flash ist knapp (BME680-Bibliothek beachten). Plane in `/architecture`, wo das Feature Platz einspart.

### Step 3: Answer User Questions
Answer the specific question first, in the context of the project state. Common ones:
- "Welche Skills gibt es?" → table below
- "Wie flashe ich?" → `/flash` (Dev-Board) bzw. `/release` (Produktivgerät; aktuell nur ein Gerät an COM9 — vor jedem Upload explizite Freigabe)
- "Wie teste ich ohne Hardware?" → `python -m pytest pc/tests` (Fake-Gerät)
- "Wo ist das Protokoll?" → `docs/SPEC.md`, Abschnitt „Serielles Protokoll"
- "Wie passe ich den Workflow an?" → `CLAUDE.md`, `.claude/rules/`, `.claude/skills/`, `.claude/agents/`
- "Wo landet das Messprotokoll?" → Standard `~/umwelt_messwerte.csv`, siehe `docs/configuration.md`

## Reference

### Skills
| Skill | Zweck |
|-------|-------|
| `/init` | PRD und Feature-Map anlegen (einmal am Projektstart) |
| `/write-spec` | Vollständige Feature-Spec schreiben |
| `/architecture` | Technisches Design (Seiten/Touch, EEPROM, RAM-Budget, Sensor, Protokoll) — kein Code |
| `/firmware` | Arduino-Seite bauen, kompilieren, Ressourcen prüfen |
| `/pc` | PC-Tool bauen (Protokoll, CLI, monitor/CSV, GUI) |
| `/flash` | Kompilieren, auf COM9 laden, Smoke-Test (Dev-Board) |
| `/integrity` | Struktur-, Protokoll-Konsistenz- und Regressions-Check (läuft automatisch) |
| `/qa` | Host-Tests + Hardware-in-the-Loop gegen die Akzeptanzkriterien |
| `/release` | Version, Produktivgerät flashen (mit Freigabe), PC-Tool installieren, Tag |
| `/archive` | Ausgelieferte Specs archivieren, INDEX.md aufräumen |
| `/autonom` | Alle geplanten Features autonom umsetzen (fragt bei wesentlichen Entscheidungen) |
| `/refine` | Bestehende Spec überarbeiten oder grundsätzlich hinterfragen |
| `/help` | Diese Übersicht |

### Architecture
```
firmware/Umgebungssensoren/   .ino (dünn) · config.h · Module: sensor, display, ui, input, storage, protocol, signal/alarm
pc/src/umwelt_ctl/        protocol · device · cli (+ monitor) · messlog · gui
docs/SPEC.md                der Vertrag zwischen beiden
```

### Quality Gates
```bash
arduino-cli compile --fqbn arduino:avr:uno --warnings all firmware/Umgebungssensoren
python -m pytest pc/tests
ruff check pc
```

## Output Format

### Aktueller Stand
_Kurz, wo das Projekt steht_

### Features
_Tabelle aus INDEX.md mit Status_

### Empfohlener nächster Schritt
_Der eine wichtigste Schritt, mit exaktem Befehl_

### Weitere Möglichkeiten
_Was sonst gerade sinnvoll ist_

## Important
- Concise and actionable, exact commands, concrete file paths
- Don't explain the framework unless asked
- Communicate in German
