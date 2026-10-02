# Release Notes

## 2026-10-02 — Firmware 0.2.0 · Control Panel 0.1.0 · PC-Tool `umwelt_ctl` 0.1.0

**Firmware 0.2.0** (geflasht auf COM9, ersetzt die Bestandsfirmware; Backup `docs/backup/*.hex`)
- BME680 mit eigenem Minimaltreiber (Temperatur, Feuchte, Druck, Gaswiderstand + Trend), Messintervall einstellbar (aktuell 1 s)
- Touch-Display: Übersicht mit vier Kacheln, Einstellungen (obere Leiste), Verlaufsseite (Kachel antippen)
- Schwellwert-Alarm mit Hysterese, optional Piezo; Einstellungen im EEPROM (Layout 1)
- Serielles Protokoll v1 (`docs/SPEC.md`); `DEBUG TOUCH` und `TESTPATTERN` entfallen (antworten `ERR 1`)
- Speicher: Flash 31 826 B (98,7 %), RAM 1 324 B (65 %). Ein Wechsel des EEPROM-Layouts setzt die Einstellungen zurück
- Bibliotheken: Adafruit GFX 1.12.6, Adafruit ST7735/ST7789 1.11.0, Adafruit BusIO 1.17.4, arduino:avr 1.8.8

**PC-Tool und Control Panel**
- CLI `umwelt` (ping, status, read, config, ack, time, monitor, gui) mit CSV-Messprotokoll
- Control Panel (PySide6): Live-Kacheln, Verlauf, SQLite-Langzeitlog, CSV-Export, Einstellungen, Update-Funktion
- Installer `UmgebungssensorenPanel-Setup-0.1.0.exe`; Updater liest `\\131.234.237.14\Gutmann\01_Interna\05_Software\Umgebungssensoren`
- Tags: `panel-v0.1.0` (Control Panel)

**Bekannt offen:** optische Abnahme des Displays am Gerät; Installation/Update/Deinstallation auf einem Rechner ohne Entwicklungsumgebung noch nicht geprüft.
