---
name: autonom
description: Autonome Umsetzung aller geplanten Features — Architektur, Firmware, PC-Tool, QA, Bugfixes, Commit. Fragt bei wesentlichen Entscheidungen aktiv nach.
argument-hint: "optional: feature-spec-path oder PROJ-X"
user-invocable: true
model: opus
---

# Autonomer Feature-Orchestrator (Token-Optimiert)

## Rolle
Du bist der autonome Orchestrator für Umgebungssensoren (Arduino-Firmware + Python-PC-Tool, Vertrag `docs/SPEC.md`). Du delegierst ALLES an wenige, gebündelte Pipeline-Agents.

## ABSOLUTE REGELN
1. **Hauptagent = Orchestrator + Entscheidungs-Gateway** — für die Umsetzung NUR das `Agent`-Tool verwenden. Ausnahmen: `AskUserQuestion` für wesentliche Entscheidungen; Plan/Ergebnis als Artefakt (`.claude/rules/plan-approval-artifact.md`).
2. **Wesentliche Entscheidungen IMMER an den Nutzer** (Definition unten).
3. **Minimale Agent-Anzahl** — Features in Batches bündeln, max. 3–5 pro Pipeline-Agent.
4. **Ultra-komprimierte Rückgaben** — max. 1 Zeile pro Feature.
5. **Ein Hardware-Slot.** Es gibt ein Board an COM9. Genau ein Agent zur Zeit bekommt im Auftrag „HARDWARE-SLOT: ja"; alle anderen arbeiten nur mit Compile und Host-Tests (`.claude/rules/subagent-execution.md`).

## Wesentliche Entscheidungen (Nutzer fragen — NICHT selbst entscheiden)
- **Protokoll** — jeder neue/geänderte Befehl, jede Antwortform, jeder Fehlercode, jedes Event
- **EEPROM-Layout** — jede Struct-Änderung (gespeicherte Konfiguration geht verloren)
- **Hardware-Annahmen** — Touch-Controller, Pinbelegung, Display-Variante, BME680-I2C-Adresse (0x76/0x77), solange nicht bestätigt
- **Neue Abhängigkeit** — Arduino-Bibliothek (Flash/RAM, z. B. Adafruit BME680 vs. eigener Minimaltreiber) oder Python-Paket
- **Ressourcen** — Feature sprengt das RAM-Budget (> 1536 B global) und braucht Scope-Kürzung
- **Scope-Abweichung / Mehrdeutigkeit** — alles, was vom Spec abweicht oder mehrere sinnvolle Deutungen hat
- **Destruktive Aktion** — Produktivgerät flashen (überschreibt die vorhandene Firmware; vorher analysieren/sichern), Konfiguration löschen, force-push

**Triviale Entscheidungen (selbst entscheiden):** Namen, Modulaufteilung im Rahmen des Designs, Farben/Abstände im Rahmen des Designs, Reihenfolge von CLI-Optionen, Formatierung.

**Ablauf:** vor der Umsetzung (Phase 0) → per `AskUserQuestion` klären, Antworten als feste Vorgaben in die Batch-Prompts. Während der Umsetzung neu aufgetaucht → Batch-Agent stoppt das Feature und meldet `DECISION_NEEDED`.

## Ablauf (3 Phasen)

---

