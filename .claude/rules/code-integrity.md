# Code-Struktur & Regressionsschutz (MANDATORY)

> Ziel: Jede Änderung hält die bestehende Struktur ein, hält Firmware, PC-Tool und
> `docs/SPEC.md` synchron und macht **keine bestehenden Features kaputt**. Gilt
> **während** der Entwicklung und wird **nach jedem Feature/Fix** mit `/integrity`
> nachgewiesen.

## Während der Entwicklung

### Struktur einhalten (siehe Handbuch, Kapitel „Projektstruktur" & „Konventionen")
- **Richtiger Ort für jeden Baustein:**
  - Pins, Grenzen, Timings, `FW_VERSION` → `firmware/Umgebungssensoren/config.h`
  - Firmware-Logik → eigenes Modul (`.h/.cpp`) je Verantwortung (storage, sensor,
    display, input/touch, protocol, signal); die `.ino` bleibt ein dünner Dispatcher
  - Protokoll-Parsing PC-seitig → `pc/src/umwelt_ctl/protocol.py` (Verbindung: `device.py`), nie in CLI oder GUI
  - Tests → `pc/tests/` (`test_*.py`), Hardware-Tests mit `@pytest.mark.hardware`
  - Protokolländerung → zuerst `docs/SPEC.md` (siehe `protocol.md`)
- **Keine Parallel-Strukturen:** Gibt es schon einen Parser, eine Zeichenroutine, eine
  Hit-Test-Tabelle, eine Fehlercode-Tabelle → erweitern, nicht duplizieren. Vorher suchen
  (`git ls-files firmware/ pc/`, Grep).
- **Geteilten Code nur mit Blick auf alle Aufrufer ändern:** `config.h`-Konstanten,
  EEPROM-Struct, Protokoll-Client, Fehlercode-Tabelle → alle Verwendungen per Grep finden
  und im selben Commit anpassen.
- **Signaturen stabil halten.** Muss sich eine Schnittstelle ändern: alle Aufrufer im
  selben Commit anpassen.

### Bestehende Features schützen
- **Vor Änderung an geteiltem Code:** Liste der betroffenen Features erstellen und diese
  danach gezielt mitprüfen (z. B. geänderter Zeilenparser → alle Befehle; geänderte
  Display-Aufteilung → Übersichtsseite, Detail-/Verlaufsseite, Alarmanzeige, Messintervall, Uhr, PC-Symbol).
- **EEPROM-Layout:** Jede Struct-Änderung = Layout-Version hoch + Eintrag in
  `docs/eeprom-layout-history.md` + Nutzerfreigabe.
- **Speicherbudget:** RAM-/Flash-Zahlen vor und nach der Änderung vergleichen; ein
  Sprung ohne Grund ist ein Befund.
- **Bestehende Tests nie abschwächen oder löschen**, um grün zu werden. Ein roter Test
  ist ein echter Bug (fixen) oder eine mit dem Nutzer abgestimmte Verhaltensänderung
  (Test + SPEC + Handbuch anpassen).
- **Neue reine Logik bekommt Tests** (PC: pytest; Firmware: über das Protokoll mit dem
  Hardware-Test bzw. – falls als reines C++ ohne Arduino-Abhängigkeit geschrieben – als
  Host-Test).

## Nach jedem Feature / Fix (MANDATORY)
Vor dem Status „In Review" bzw. vor jedem Release den Skill **`/integrity`** ausführen.
Er prüft mindestens:
1. Gates: `arduino-cli compile … --warnings all` (keine neuen Warnungen, RAM ≤ 75 %),
   `python -m pytest pc/tests`, `ruff check pc`
2. Struktur-Check des Diffs gegen die Regeln oben
3. **Protokoll-Konsistenz:** jeder Befehl/Fehlercode/Event in SPEC.md ist in Firmware,
   PC-Client und Tests vorhanden — und umgekehrt nichts, was nicht in SPEC.md steht
4. Regressions-Check der betroffenen Features
5. Handbuch-Pflege laut `developer-handbook.md`

Ergebnis ist ein kurzer Bericht (bestanden / Befunde). **Befunde CRITICAL/HIGH werden
vor dem Abschluss gefixt**; kleinere werden dem Nutzer genannt.

## Automatik
- Der Integrity-Check läuft **ohne Aufforderung**: Jede Session, jeder Skill und jeder
  Subagent, der Code ändert, führt ihn nach jedem fertigen Feature/Fix und spätestens vor
  „In Review" oder Release aus.
- Subagents ohne Skill-Tool lesen `.claude/skills/integrity/SKILL.md` und arbeiten die
  Schritte direkt ab.
- Es gibt (bewusst) kein technisches Gate-Skript/Hook — die Disziplin liegt in dieser Regel.

## Verbote
- Kein `--no-verify`, kein Abschalten von Warnungen (`#pragma GCC diagnostic ignored`,
  `# noqa`) ohne punktuelle Begründung
- Kein Umbau/„Aufräumen" fremder Module als Beifang eines Features ohne Rückfrage
