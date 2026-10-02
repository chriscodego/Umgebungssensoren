# PROJ-8: Control Panel (PySide6) mit dauerhaftem Messwert-Log

## Status: In Review
**Created:** 2026-10-02
**Last Updated:** 2026-10-02

## Dependencies
- Requires: PROJ-4 (PC-Tool: `umwelt_ctl.protocol`/`device` werden wiederverwendet)
- Requires: PROJ-5 (CSV-Format des Messprotokolls, `umwelt_ctl.messlog`)

## Summary
Desktop-Oberfläche analog zum Schwesterprojekt „RFB Controll Panel": zeigt die BME680-Werte live
(vier Kacheln mit Verlaufskurve), meldet Alarme mit Quittieren-Knopf, ändert die Geräteeinstellungen
und speichert jede Messung dauerhaft in einer lokalen SQLite-Datenbank mit Verlaufsansicht und CSV-Export.

## User Stories
- Als Nutzer möchte ich die aktuellen Werte groß und mit Verlauf sehen, um die Raumluft auf einen Blick zu beurteilen
- Als Nutzer möchte ich einen Alarm sofort bemerken und am PC quittieren können
- Als Nutzer möchte ich, dass alle Messwerte automatisch gespeichert werden, solange das Gerät verbunden ist
- Als Nutzer möchte ich den Verlauf der letzten Stunde/24 h/7 Tage/alles ansehen und als CSV exportieren
- Als Nutzer möchte ich sehen, wie groß das Log ist, und es nur nach Rückfrage löschen

## Placement
- **Gerät:** keine Änderung
- **Protokoll:** keine Änderung (genutzt: `PING`, `STATUS`, `READ`, `CFG`, `CFG <key> <value>`, `CFG RESET`, `STREAM 1/0`, `ACK`, `TIME`; Events `DATA`, `ALARM`, `SENSOR`, `BOOT`)
- **PC-Tool:** neues Paket `umwelt_panel` (`python -m umwelt_panel`, Konsolenbefehl `umwelt-panel`), Extra `panel`
- **Ohne PC nutzbar:** ja (das Panel ist optional)

## Out of Scope
- Installer, Updater, Bluetooth, Alembic/SQLAlchemy
- Automatische Aufbewahrungsfrist/Löschung (Entscheidung des Nutzers)
- Ersetzen der Tk-GUI (`umwelt gui` bleibt bis zur Nutzerentscheidung)

## Acceptance Criteria
- [x] Angenommen das Gerät ist angesteckt, wenn das Panel startet, dann verbindet es automatisch (USB-VID 0x2341, `--port`/`UMWELT_PORT`), ohne den Uno zurückzusetzen, schaltet `STREAM 1` ein, stellt die Uhr und zeigt Port + Firmware im Verbindungsbanner
- [x] Angenommen eine Messung kommt an, wenn `EVT DATA` eintrifft, dann zeigen die vier Kacheln die Werte mit Dezimalkomma und Einheit, die Gas-Kachel zusätzlich den Trend; ungültige Werte erscheinen als `--`, nie als 0
- [x] Angenommen „automatisch aufzeichnen" ist an (Standard), wenn eine Messung eintrifft, dann wird sie mit PC-Zeit (UTC) und Alarm-Bitmaske in der Datenbank gespeichert; ungültige Werte als leer; fehlerhafte `EVT DATA` werden nie gespeichert
- [x] Angenommen ein Alarm wird aktiv, dann erscheint ein rot blinkendes Band mit Text; „Quittieren" sendet `ACK`, danach bleibt das Band blass sichtbar, bis die Ursache weg ist
- [x] Angenommen das USB-Kabel wird gezogen, dann zeigt das Banner „Nicht verbunden – warte auf das Gerät …", der Port wird geschlossen und nach dem Einstecken automatisch neu verbunden; ein `EVT BOOT` mitten in der Sitzung stellt Uhr/Status/Stream wieder her
- [x] Angenommen „Trennen" wurde geklickt, dann wird nicht automatisch neu verbunden, bis „Verbinden" geklickt wird
- [x] Angenommen das Gerät ist verbunden, wenn der Nutzer die Einstellungen öffnet, dann kann er Intervall, Temperatur-Offset, Schwellwerte (an/aus), Piezo ändern (nur geänderte Werte werden gesendet), die Uhr synchronisieren und nach Bestätigung auf Standardwerte zurücksetzen; `ERR`-Codes erscheinen als deutsche Meldung
- [x] Angenommen der Nutzer öffnet „Verlauf", dann sieht er die gewählte Messgröße für 1 h/24 h/7 Tage/alles aus der Datenbank (Abfrage im Hintergrund, Lücken bleiben Lücken)
- [x] Angenommen der Nutzer wählt „CSV exportieren", dann entsteht für den gewählten Zeitraum eine Datei im Format von docs/SPEC.md „PC-Tool" (`;`, UTF-8 mit BOM, Kopfzeile, Dezimalkomma, ISO 8601 mit Offset, ungültig leer)
- [x] Angenommen das Log enthält Werte, dann sind Anzahl, Größe und Pfad sichtbar; „Log löschen" löscht erst nach Bestätigung
- [x] Angenommen die Datenbank ist beschädigt oder von einer neueren Version, dann startet das Panel nicht, sondern zeigt eine deutsche Meldung (kein Traceback)

