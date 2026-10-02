# PROJ-10: Live-Verlaufsdiagramm auf dem Gerät

## Status: In Progress
**Created:** 2026-10-02
**Last Updated:** 2026-10-02

## Dependencies
- PROJ-2 (Firmware-Grundgerüst: Display, Touch, Übersicht)
- Löst PROJ-7 („Verlauf auf dem Gerät", nur Roadmap) ab

## Summary
Neue Seite „Verlauf" auf dem Gerät: Liniendiagramm der letzten ~32 Minuten für einen Messwert
(Temperatur, Feuchte, Druck, Gas) aus einem RAM-Ringpuffer, den das Gerät selbst füllt. Kein PC und
keine Protokolländerung nötig; der Langzeitverlauf bleibt im Control Panel (PROJ-8, SQLite).
Variante A, vom Nutzer gewählt.

## User Stories
- Als Nutzer möchte ich am Gerät sehen, wie sich ein Messwert in der letzten halben Stunde entwickelt hat, ohne einen PC anzuschließen
- Als Nutzer möchte ich durch Antippen zwischen den vier Messwerten wechseln
- Als Nutzer möchte ich, dass das Gerät von selbst zur Übersicht zurückkehrt, wenn ich die Verlaufsseite offen lasse

## Placement
- **Gerät:** Übersicht → Antippen einer Wertkachel öffnet „Verlauf" für diesen Wert; Diagramm antippen → nächster Wert; Taste „Zurück" unten
- **Protokoll:** keine Änderung (Protokollversion 1 bleibt)
- **PC-Tool:** keine Änderung
- **Ohne PC nutzbar:** ja

## Out of Scope
- Langzeitverlauf, Export, Zoom (bleibt im Control Panel PROJ-8)
- Verlauf über einen Reset/Stromausfall hinaus (nur RAM, nie EEPROM)
- Übertragung des Gerätepuffers an den PC (wäre eine Protokolländerung)

## Acceptance Criteria
- [ ] Angenommen die Übersicht ist sichtbar, wenn ich eine Wertkachel antippe, dann wird ein unquittierter Alarm quittiert (wie bisher) und die Seite „Verlauf" für genau diesen Wert öffnet sich
- [ ] Angenommen die Übersicht ist sichtbar, wenn ich die obere Leiste (Uhr/Status) antippe, dann öffnen sich weiterhin die Einstellungen
- [ ] Angenommen die Seite „Verlauf" ist offen, wenn ich das Diagramm antippe, dann wechselt die Anzeige zum nächsten Wert (Temperatur → Feuchte → Druck → Gas → Temperatur)
- [ ] Angenommen die Seite „Verlauf" ist offen, wenn ich „Zurück" (unten, 24 px hoch) antippe oder 60 s nichts berühre, dann erscheint die Übersicht
- [ ] Angenommen das Gerät misst, dann kommt alle `GRAPH_STEP_S` (30 s) ein Punkt je Wert in den Ringpuffer (64 Punkte ≈ 32 min); die Kopfzeile zeigt Wertname mit Einheit (`°` per CP437) und „32 min"
- [ ] Angenommen ein Wert ist ungültig oder der Sensor fehlt, dann entsteht im Diagramm eine Lücke (nie ein Punkt bei 0)
- [ ] Angenommen es gibt gültige Punkte, dann zeigt die linke Spalte oben das Maximum und unten das Minimum der Achse als Ganzzahl-Skala mit einer Nachkommastelle (Komma, kein `float`); bei flachem Verlauf spannt die Achse mindestens 1,0 Einheiten
- [ ] Angenommen es gibt noch keine gültigen Punkte (z. B. kurz nach dem Einschalten), dann zeigen beide Beschriftungen `--` und das Diagramm ist leer
- [ ] Angenommen ein neuer Punkt kommt hinzu, dann wird nur das Diagramm (und die Beschriftungen) neu gezeichnet — spaltenweise von links nach rechts in mehreren `loop()`-Durchläufen, ohne Löschen des ganzen Bildschirms
- [ ] Angenommen die Firmware ist gebaut, dann bleiben Flash ≤ 32 000 B und globaler RAM ≤ 1 536 B

## Edge Cases
- Messintervall > 30 s: der letzte Messwert wird mehrfach eingetragen (Treppenstufe), keine Interpolation
- Sensor fehlt/fällt aus: `sensor_data().valid` ist 0 → Lücken; nach Wiederkehr geht die Linie weiter
- Gas > 3 276,7 kΩ: wird auf 3 276,7 kΩ begrenzt (int16-Puffer)
- Neuer Punkt während das Diagramm gezeichnet wird: Zeichnen beginnt mit den neuen Daten von vorn
- Alarm während die Verlaufsseite offen ist: wie auf der Einstellungsseite blinkt nur die Übersicht; der Piezo läuft unabhängig

## Device & Runtime Behaviour
| Aspekt | Verhalten |
|--------|-----------|
| Autarkie | funktioniert ohne PC |
| Touch-Bedienung | Kachel 80×58 → Verlauf; Diagrammrahmen 122×90 = Ziel „nächster Wert"; „Zurück" 156×24; Hit-Test aus denselben Konstanten (`GRAPH_X/Y/W/H`, `BACK_Y/H`, Kachelraster) wie das Zeichnen |
| Anzeige | Kopfzeile Wertname + Zeitspanne; links Max/Min (6 Zeichen, feste Breite); Linie gelb; Lücken bleiben leer; kein `fillScreen()` in `loop()` |
| Zeitverhalten | Punkt alle 30 s (`millis()`-Differenz, überlaufsicher); Zeichnen in Schritten zu 8 Segmenten |
| Persistenz | nur RAM (4 × 64 × 2 B = 512 B); geht bei Reset verloren |
| Reset / Stromausfall | Verlauf leer (alle Punkte Lücke), füllt sich neu |
| Protokoll | keine Änderung |
| PC-Tool | keine Änderung |
| Ressourcen | RAM +535 B (806 → 1 341 B); Flash ≈ +1,2 KB (siehe Implementation Notes) |

## Decision Log

### Product Decisions
| Entscheidung | Begründung | Datum |
|--------------|------------|-------|
| Variante A: Verlauf aus eigenem RAM-Puffer, keine Protokolländerung | Gerät bleibt autark; Langzeitverlauf hat das Control Panel | 2026-10-02 |
| PROJ-7 wird durch PROJ-10 ersetzt | gleiches Ziel, konkretisiert | 2026-10-02 |

### Technical Decisions
| Entscheidung | Begründung | Datum |
|--------------|------------|-------|
| Neues Modul `history.*` (Ringpuffer), Zeichnen in `display.cpp`, Seite in `ui.cpp` | Trennung Daten/Anzeige wie bei der Übersicht | 2026-10-02 |
| Werte im Puffer in Zehnteln (0,1 °C / 0,1 % / 0,1 hPa / 0,1 kΩ), Lücke = −32768 | eine Skala für Beschriftung und Achse, int16 reicht | 2026-10-02 |
| Spaltenweises Neuzeichnen (Segment löschen + Linie) | kein Flackern, keine langen Blockaden | 2026-10-02 |

---

## Implementation Notes (Firmware, 2026-10-02)
- `config.h`: `GRAPH_POINTS` 64, `GRAPH_STEP_S` 30, `GRAPH_GAP`, `GRAPH_MIN_SPAN` 10, `GRAPH_X/Y/W/H` (38/12/122/90), `GRAPH_SEG_PER_PASS` 8; `FW_VERSION` 0.2.0
- `history.*`: `history_begin()` (alle Punkte Lücke), `history_poll()` (Punkt alle 30 s aus `sensor_data()`), `history_get()`, `history_generation()`
- `display.cpp`: `display_tileAt()` (Kachelraster), `display_graphInvalidate()`, `display_graphUpdate()`; `display_fmtNum()` kompakter neu geschrieben (gleiche Ausgabe)
- `ui.cpp`: `PAGE_GRAPH`, Kacheltipp öffnet den Verlauf, Diagrammtipp wechselt den Wert, „Zurück" und 60-s-Rückkehr wie Einstellungen
- Einsparung ohne Funktionsverlust: `DEBUG TOUCH` rechnet die Bildschirmposition erst beim Ausgeben um und gibt die fünf Werte in einer Schleife aus (gleiche Ausgabe, −190 B)
- **Speicher:** vorher 31 426 B Flash / 806 B RAM; jetzt 32 610 B Flash (101 %, passt nicht) / 1 341 B RAM
- **Blockiert (DECISION_NEEDED):** Das Feature braucht ≈ 1,2 KB Flash; ohne Streichen bestehender Funktionen ist das Budget nicht erreichbar. Vorschlag: Diagnosebefehle `DEBUG TOUCH` und `TESTPATTERN` entfernen (nicht Teil des stabilen Vertrags, weder PC-Tool noch Tests nutzen sie) → ≈ 31 880 B; zusätzlich `CAL SHOW` → ≈ 31 690 B. Erst nach Nutzerentscheid: bauen, flashen, SPEC.md „Anzeige" ergänzen