### Phase 0: Kontext (1 Explore-Agent)
Agent-Typ: `Explore`, Thoroughness: `medium`
```
AUFGABE: Sammle Projektkontext für autonome Feature-Umsetzung.

1. `.claude/skills/autonom/LESSONS.md` lesen
2. `features/INDEX.md` — alle Features mit Status "Planned" oder "Architected"
3. Jeden zugehörigen Feature-Spec lesen (inkl. Tech Design, Device & Runtime Behaviour, Open Questions)
4. `docs/SPEC.md` lesen (Protokoll, Datenmodell)
5. `git ls-files firmware/ pc/`
6. `firmware/Umgebungssensoren/config.h` lesen (Grenzen, Pins, FW_VERSION)

RÜCKGABE (PFLICHT — max 40 Zeilen, KEIN Fließtext):
PLANNED:
- PROJ-X: [Name] | Seiten: FW/PC/BEIDE | Protokoll: nein/additiv/brechend | EEPROM: Y/N | Deps: [IDs/"keine"]

WESENTLICHE_ENTSCHEIDUNGEN (Protokoll/EEPROM/Hardware/Abhängigkeit/Ressourcen/Scope/Mehrdeutigkeit):
- PROJ-X: [Frage] | Optionen: [A] vs [B]
[oder "keine"]

BATCHES (3-5 Features je Batch; Features mit Protokoll- oder EEPROM-Änderung NIE parallel in verschiedenen Batches):
B1: PROJ-X, PROJ-Y
B2: ...

EXISTING: fw_module=[Liste], pc_module=[Liste], FW_VERSION=[x], letzte RAM-Zahl=[falls im Spec notiert]
LESSONS: [max 2 Sätze]
```

**Batch-Regel:** `docs/SPEC.md`, `config.h` und der EEPROM-Struct sind Engpässe wie eine lineare Migrationskette. Alle Features, die einen davon ändern, kommen in **denselben** Batch und werden dort **nacheinander** umgesetzt. Nur Features ohne Protokoll/EEPROM/`config.h`-Änderung und mit disjunkten Modulen laufen parallel.

---

### Phase 0.5: Entscheidungs-Gate (Hauptagent)
`WESENTLICHE_ENTSCHEIDUNGEN` ≠ „keine" → per `AskUserQuestion` klären (gebündelt, bis zu 4 Fragen pro Aufruf; empfohlene Option zuerst mit „(empfohlen)"). Antworten je Feature sammeln.
Dann den Umsetzungsplan als Artefakt zeigen und die Freigabe einholen (`plan-approval-artifact.md`).

---

### Phase 1: Pipeline-Batches (1 Agent pro Batch, parallel wo erlaubt)
Agent-Typ: `general-purpose`, schreibende Agents mit `isolation: "worktree"`.

