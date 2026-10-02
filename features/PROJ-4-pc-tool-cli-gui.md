# PROJ-4: PC-Tool CLI/GUI

## Status: In Progress
**Created:** 2026-10-02
**Last Updated:** 2026-10-02

## Dependencies
- PROJ-3 (Serielles Protokoll, Vertrag in `docs/SPEC.md`, Protokollversion 1)

## Summary
Optionales Python-PC-Tool `umwelt_ctl` (Konsolenbefehl `umwelt`) für die Umgebungssensoren-Anzeige:
Verbindung ohne Reset, Port-Erkennung, Werte/Status lesen, Einstellungen ändern, Alarm quittieren,
Uhr stellen, Live-`monitor` und eine Tkinter-GUI mit vier Live-Kacheln, Alarmanzeige und Temperaturverlauf.

## User Stories
- Als auswertende Person möchte ich mit `umwelt read` die aktuellen Werte in °C, % rF, hPa und Ω sehen, um ohne Gerät vor Augen zu prüfen.
- Als auswertende Person möchte ich Intervall, Schwellwerte, Temperatur-Offset und Piezo am PC einstellen, um nicht am kleinen Touch-Display tippen zu müssen.
- Als Nutzer möchte ich in einer GUI die vier Werte live, einen Temperaturverlauf und aktive Alarme sehen und quittieren.
- Als Nutzer möchte ich, dass das Verbinden das Gerät nicht neu startet (Uhr und Zustand bleiben erhalten).

## Placement
- **Protokoll:** genutzt: `PING`, `STATUS`, `READ`, `CFG`, `CFG <key> <value>`, `CFG RESET`, `STREAM`, `ACK`, `TIME`; Events `BOOT`, `DATA`, `ALARM`, `SENSOR` — keine Änderung
- **PC-Tool:** `umwelt ping|status|ports|read|config [key [value]]|config reset|ack|time [sync]|monitor|gui`
- **Ohne PC nutzbar:** ja — das Gerät arbeitet autark, das Tool ist Zusatz

## Out of Scope
- CSV-Format und -Ablage (PROJ-5)
- Auswertung/Diagramme vorhandener CSV-Dateien, Plot-Bibliotheken (matplotlib o. Ä.)
- Diagnosebefehle (`DEBUG TOUCH`, `TESTPATTERN`, `CAL SHOW`)

## Acceptance Criteria
- [ ] Angenommen das Gerät hängt an USB, wenn `umwelt ping` läuft, dann erscheint „PONG – Umgebungssensoren Firmware <fw> an <Port>“ und das Gerät startet nicht neu (Uptime läuft weiter).
- [ ] Angenommen kein `--port`, wenn ein Befehl läuft, dann wird der Port über `UMWELT_PORT`, sonst über USB-VID 0x2341 gefunden; `--port` hat Vorrang.
- [ ] Angenommen der Sensor fehlt, wenn `umwelt read` läuft, dann erscheint eine deutsche Meldung „Sensor nicht verfügbar …“ (ERR 5), Exit-Code ≠ 0, kein Traceback.
- [ ] Angenommen ein beliebiger `ERR`-Code (1, 2, 3, 5, 7), dann wird er über eine Tabelle in einen deutschen Text übersetzt.
- [ ] Angenommen `umwelt config T_HI 28,5`, dann sendet das Tool `CFG T_HI 2850`; ungültige Eingaben werden lokal mit deutscher Meldung abgelehnt, ohne zu verbinden.
- [ ] Angenommen `umwelt config reset`, dann fragt das Tool nach (außer mit `-y`).
- [ ] Angenommen der Port ist belegt, dann meldet das Tool „Port … ist belegt …“ statt eines Tracebacks.
- [ ] Angenommen das Gerät startet mitten in einer Sitzung neu (`EVT BOOT`), dann liest das Tool `STATUS` neu, stellt die Uhr (`TIME`) und schaltet `STREAM` wieder ein.
- [ ] Angenommen die GUI ist verbunden, dann zeigt sie vier Kacheln, Statuszeile, Temperaturverlauf (Canvas) und bei Alarm einen rot blinkenden Text mit „Quittieren“; die Oberfläche friert nie ein.
- [ ] Angenommen der Sensor fehlt, dann zeigt die GUI „Sensor nicht erreichbar“ statt Zahlen (nie 0).

