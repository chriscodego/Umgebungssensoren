# PROJ-2: Firmware-Grundgerüst

## Status: In Progress
**Created:** 2026-10-02
**Last Updated:** 2026-10-02

## Dependencies
- PROJ-1

## Summary
Autarke Anzeige der BME680-Werte (Temperatur, Feuchte, Druck, Gaswiderstand + Trend) auf der Übersichtsseite, Touch mit eigenem XPT2046-Treiber und Kalibrierung, fehlender Sensor als normaler Zustand.

## Placement
- **Gerät:** Übersicht (Statuszeile + 4 Wertekacheln), Seitenleiste unten (Übersicht | Einstellung), Kalibrierung
- **Protokoll:** siehe PROJ-3 · **Ohne PC nutzbar:** ja

## Acceptance Criteria
- [ ] Angenommen der BME680 ist angeschlossen, wenn das Gerät startet, dann zeigt die Übersicht nach ≤ 1 Messung vier plausible Werte (°C, %, hPa, kΩ mit Trendpfeil)
- [ ] Angenommen kein BME680 antwortet (0x76/0x77), dann zeigt die Statuszeile „Sensor fehlt!“, alle Werte `--`, Wiederholversuch alle 5 s, keine Blockade
- [ ] Angenommen der Bildschirm wird beim Einschalten berührt, dann startet die Kalibrierung (4 Kreuze)
- [ ] Werte ändern sich ohne Flackern und ohne Ziffernreste

## Device & Runtime Behaviour
| Aspekt | Verhalten |
|---|---|
| Zeitverhalten | Forced Mode, Trigger → 180 ms warten → „new data“ pollen (10 ms), Timeout 1 s → ERROR; Intervall aus EEPROM |
| Persistenz | EEPROM Layout 1 (SPEC), Messwerte nur RAM |
| Ressourcen | siehe Implementation Notes |

## Technical Decisions
| Entscheidung | Begründung | Datum |
|---|---|---|
| Eigener BME680-Treiber, Bosch-Ganzzahlkompensation ohne int64 (exakte 32-bit-Zerlegung) | Flash; per Python gegen die Bosch-Referenz geprüft (57 529 Fälle, 0 Abweichungen) | 2026-10-02 |
| Eigener gepollter TWI-Master statt `Wire` | Flash war mit Wire 268 B über 100 %; spart ~1 KB Flash und ~100 B RAM; jede Wartezeit begrenzt | 2026-10-02 |
| EEPROM wird beim Booten nie geschrieben (ungültig → Defaults nur im RAM) | Inhalt der Bestandsfirmware bleibt bis zur ersten Änderung erhalten (keine gültige EEPROM-Sicherung) | 2026-10-02 |

## Implementation Notes
- Module: `sensor`, `storage`, `display`, `ui`, `input`, `protocol`, `signal`; `.ino` dünn. FW 0.1.0.
- Build (2026-10-02): **Flash 31 506 B (97,7 %) · RAM 806 B (39 %)**, 0 Warnungen. > 95 % → Architekturthema: PROJ-7 (Verlauf) passt nicht ohne Einsparungen. Der TWI-ISR der Wire-Bibliothek (~0,8 KB) wird trotzdem gelinkt, weil Adafruit GFX → BusIO `Wire.h` einbindet.
- **Nicht geflasht** (Upload braucht die Freigabe des Nutzers selbst); optische Abnahme offen.
