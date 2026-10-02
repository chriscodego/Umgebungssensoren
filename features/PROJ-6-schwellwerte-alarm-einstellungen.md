# PROJ-6: Schwellwerte, Alarm, Einstellungen (Firmware-Seite)

## Status: In Progress
**Created:** 2026-10-02
**Last Updated:** 2026-10-02

## Dependencies
- PROJ-3, PROJ-4

## Summary
Schwellwerte T_HI/T_LO/RH_HI/RH_LO mit Hysterese, Sensor-Alarm, Quittierung (ACK / Antippen), Piezo; Einstellungsseite am Gerät (Intervall, Piezo, Kalibrieren, Standard).

## Acceptance Criteria
- [ ] Angenommen T_HI gesetzt, wenn 2 Messungen in Folge darüber liegen, dann `EVT ALARM 1 1`, Kachel blinkt rot mit Text „! zu hoch“, Piezo bei `BUZZER 1`
- [ ] Wenn der Wert ≥ 0,5 °C (RH: 2 %) innerhalb der Grenze liegt, dann `EVT ALARM 1 0`
- [ ] Antippen der Übersicht oder `ACK` quittiert: Blinken/Ton aus, Flag bleibt solange die Ursache besteht
- [ ] Sensor MISSING/ERROR → Flag 16, Statuszeile blinkt „Sensor fehlt!“/„Messfehler!“
- [ ] Einstellungen: −/+ (1·2·5·10·30·60 s), „Piezo: an/aus“, „Kalibrieren“, „Standard“ (zweites Antippen „Sicher?“ innerhalb 3 s)

## Implementation Notes
- Alarmlogik und Piezo im Modul `signal` (Timer2, 3 Töne alle 10 s solange unquittiert).
- Schwellwert-Flags bleiben bei fehlendem Sensor unverändert (nur Flag 16 wechselt).
- Gerätseitige Einstellungsänderungen erzeugen kein Event (SPEC kennt keins) — Lücke, Handbuch Kap. 8.
- Einstellungsseite kehrt nach 60 s ohne Berührung zur Übersicht zurück.
