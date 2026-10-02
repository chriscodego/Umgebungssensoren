# SPEC — der Vertrag (Entwurf)

> **Status: Skelett.** Wird mit `/write-spec` und `/architecture` ausgefüllt. Solange ein Abschnitt
> „offen" ist, wird dazu kein Code geschrieben. Bei Widersprüchen zu anderen Dokumenten gilt diese Datei.

## Hardware
| Komponente | Anschluss | Status |
|---|---|---|
| Arduino Uno R3 | USB, COM9 | vorhanden, Bestandsfirmware unbekannt |
| Display ST7735R 160×128 (Joy-IT RB-TFT1.8-T) | CS D10, DC D9, RST D8, MOSI D11, SCK D13 | wie GloveboxControl, am Aufbau zu verifizieren |
| Touch XPT2046 | T_CS D4, T_IRQ D2, MISO D12 | wie GloveboxControl, zu verifizieren |
| BME680 | I2C: SDA A4, SCL A5, Adresse 0x76 oder 0x77 | zu verifizieren (Modul, Pegel, Adresse) |
| Piezo (optional) | D5 | offen |

## Datenmodell
offen (Messwerte als Ganzzahlen: 0,01 °C · 0,01 %rF · 0,1 hPa · Ω; Messintervall; Schwellwerte; Einheiten)

## Anzeige
offen (Seiten: Übersicht, Detail/Verlauf, Einstellungen; 160×128, CP437)

## Eingabe
offen (Touch: Tippen; Seitenwechsel, Einstellungen)

## Serielles Protokoll
offen — wird in PROJ-2 festgelegt. Entwurf und Regeln: `.claude/rules/protocol.md`.

## EEPROM
offen — Historie in `docs/eeprom-layout-history.md`.