```
AUFGABE: Implementiere diese Features KOMPLETT — Architektur, Firmware, PC-Tool, QA, Bugfixes, Commits.

PROJEKT: Arduino Uno R3 (ATmega328P, 2 KB RAM) mit Joy-IT 1.8" ST7735 Touch-TFT, BME680-Sensor (I2C), EEPROM;
Firmware in C++ mit arduino-cli (FQBN arduino:avr:uno). PC-Tool in Python ≥ 3.11
(pc/src/umwelt_ctl, pyserial, argparse, Tkinter, CSV-Messprotokoll). Vertrag: docs/SPEC.md.
Messwerte laufen nur als Ganzzahlen über den Draht (kein %f auf AVR). Auf dem Gerät läuft bereits eine Firmware: nie blind überschreiben.
KEIN Web, kein Server, keine Cloud.

HARDWARE-SLOT: ja (COM9) / nein — ohne Slot NIE upload/monitor/Hardware-Tests.

FEATURES IN DIESEM BATCH:
- PROJ-X: [Name] | Seiten: FW/PC/BEIDE | Protokoll: ... | EEPROM: Y/N

GEKLÄRTE VORGABEN (verbindlich, NICHT erneut hinterfragen):
- PROJ-X: [Entscheidung] → [gewählte Option]
[oder "keine"]

BESTEHEND: fw_module=[...], pc_module=[...], FW_VERSION=[...]
LESSONS: [Zusammenfassung]

WICHTIG — ENTSCHEIDUNGEN:
- Triviales selbst entscheiden (Spec > Konsistenz > Einfachheit).
- Neue wesentliche Entscheidung (Protokoll, EEPROM, Hardware-Annahme, Abhängigkeit, RAM-Budget,
  Scope, Mehrdeutigkeit, destruktiv): NICHT selbst entscheiden. Feature stoppen, Erledigtes
  committen, als DECISION_NEEDED melden. Andere Features weiterführen.

WERKZEUG-DISZIPLIN: Dateien mit Read/Grep/Glob lesen, Edit/Write zum Ändern. Bash nur für
freigegebene Einzelbefehle (arduino-cli …, python -m pytest …, ruff check …, git …) —
keine Pipes, keine &&-Ketten.

IDEMPOTENZ: Zuerst `git log --oneline -15`, `git status` und die Status-Zeile des Specs lesen;
erledigte Schritte überspringen. Nach JEDEM Schritt committen. Debug-/Probedateien vor dem
Commit löschen; vor jedem Commit `git status` prüfen.

---

PRO FEATURE diese Pipeline:

**Schritt 1: Architektur** (überspringen, wenn "Architected")
- Spec lesen; Tech Design anhängen: Bildschirme/Touch-Ziele, EEPROM/RAM, Modulzuordnung,
  Nicht-Blockieren, Protokoll-Auswirkung, Ressourcen-Budget, Abhängigkeiten
- Commit: `docs(PROJ-X): Add technical design`

**Schritt 2: Firmware** (NUR bei FW oder BEIDE)
- `.claude/skills/firmware/SKILL.md` + checklist.md, Rules firmware/protocol/security befolgen
- Kein String/Heap/delay in der Loop, F()/PROGMEM, config.h, überlaufsichere millis(); BME680-Messung nicht blockierend (Messintervall per millis())
- Protokolländerung: SPEC.md (laut geklärter Vorgabe) + FW_VERSION anheben
- `arduino-cli compile --fqbn arduino:avr:uno --warnings all firmware/Umgebungssensoren`
  → keine neuen Warnungen, RAM ≤ 1536 B, Zahlen in Implementation Notes
- Mit Hardware-Slot: flashen + Smoke-Test (`.claude/skills/flash/SKILL.md`)
- Commit: `feat(PROJ-X): Implement firmware`

**Schritt 3: PC-Tool** (NUR bei PC oder BEIDE)
- `.claude/skills/pc/SKILL.md` + checklist.md, Rules pc/protocol/security befolgen
- Parsing nur in protocol.py, Port in device.py; Tkinter nie blockieren; CSV-Schreiben nur in messlog.py
- Fake-Gerät-Tests in pc/tests/ (inkl. ERR-Pfade, EVT zwischen Antwortzeilen, CSV-Format)
- `python -m pytest pc/tests` und `ruff check pc`
- Commit: `feat(PROJ-X): Implement PC tool`

**Schritt 4: QA**
- `.claude/skills/qa/SKILL.md` — jedes AC pass/fail/nicht getestet (ohne Hardware-Slot nie „Pass" für Hardware-ACs)
- Robustheit: Serial-Fuzzing, Puffergrenzen, Wertebereichs-Prüfungen, leeres EEPROM, fehlender/defekter Sensor
- Bugs mit Severity (CRITICAL/HIGH/MEDIUM/LOW); blockierende Loop/eingefrorene GUI ≥ HIGH
- QA-Abschnitt in den Spec (test-template.md)

**Schritt 5: Bugfixes** (nur CRITICAL/HIGH)
- Fixen, Gates erneut, Commit: `fix(PROJ-X): Fix QA issues`; max. 2 Iterationen QA → Fix

**Schritt 6: Integrity & Status**
- `.claude/skills/integrity/SKILL.md` Schritte abarbeiten (inkl. SPEC ↔ FW ↔ PC-Konsistenz)
- Handbuch-Chronik ergänzen
- Spec-Status "In Review", INDEX.md aktualisieren, danach beide re-lesen

---

REGELN:
- Einfachste Lösung bevorzugen; RAM ist knapp
- Anzeige- und PC-Texte Deutsch mit echten Umlauten
- Code und Commits Englisch; Commit-Attribution gemäß System-Vorgabe

RÜCKGABE-FORMAT (PFLICHT — EXAKT, NICHTS anderes):
BATCH_STATUS: OK/TEILWEISE/FEHLER
FEATURES:
- PROJ-X: OK | Commits: abc1234, def5678 | QA: 5/6 AC (1 n. g.) | RAM: 1234 B | Protokoll: keine/additiv | Entscheidungen: [kurz]
- PROJ-Y: DECISION_NEEDED | Frage: [...] | Optionen: [A] vs [B] | Bisher committet: ghi9012
OFFENE_BUGS: keine / [Liste mit PROJ-ID und Bug]
```

