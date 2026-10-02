---
name: integrity
description: Struktur-, Protokoll-Konsistenz- und Regressions-Check — läuft AUTOMATISCH nach jedem Feature/Fix und vor Status „In Review" oder einem Release (ohne Aufforderung). Prüft Compile/Ressourcen, Tests, Struktur gegen Handbuch und Rules, SPEC.md ↔ Firmware ↔ PC-Tool, Auswirkungen auf bestehende Features und die Handbuch-Pflege.
argument-hint: "optional: feature-spec-path oder Commit-Range"
user-invocable: true
model: opus
---

# Integrity-Check (Struktur, Protokoll, Regression)

## Rolle
Du bist der Wächter über Struktur und Stabilität. Du baust nichts Neues — du prüfst, ob die letzte Änderung sauber in die Architektur passt, ob Firmware, PC-Tool und `docs/SPEC.md` noch denselben Vertrag sprechen und ob bestehende Features gefährdet sind. Grundlage: `.claude/rules/code-integrity.md`, `.claude/rules/protocol.md`, `.claude/rules/developer-handbook.md`, `docs/ENTWICKLERHANDBUCH.md`.

## Vor dem Start
1. `LESSONS.md` in diesem Ordner lesen und anwenden
2. `docs/ENTWICKLERHANDBUCH.md`: Konventionen, Projektstruktur, Bekannte Fallstricke
3. Umfang bestimmen:
   - Argument = Spec-Pfad → Commits per `git log --oneline --grep="PROJ-X"`
   - Argument = Commit-Range → diese
   - Kein Argument → uncommittete Änderungen (`git status`, `git diff`) plus Commits seit dem letzten Tag (`git describe --tags --abbrev=0`, falls es Tags gibt)
4. Dateiliste: `git diff --name-status <basis>..HEAD` (+ Working Tree)

## Wann dieser Check läuft (automatisch — nie auf den Nutzer warten)
Nach jedem fertigen Feature/Fix, vor Status „In Review", vor jedem Release. `/firmware`, `/pc`, `/qa`, `/release`, `/autonom` und die Agents lesen diese Datei und arbeiten sie direkt ab.

## Schritt 1 — Automatische Gates
```bash
arduino-cli compile --fqbn arduino:avr:uno --warnings all firmware/Umgebungssensoren
python -m pytest pc/tests
ruff check pc
```
(`arduino-cli` liegt unter `C:\Program Files\Arduino CLI\arduino-cli.exe`, nicht im PATH.)
- Compile rot oder neue Warnung → HIGH
- Globaler RAM > 1536 B → HIGH; deutlicher Anstieg ohne Begründung im Spec → MEDIUM
- Flash ≥ 100 % → HIGH; deutlicher Anstieg ohne Begründung im Spec → MEDIUM (Stand jeweils neu messen)
- pytest rot → HIGH (nie Tests abschwächen)
Bei OneDrive-Sperrfehlern (Build-Ordner) einmal wiederholen.

## Schritt 2 — Struktur-Check des Diffs
Für jede geänderte/neue Datei:
- [ ] Richtiger Ort (`config.h` / Firmware-Modul `sensor`/`display`/`ui`/`input`/`storage`/`protocol` / `.ino` dünn / `pc/src/umwelt_ctl/<modul>.py` / `pc/tests/`)?
- [ ] Keine Pins, Grenzen, Timings, I2C-Adressen außerhalb von `config.h`?
- [ ] Keine Duplikate (zweiter Parser, zweite Fehlercode-Tabelle, zweite Hit-Test-Tabelle, zweite Einheiten-Umrechnung)?
- [ ] Firmware: kein `String`, kein Heap, kein `delay()` in der Loop (auch nicht im Sensor-Treiber), `F()`/`PROGMEM` für Konstanten, überlaufsichere `millis()`-Vergleiche, begrenzte Puffer-Kopien, Bereichsprüfung vor Array-Zugriff, keine Float-Formatierung (`%f`)?
- [ ] Sensor: Fehlerzustand (Sensor fehlt/I2C-Fehler) definiert, kein veralteter Messwert als gültig angezeigt?
- [ ] Anzeige- und PC-Texte mit echten Umlauten (Display: CP437, ° = 0xF8); PC-Texte Deutsch mit echten Umlauten?
- [ ] PC: Protokoll-Parsing nur in `protocol.py`, CSV nur in `messlog.py`, keine Widget-Zugriffe aus Threads, Timeouts gesetzt, Port sauber geschlossen?
- [ ] Keine Messprotokolle/CSV-Dateien im Diff (Ablageort bleibt Nutzerentscheid, kein automatisches Löschen)?
- [ ] Neue Logik hat Tests; keine Tests gelöscht oder abgeschwächt?

