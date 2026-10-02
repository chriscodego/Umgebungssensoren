# PROJ-3: Serielles Protokoll (Firmware-Seite)

## Status: In Progress
**Created:** 2026-10-02
**Last Updated:** 2026-10-02

## Dependencies
- PROJ-2

## Summary
Firmware-Seite des Protokolls Version 1 laut `docs/SPEC.md`: PING, STATUS, READ, CFG (Liste/Setzen/RESET), STREAM, ACK, TIME; Events BOOT, DATA, ALARM, SENSOR; Diagnose DEBUG TOUCH, TESTPATTERN, CAL SHOW.

## Acceptance Criteria
- [ ] `PING` → `OK PONG Umgebungssensoren 0.1.0`
- [ ] `READ` → `OK <t> <rh> <p> <gas> <ageSec>` mit plausiblen Werten; Sensor fehlt → `ERR 5`
- [ ] Zeile > 80 Byte → `ERR 2`, unbekannter Befehl → `ERR 1`, `ACK` ohne Alarm → `ERR 7`
- [ ] `STREAM 1` → nach jeder Messung `EVT DATA …`
- [ ] `TIME 12:34:56` → `OK`; `TIME` → `OK 12:34:5x`; `TIME 24:00:00` → `ERR 2`

## Implementation Notes
- Auslegung von SPEC-Lücken (Handbuch Kap. 8): `CFG INTERVAL OFF` → ERR 2; `CFG <unbekannt>` → ERR 3, `CFG <bekannt>` ohne Wert → ERR 2; T_LO ≥ T_HI bzw. RH_LO ≥ RH_HI → ERR 3; `READ` bei ERROR → `OK` mit `-`.
- Uhr und Uptime zählen ganze Sekunden (über den millis()-Überlauf hinweg korrekt).
- PC-Host-Tests: 140 passed (`python -m pytest pc/tests`). Smoke-Test am Gerät **offen** (nicht geflasht).