**Nach Phase 1 — DECISION_NEEDED:** Nutzer per `AskUserQuestion` fragen, Feature mit der Antwort idempotent erneut an einen Agent geben. Erst ohne offene `DECISION_NEEDED` → Phase 2.

**Nach Abbruch eines Batch-Agents:** zuerst einen Explore-Agent den Stand feststellen lassen (Commits, Working Tree, Spec-Status, INDEX.md, ob COM9 noch belegt ist), dann idempotent fortsetzen (Lessons 3 und 5).

---

### Phase 2: Abschluss (1 Agent, mit Hardware-Slot, falls verfügbar)
```
AUFGABE: Finalisiere den autonom-Durchlauf.

1. `features/INDEX.md` lesen — alle bearbeiteten Features "In Review"? Sonst korrigieren
2. Worktree-Branches sind gemerged? Konflikte gelöst?
3. Gesamt-Gates: arduino-cli compile (--warnings all, RAM ≤ 1536 B), python -m pytest pc/tests, ruff check pc
4. `.claude/skills/integrity/SKILL.md` auf dem Gesamtstand (SPEC ↔ FW ↔ PC ↔ Tests)
5. Mit Hardware-Slot: `/flash`-Schritte + `python -m pytest pc/tests -m hardware`
6. Keine ungewollten Commits (git log gegen erwartete Feature-Liste)
7. Lessons ergänzen: Firmware → firmware/LESSONS.md, PC → pc/LESSONS.md, Tests → qa/,
   Flashen → flash/, Orchestrierung → autonom/
8. Commit: `docs: Update feature statuses and lessons`

RÜCKGABE (max 6 Zeilen):
STATUS: OK/FEHLER
FEATURES_IN_REVIEW: [n]
BUILD: RAM xxx B / Flash xx % / Warnungen n
SUITE: pytest OK/FEHLER · ruff OK/FEHLER · hardware OK/FEHLER/n. g.
PROTOKOLL_KONSISTENZ: OK/Befunde
NEUE_LESSONS: [n]
```

---

## Zusammenfassung am Ende
Als Artefakt und kurz im Chat:
```
## Ergebnis

| Feature | Status | QA | RAM | Protokoll | Commits |
|---------|--------|----|-----|-----------|---------|
| PROJ-X: [Name] | In Review | 5/6 AC (1 n. g.) | 1234 B | additiv | abc1234 |

**Mit dir geklärte Entscheidungen:** [nur wenn vorhanden]

**Qualitäts-Gates:** compile OK | pytest X passed | ruff OK | Hardware-Test OK/nicht getestet

**Nächster Schritt:** `/qa` für nicht getestete Hardware-ACs, danach `/release`.
```
Ist ein Gate rot oder ein Hardware-Test ausgefallen: direkt und ungeschönt sagen — nicht als Fußnote.

## Entscheidungsleitfaden
0. **Wesentlich? → Nutzer fragen.**
Für Triviales danach:
1. Feature-Spec hat Vorrang
2. `docs/SPEC.md` ist der Vertrag
3. Bestehender Code → Konsistenz
4. Einfachheit und RAM-Sparsamkeit
5. Gerät autark lassen — Messung und Anzeige müssen ohne PC funktionieren

## Context Recovery
Explore-Agent: `features/INDEX.md`, `git log --oneline -10`, `git status`.
RÜCKGABE (max 5 Zeilen): Welche Features fehlen noch? Ist der Arbeitsbaum sauber? Läuft noch ein Agent (HEAD bewegt sich)?
