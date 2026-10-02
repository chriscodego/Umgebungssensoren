# PROJ-X: Feature Name

## Status: Planned
**Created:** YYYY-MM-DD
**Last Updated:** YYYY-MM-DD

## Dependencies
- None

## Summary
_Zwei, drei Sätze: was das Feature tut und für wen._

## User Stories
- Als [Nutzertyp] möchte ich [Aktion], um [Ziel] zu erreichen

## Placement
<!-- Where this feature lives. Delete lines that do not apply. -->
- **Gerät:** _Seite / Button / Touch-Ziel / Schwellwert-Alarm / Signal_
- **Protokoll:** _neue oder genutzte Befehle / Events — oder „keine Änderung"_
- **PC-Tool:** _CLI-Kommando / GUI-Ansicht / monitor_
- **Ohne PC nutzbar:** _ja / nein (Begründung)_

## Out of Scope
<!-- What this feature explicitly does NOT cover. Critical for developer handoffs. -->
- _Beispiel: Auswertung/Diagramm der CSV im PC-Tool (eigenes Feature — PROJ-X)_

## Acceptance Criteria

**Format:** Angenommen [Vorbedingung] / Wenn [Aktion] / Dann [Ergebnis]

- [ ] Angenommen [Vorbedingung], wenn [Aktion], dann [Ergebnis]
- [ ] Angenommen [Vorbedingung], wenn [Aktion], dann [Ergebnis]

## Edge Cases
- Was passiert, wenn ...?
- Wie behandeln wir ...?

## Device & Runtime Behaviour
<!-- Fill in every row that applies; delete rows that genuinely do not. -->
| Aspekt | Verhalten |
|--------|-----------|
| Autarkie | _funktioniert ohne PC ja/nein_ |
| Touch-Bedienung | _Ziele, Mindestgröße (≥ ~24×24 px laut SPEC, größer wo möglich), Tippen, Seitenwechsel, Bestätigung_ |
| Anzeige | _was wird wann gezeigt/aktualisiert, Einheiten °C/%/hPa, Texte mit Umlauten (CP437), kein Flackern_ |
| Zeitverhalten | _Messintervall, Sensor-Wandlungszeit (nicht blockierend), Aufwärmphase Gassensor, millis-Überlauf_ |
| Persistenz | _EEPROM (überlebt Stromausfall: Intervall, Schwellwerte, Einheiten, Offsets) / nur RAM (Messwerte, Verlauf, Uhr; endet bei Reset)_ |
| Reset / Stromausfall | _was geht verloren, was meldet das Gerät (`EVT BOOT`)_ |
| Protokoll | _keine Änderung / additiv / brechend — betroffene Befehle, Events, Fehlercodes_ |
| PC-Tool | _CLI/GUI-Verhalten, Timeouts, Verhalten ohne Gerät_ |
| Ressourcen | _grobe RAM-/Flash-/EEPROM-Schätzung (wird in /architecture präzisiert)_ |
| Destruktive Aktionen | _Bestätigung am Gerät und am PC, rückgängig machbar?_ |
| Datenablage | _was wird protokolliert (Messwerte, Zeitstempel), wo liegt die Datei, wie lange? (keine Personendaten; Ablageort = Nutzerentscheid)_ |

## Technical Requirements (optional)
- Speicher: _z. B. zusätzliches RAM ≤ 100 B_
- Timing: _z. B. Reaktion auf Touch < 100 ms, Anzeige-Update 1×/s_
- Hardware: _Arduino Uno R3, Joy-IT RB-TFT1.8-T, BME680 (I2C), Windows 10/11 für das PC-Tool_

## Open Questions
<!-- Unresolved questions from the spec interview. Close them in /refine when answered. -->
- [ ] Frage 1

## Decision Log
<!-- Record of conscious decisions made and why. Added to by /write-spec and /architecture. -->

### Product Decisions
<!-- Added by /write-spec -->
| Entscheidung | Begründung | Datum |
|--------------|------------|-------|
| _Beispiel: Messverlauf nur im RAM_ | _EEPROM-Schreibzyklen sind begrenzt; der PC protokolliert dauerhaft in die CSV_ | YYYY-MM-DD |

### Technical Decisions
<!-- Added by /architecture -->
| Entscheidung | Begründung | Datum |
|--------------|------------|-------|
| _Beispiel: Texte und Touch-Ziele in PROGMEM_ | _Spart RAM; Zeichnen und Treffer-Prüfung nutzen dieselbe Tabelle_ | YYYY-MM-DD |

---
<!-- Sections below are added by subsequent skills -->

## Tech Design (Solution Architect)
_To be added by /architecture_

## Implementation Notes
_To be added by /firmware and /pc (incl. RAM/Flash after build)_

## QA Test Results
_To be added by /qa_

## Release
_To be added by /release_