## Schritt 3 — Protokoll-Konsistenz (SPEC.md ↔ Firmware ↔ PC-Tool ↔ Tests)
1. Befehlstabelle, Fehlercodes und Events aus `docs/SPEC.md` auflisten (inkl. Einheiten der Ganzzahl-Messwerte)
2. Firmware: jeder Befehl wird erkannt, jede Antwortform entspricht SPEC, jeder Fehlercode wird verwendet, jedes Event wird gesendet (Grep in `firmware/`)
3. PC-Tool: jeder Befehl hat eine Client-Funktion/CLI-Entsprechung, jeder Fehlercode einen deutschen Text, jedes Event wird verarbeitet oder bewusst ignoriert, Einheiten-Umrechnung passt zur SPEC (Grep in `pc/src/`)
4. Tests: jeder Befehl mindestens einmal im Fake-Gerät (`pc/tests/`)
5. Etwas, das im Code, aber **nicht** in SPEC.md steht → HIGH (undokumentierter Vertrag)
6. Protokoll geändert, aber `FW_VERSION` nicht erhöht → MEDIUM

## Schritt 4 — Regressions-Analyse
1. Geteilte Bausteine im Diff: `config.h`, EEPROM-Struct/Storage, Zeilenparser, Sensor-Modul (Messintervall, Einheiten, Offsets), Display-Layout, Input/Touch-Modul, `protocol.py`, `device.py`, `messlog.py`
2. Aufrufer per Grep finden → Liste **betroffener Features** (aus `features/INDEX.md`)
3. Pro betroffenem Feature: passt der Aufrufer noch? Verhalten geändert (Timing, Grenzen, Einheiten, Defaults)? Decken Tests es ab? CSV-Spalten/-Einheiten geändert → bestehende Messprotokolle inkompatibel?
4. EEPROM-Struct geändert → Layout-Version erhöht? `docs/eeprom-layout-history.md`? Nutzerfreigabe dokumentiert? Sonst HIGH
5. Bei Firmware-Änderungen mit Hardware-Slot: `/flash` (nur mit Nutzerfreigabe, überschreibt die vorhandene Firmware) + `python -m pytest pc/tests -m hardware`; ohne Slot im Bericht vermerken

## Schritt 5 — Handbuch-Pflege
- [ ] Chronik-Eintrag in `docs/ENTWICKLERHANDBUCH.md` (Datum, PROJ-ID, Kurzbeschreibung)?
- [ ] Betroffene Kapitel aktualisiert (Module, Pins, EEPROM, Speicherbudget, CLI, Konventionen)?
- [ ] „Stand:"-Datum aktuell?
Fehlt etwas → nachtragen (Edit, danach re-lesen).

## Schritt 6 — Bericht & Fixes
```
Integrity-Check <Umfang>
Gates: compile ✓/✗ (RAM xxx B / Flash xx %) · pytest ✓/✗ (n/m) · ruff ✓/✗
Struktur: <n> Befunde
Protokoll: SPEC ↔ FW ↔ PC ↔ Tests konsistent / Befunde
Regression: betroffene Features: <Liste> → ok / Befunde
Hardware: getestet / nicht getestet (kein Slot)
Handbuch: aktuell / nachgetragen
Befunde (nach Schwere): CRITICAL/HIGH/MEDIUM/LOW …
```
- **CRITICAL/HIGH** → sofort fixen, committen (`fix(PROJ-X): …`), Check wiederholen
- **MEDIUM/LOW** → dem Nutzer nennen, auf Wunsch fixen
- Tests nie abschwächen/löschen, um grün zu werden

## Nach Fehlern
Wiederkehrende Strukturfehler oder übersehene Regressionen als Lesson in `LESSONS.md`; projektweite Fallstricke zusätzlich ins Handbuch.

## Handoff
Alles grün → „Nächster Schritt: `/qa` für die Akzeptanzkriterien" bzw. „`/release`".
