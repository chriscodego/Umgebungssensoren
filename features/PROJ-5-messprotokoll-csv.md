# PROJ-5: Messprotokoll (CSV)

## Status: In Progress
**Created:** 2026-10-02
**Last Updated:** 2026-10-02

## Dependencies
- PROJ-4 (PC-Tool CLI/GUI)

## Summary
Das PC-Tool schreibt jede empfangene Messung mit PC-Zeitstempel in eine CSV-Datei, die Excel direkt
öffnen kann — über `umwelt monitor --csv [DATEI]` oder den Schalter „Aufzeichnen“ in der GUI.

## User Stories
- Als auswertende Person möchte ich die Messwerte lückenlos in einer CSV-Datei haben, um sie in Excel auszuwerten.
- Als Nutzer möchte ich wissen, wo die Datei liegt, und selbst über Aufbewahrung/Löschen entscheiden.

## Placement
- **Protokoll:** genutzt: `EVT DATA` (Stream), `READ` (Abfrage), `STATUS`/`EVT ALARM` (Alarmspalte) — keine Änderung
- **PC-Tool:** `umwelt monitor --csv [DATEI]`, GUI-Reiter „Live“ → „Messprotokoll (CSV)“
- **Ohne PC nutzbar:** ja (Gerät misst weiter; Protokoll nur bei laufendem Tool)

## Out of Scope
- Automatische Aufbewahrung/Löschung, Rotation
- Auswertung der CSV im Tool

## Acceptance Criteria
- [ ] Angenommen eine neue oder leere Datei, wenn die erste Zeile geschrieben wird, dann beginnt sie mit UTF-8-BOM und der Kopfzeile `zeit;temperatur_c;feuchte_proz;druck_hpa;gas_ohm;alarm`.
- [ ] Angenommen eine vorhandene Datei, dann werden Zeilen angehängt, ohne zweiten BOM und ohne zweite Kopfzeile.
- [ ] Angenommen eine Messung, dann steht in `zeit` die PC-Zeit als ISO 8601 mit Offset (`2026-10-02T14:03:12+02:00`), die Werte in °C, %, hPa mit Dezimalkomma und Ω als Ganzzahl.
- [ ] Angenommen ein ungültiger Wert (`-`) oder fehlender Sensor, dann bleibt die Zelle leer, nie `0`.
- [ ] Angenommen ein unbrauchbares `EVT DATA`, dann entsteht keine Zeile.
- [ ] Angenommen das Tool stürzt ab, dann sind alle bis dahin empfangenen Zeilen auf der Platte (Datei je Zeile geöffnet/geschlossen).
- [ ] Angenommen keine Datei angegeben, dann ist der Standard `~/umwelt_messwerte.csv`; das Tool nennt den Pfad.

## Edge Cases
- Datei in Excel geöffnet (Windows-Sperre) → Zeilen warten im Speicher und werden mit der nächsten Zeile nachgetragen; Warnung.
- Ordner existiert nicht → deutsche Fehlermeldung, kein Absturz.
- `monitor --interval` und Sensor fehlt (`ERR 5`) → Zeile ohne Werte mit `alarm` 16 („keine Daten“ = Alarm).

## Device & Runtime Behaviour
| Aspekt | Verhalten |
|--------|-----------|
| Datenablage | Messwerte + PC-Zeitstempel + Alarm-Bitmaske; Standard `~/umwelt_messwerte.csv` (lokal, außerhalb des Repos); keine Personendaten; Aufbewahrung = Nutzerentscheid |
| PC-Tool | eine Zeile je `EVT DATA` (Stream) bzw. je `READ` (`--interval`); GUI: Aufzeichnung standardmäßig aus |
| Protokoll | keine Änderung |

## Decision Log

### Product Decisions
| Entscheidung | Begründung | Datum |
|--------------|------------|-------|
| Spalte `alarm` = Alarm-Bitmaske der SPEC (0 = keiner, leer = unbekannt) | SPEC nennt die Spalte, nicht den Inhalt; Bitmaske ist verlustfrei | 2026-10-02 |
| Gas in Ω als Ganzzahl (Spalte `gas_ohm`) | Spaltenname nennt Ω; keine Rundung | 2026-10-02 |
| GUI-Aufzeichnung standardmäßig aus | Ablage ist Nutzerentscheid | 2026-10-02 |

### Technical Decisions
| Entscheidung | Begründung | Datum |
|--------------|------------|-------|
| Datei je Zeile öffnen/anhängen/schließen | Flush je Zeile, robust gegen Excel-Sperre, BOM/Kopf auch nach Löschen der Datei korrekt | 2026-10-02 |
| Zahlenformat per Ganzzahl-Arithmetik in `protocol.py` | Kein Float-Drift; Umrechnung an einer Stelle | 2026-10-02 |

---

## Tech Design (Solution Architect)
Kein separates `/architecture` — Format laut `docs/SPEC.md` („PC-Tool“).

## Implementation Notes
- `pc/src/umwelt_ctl/messlog.py`: `MessLogger`, `default_log_path()`, `timestamp()`, `HEADER`.
- Tests: `pc/tests/test_messlog.py` (BOM, Kopf, Anhängen, leere Datei, leere Zellen, Zeitstempel, gesperrte Datei),
  CSV-Pfade in `test_cli.py` (Monitor Stream/Polling) und `test_gui.py` (Aufzeichnung an/aus).
- Dokumentiert in `docs/configuration.md`.

## QA Test Results
_To be added by /qa_

## Release
_To be added by /release_