## Edge Cases
- Sensor fehlt (`MISSING`): Banner orange „Verbunden – Sensor nicht erreichbar", Kacheln mit Fehlertext, Zeilen mit leeren Werten und Alarm 16
- Firmware zu alt: eine Fehlermeldung, kein endloser Wiederholversuch
- Datenbank gesperrt beim Schreiben: Messung wird angezeigt, eine Meldung pro Störungsphase, keine Meldungsflut
- Export-Ziel nicht beschreibbar: deutsche Meldung, keine halbe Datei (Schreiben in `.tmp`, dann umbenennen)
- Zwei Panels gleichzeitig: Migration in `BEGIN IMMEDIATE`, Port nur von einem Prozess nutzbar (Meldung „Port belegt")

## Device & Runtime Behaviour
| Aspekt | Verhalten |
|--------|-----------|
| Autarkie | Gerät arbeitet ohne Panel weiter |
| Protokoll | keine Änderung |
| PC-Tool | Serial nur im Worker-`QThread`; Datenbankabfragen/Export im `QThreadPool`; GUI blockiert nie |
| Destruktive Aktionen | Config-Reset und Log löschen mit Bestätigung, kein Undo |
| Datenablage | `%LOCALAPPDATA%\Umgebungssensoren\messwerte.db` (lokal, nicht im Repo, wächst unbegrenzt; Löschen entscheidet der Nutzer) |

## Decision Log

### Product Decisions
| Entscheidung | Begründung | Datum |
|--------------|------------|-------|
| PySide6 + sqlite3 + platformdirs nur im Extra `panel` | Nutzerentscheidung (pc.md, Abschnitt „Control Panel"); CLI bleibt pyserial-only | 2026-10-02 |
| Automatisches Loggen standardmäßig an, abschaltbar | Auftrag: „dauerhaft loggen, sobald verbunden" | 2026-10-02 |
| Keine automatische Retention | security.md: Löschen ist Nutzerentscheidung | 2026-10-02 |

### Technical Decisions
| Entscheidung | Begründung | Datum |
|--------------|------------|-------|
| Werte als Draht-Ganzzahlen in SQLite, `ts_utc` = Unix-Millisekunden | exakt, keine Float-Drift; Umrechnung nur in `umwelt_ctl.protocol` | 2026-10-02 |
| Schema-Version in `PRAGMA user_version`, Migrationsliste in `data/db.py` | einfach, ohne Alembic; neuere DB wird abgelehnt | 2026-10-02 |
| CSV-Export über `messlog.csv_text`/`make_row` | identisches Format wie `monitor --csv`, keine zweite CSV-Logik | 2026-10-02 |
| Gas-Trend im PC berechnet (gleitender Mittelwert 1/8, ±5 %) | wie Geräteanzeige; kein Protokollfeld nötig | 2026-10-02 |
| pytest-qt per `-p no:pytest-qt` aus, in conftest nur mit PySide6 geladen | `pip install -e "pc[dev]"` (CI) läuft weiter ohne PySide6 | 2026-10-02 |

---

## Implementation Notes
- Paket `pc/src/umwelt_panel/`: `core/` (models, trend, errors, services: device_session, log_service, settings_service), `data/` (db, repositories), `ui/` (main_window, device_controller, history_view, settings_dialog, widgets, resources/app.qss)
- Tests: `pc/tests/test_panel_core.py` (Qt-frei), `pc/tests/test_panel_gui.py` (Marker `gui`, offscreen)
- Screenshot: `docs/screenshots/panel.png`
- Hardware-Test gegen COM9: noch offen (kein Hardware-Slot)

## QA Test Results
_To be added by /qa_

## Release
_To be added by /release_
