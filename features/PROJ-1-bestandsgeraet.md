# PROJ-1: Bestandsgerät analysieren

## Status: In Review
**Created:** 2026-10-02
**Last Updated:** 2026-10-02

## Dependencies
- None

## Summary
Die unbekannte Firmware auf COM9 wird vor dem ersten Upload beobachtet, gesichert und im Handbuch (Kap. 4) dokumentiert.

## Acceptance Criteria
- [x] Angenommen das Gerät läuft, wenn der Port nur lesend (DTR/RTS aus) geöffnet wird, dann ist die Ausgabe dokumentiert
- [x] Angenommen ein Upload steht an, wenn das Flash gesichert ist, dann liegt die Sicherung in `docs/backup/`
- [ ] Nutzer bestätigt den Befund und gibt das Überschreiben ausdrücklich frei

## Implementation Notes
- Befund: Handbuch Kap. 4. Ausgabe 9600 Baud, CSV `24.22,53.59,1013.91` (°C, %rF, hPa) etwa alle 4 s → BME680 angeschlossen und funktionsfähig; Adresse 0x76 oder 0x77 (die Bestandsfirmware probiert beide nacheinander, Disassembly).
- **Mangel:** `docs/backup/bestandsfirmware_eeprom.hex` ist identisch mit den ersten 1024 Byte des Flash-Abbilds — keine gültige EEPROM-Sicherung (Optiboot kann das EEPROM nicht auslesen). Die neue Firmware schreibt das EEPROM erst bei einer Einstellungsänderung.