## Edge Cases
- `EVT`-Zeilen zwischen den `C`-Zeilen von `CFG` → an Event-Callbacks, Antwort wird weiter gesammelt.
- Ungültiges `EVT DATA` (falsche Feldzahl, keine Zahl) → protokolliert und verworfen.
- Werte außerhalb des SPEC-Plausibilitätsbereichs → ungültig (`--`), nicht angezeigt.
- Board resettet beim Öffnen doch (Treiber) → Ready-Check wartet auf `EVT BOOT`.
- Fehlende Antwort / fehlendes `END` → Zeitüberschreitung, kein Hängen.
- Falsches Gerät am Port (anderer Produktname im `PONG`) → deutsche Meldung „falscher Port?“.

## Device & Runtime Behaviour
| Aspekt | Verhalten |
|--------|-----------|
| Autarkie | Gerät funktioniert ohne PC |
| Protokoll | keine Änderung |
| PC-Tool | Lese-Timeout 0,1 s, Antwort-Timeout 2 s; Port wird immer geschlossen; GUI verbindet automatisch neu |
| Reset / Stromausfall | `EVT BOOT` → STATUS/TIME/STREAM neu |
| Destruktive Aktionen | `config reset` (CLI: Rückfrage oder `-y`), „Standardwerte …“ (GUI: Rückfrage) |

## Decision Log

### Product Decisions
| Entscheidung | Begründung | Datum |
|--------------|------------|-------|
| CLI-Werte für `config` in physikalischen Einheiten (°C, %, s) mit Komma oder Punkt | Lesbarer als Rohwerte (0,01 °C); Umrechnung nur in `protocol.py` | 2026-10-02 |
| `monitor` ohne `--interval` nutzt `STREAM 1`, mit `--interval S` fragt er per `READ` ab | SPEC lässt die Bedeutung offen; `CFG INTERVAL` zu ändern wäre ein dauerhafter Eingriff ins EEPROM | 2026-10-02 |
| PING prüft den Produktnamen `Umgebungssensoren` | Verhindert Arbeiten mit einem fremden Arduino am Port | 2026-10-02 |

### Technical Decisions
| Entscheidung | Begründung | Datum |
|--------------|------------|-------|
| Muster aus GloveboxControl: Reader- + Dispatcher-Thread, Worker-Thread + Queue + `root.after` in der GUI | Bewährt; GUI blockiert nie | 2026-10-02 |
| `MIN_FW_VERSION = 0.1.0` | Erste Firmware mit Protokollversion 1; anpassen, sobald die Firmware ihre Version festlegt | 2026-10-02 |

---

## Tech Design (Solution Architect)
Kein separates `/architecture` — Muster aus GloveboxControl übernommen (Auftrag des Orchestrators).

## Implementation Notes
- Module: `pc/src/umwelt_ctl/protocol.py` (Parsing, Fehlertabelle, Umrechnung, Befehle), `device.py`
  (SerialTransport mit DTR/RTS aus, Ready-Check, Reboot-Abgleich, Port-Erkennung, `PortBusy`),
  `cli.py`, `gui.py`, `messlog.py` (PROJ-5), `__main__.py`.
- GUI: Reiter „Live“ (vier Kacheln, Canvas-Verlauf der letzten 360 Temperaturwerte, CSV an/aus) und
  „Einstellungen“ (Intervall, Offset, vier Schwellwerte, Piezo, Standardwerte, Uhr); Alarmband oben.
  Zustände: getrennt / laden / Sensorfehler / Werte.
- Tests: `pc/tests/` mit `FakeUmwelt` (SPEC-Modell) — 140 Host-Tests; Hardware-Tests in
  `test_hardware.py` (`@pytest.mark.hardware`, Port `UMWELT_PORT`/COM9) geschrieben, noch nicht ausgeführt.
- Offen: Hardware-Lauf gegen die neue Firmware (PROJ-2/3), Firmware-Version für `MIN_FW_VERSION` abgleichen.

## QA Test Results
_To be added by /qa_

## Release
_To be added by /release_
