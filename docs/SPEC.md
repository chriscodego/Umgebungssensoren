# SPEC — der Vertrag

> Verbindlich für Firmware (`firmware/Umgebungssensoren/`), PC-Tool (`pc/src/umwelt_ctl/`) und Tests.
> Änderungen am Draht-Format nur gemeinsam (siehe `.claude/rules/protocol.md`). Stand: 2026-10-02, Protokollversion 1.

## Hardware
| Komponente | Anschluss |
|---|---|
| Arduino Uno R3 | USB, COM9 (VID 0x2341 / PID 0x0043) |
| Display ST7735R 160×128 (Joy-IT RB-TFT1.8-T) | CS D10, DC D9, RST D8, MOSI D11, SCK D13; Rotation 1 |
| Touch XPT2046 | T_CS D4, T_IRQ D2, MISO D12 (gemeinsamer SPI-Bus) |
| BME680 | I2C: SDA A4, SCL A5, Adresse 0x76, sonst 0x77 (beim Start geprüft) |
| Piezo (optional) | D5 (eigener Timer2-Treiber) |

Entscheidungen (2026-10-02, autonom getroffen, Nutzer: „alles alleine erledigen"):
- BME680: **eigener Minimaltreiber** (Ganzzahl-Kompensation nach Bosch BME68x), keine Bibliothek — spart Flash, kein `float`.
- Bestandsfirmware (zeigte Temperatur/Luftdruck/Feuchtigkeit, „BME680 Messfehler") wurde vor dem Überschreiben
  gesichert: `docs/backup/bestandsfirmware_flash.hex` und `…_eeprom.hex` (Wiederherstellung: avrdude `-U flash:w:…:i`).

## Messwerte (Ganzzahlen, auf dem Gerät und auf dem Draht)
| Größe | Einheit/Skala | Typ | Beispiel |
|---|---|---|---|
| Temperatur `t` | 0,01 °C | int16 | `2134` = 21,34 °C |
| Feuchte `rh` | 0,01 %rF | uint16 | `4512` = 45,12 % |
| Druck `p` | 0,1 hPa | uint16 | `10132` = 1013,2 hPa |
| Gaswiderstand `gas` | Ω | uint32 | `85000` |
Ungültig/nicht vorhanden → `-` (nie `0`). Luftqualität: nur Gaswiderstand und Trend, kein IAQ-Index.
Plausibilitätsbereich (sonst ungültig): t −4000…8500, rh 0…10000, p 3000…11000, gas > 0.

## Messung
Messintervall `INTERVAL` 1…3600 s, Standard 10 s. Messung als nicht blockierende Zustandsmaschine (Forced Mode,
Gasheizer 320 °C / 150 ms). Temperatur-Offset `TEMP_OFFSET` (0,01 °C, −5000…5000, Standard 0) wird auf `t` angewandt.
Sensor-Zustand: `OK`, `MISSING` (nicht gefunden / I2C-Fehler), `ERROR` (Messung ungültig). Bei `MISSING` werden
alle Werte `-`; Wiederholversuch alle 5 s.

## Alarm
Schwellwerte (`CFG`): `T_HI`, `T_LO` (0,01 °C), `RH_HI`, `RH_LO` (0,01 %), je `OFF` (Standard) oder Zahl.
Hysterese: Alarm setzt bei Überschreitung in 2 aufeinanderfolgenden Messungen, löscht bei Rückkehr um
2 % des Wertebereichs (T: 0,5 °C, RH: 2 %) innerhalb der Grenze. Flags (Bitmaske): 1 `T_HI`, 2 `T_LO`, 4 `RH_HI`,
8 `RH_LO`, 16 `SENSOR` (Sensor MISSING/ERROR). Aktiver, nicht quittierter Alarm: Anzeige rot blinkend + Text
(nicht nur Farbe), Piezo wenn `BUZZER 1`. `ACK` bzw. Antippen quittiert (Anzeige/Ton aus, Flag bleibt, solange die
Ursache besteht). „Keine Daten" gilt als Alarm 16, nie als „alles gut".

## Anzeige (160×128, CP437, echte Umlaute, `°` = 0xF8)
Seiten, Wechsel per Antippen der Seitenleiste unten (Ziele ≥ 24 px):
1. **Übersicht:** vier Werte groß (Temperatur °C, Feuchte %, Druck hPa, Gas kΩ mit Trendpfeil), Statuszeile (Uhrzeit
   `HH:MM` wenn gestellt, „PC"-Symbol 5 s nach letztem Kommando, Sensorstatus). Ungültig: `--`.
2. **Einstellungen:** Messintervall (+/−, Stufen 1·2·5·10·30·60 s), Piezo an/aus, „Kalibrieren" (Touch), „Standard".
3. (optional, nur wenn Flash reicht, PROJ-7) **Verlauf:** Min/Max seit Start, Temperaturverlauf Mini-Graph.
Nur geänderte Felder neu zeichnen, Ziffernreste vermeiden (feste Feldbreite), kein `fillScreen()` in `loop()`.

## Eingabe (Touch)
Eigener XPT2046-Treiber (Antippen). Kalibrierung: beim Einschalten Display berührt halten oder Einstellungen →
„Kalibrieren"; vier Kreuze. Defaults (am Modul gemessen, wie GloveboxControl): X links→rechts, Y invertiert, kein Swap,
bis kalibriert.

## EEPROM (Layout 1)
Adresse 0: Magic `0x554D5753` ("UMWS"), Layout-Version `1`, Config {interval, temp_offset, t_hi, t_lo, rh_hi, rh_lo,
buzzer} + CRC-8; danach Touch-Kalibrierung mit eigenem CRC-8. Bei ungültigem Magic/Version/CRC/Bereich: Defaults.
Schreiben nur bei Änderung. Messwerte/Verlauf nie im EEPROM. Historie: `docs/eeprom-layout-history.md`.

## Serielles Protokoll (Version 1)
115200 8N1, ASCII, Zeilenende `\n`, `\r` ignoriert, max. 80 Byte je Zeile (länger → bis `\n` verwerfen, `ERR 2`).
Befehle case-insensitiv, Argumente durch Leerzeichen getrennt, leere Zeilen ignoriert. Jede Antwort beginnt mit
`OK` oder `ERR <code> <text>`; Listen enden mit `END`. `EVT …`-Zeilen können jederzeit, auch zwischen Antwortzeilen
einer Liste, auftreten. Öffnen des Ports (DTR/RTS aus) resettet den Uno nicht; ein Upload schon (→ `EVT BOOT`).

### Befehle
| Befehl | Antwort | Fehler |
|---|---|---|
| `PING` | `OK PONG Umgebungssensoren <fw>` | — |
| `STATUS` | `OK <sensor> <interval> <uptimeSec> <alarmFlags> <unackedFlags>` (`sensor` = `OK`/`MISSING`/`ERROR`) | — |
| `READ` | `OK <t> <rh> <p> <gas> <ageSec>` (je Wert Zahl oder `-`; `ageSec` = Alter der Messung, `-` wenn noch keine) | `ERR 5` wenn Sensor `MISSING` |
| `CFG` | Liste `C <key> <value>` je Schlüssel (`INTERVAL`, `TEMP_OFFSET`, `T_HI`, `T_LO`, `RH_HI`, `RH_LO`, `BUZZER`), dann `END` | — |
| `CFG <key> <value>` | `OK` (sofort wirksam, im EEPROM gespeichert; `OFF` nur für Schwellwerte) | `ERR 3` unbekannter Schlüssel/Wert außerhalb des Bereichs, `ERR 2` nicht numerisch/Argumentzahl |
| `CFG RESET` | `OK` (Config auf Defaults, Touch-Kalibrierung bleibt) | — |
| `STREAM <0\|1>` | `OK` (1 = nach jeder Messung `EVT DATA`; nach Reset 0) | `ERR 2` |
| `ACK` | `OK` | `ERR 7` wenn kein unquittierter Alarm |
| `TIME` | `OK <hh:mm:ss>` oder `OK --:--:--` | — |
| `TIME <hh:mm:ss>` | `OK` (zwei Ziffern je Feld, hh 00–23, mm/ss 00–59; nur RAM) | `ERR 2` |

Bereiche: `INTERVAL` 1…3600; `TEMP_OFFSET` −5000…5000; `T_HI`/`T_LO` −4000…8500; `RH_HI`/`RH_LO` 0…10000; `BUZZER` 0|1.
Standard: INTERVAL 10, TEMP_OFFSET 0, Schwellwerte OFF, BUZZER 0.

### Events
`EVT BOOT <fw>` (≈ 2–3 s nach Reset) · `EVT DATA <t> <rh> <p> <gas>` (nur bei `STREAM 1`, nach jeder abgeschlossenen
Messung, ungültige Werte `-`) · `EVT ALARM <flag> <0|1>` (Flag-Wert 1/2/4/8/16; 1 = aktiv, 0 = beendet) ·
`EVT SENSOR <OK|MISSING|ERROR>` (bei Zustandswechsel).

### Fehlercodes
1 unbekannter Befehl/Unterbefehl · 2 falsche Argumente/Format/zu lange Zeile · 3 Wert außerhalb des Bereichs bzw.
unbekannter Schlüssel · 5 Sensor nicht verfügbar · 7 falscher Zustand. (4 und 6 reserviert/unbenutzt.) Nur der Code
zählt, der Text ist frei.

### Diagnose (nicht Teil des stabilen Vertrags)
`DEBUG TOUCH <0|1>` (roher Touch als `EVT TOUCH x y`), `TESTPATTERN`, `CAL SHOW`. Format kann sich ändern; nach Reset aus.

## PC-Tool (Entwurf der Oberfläche)
CLI `umwelt`: `ping`, `status`, `ports`, `read`, `config [key [value]]`, `config reset`, `ack`, `time [sync]`,
`monitor [--csv DATEI] [--interval S]`, `gui`. Messprotokoll-CSV (Standard `~/umwelt_messwerte.csv`, `;`, UTF-8 mit BOM,
Kopfzeile): `zeit;temperatur_c;feuchte_proz;druck_hpa;gas_ohm;alarm` — Zeit ISO 8601 mit Offset, physikalische Einheiten
mit Dezimalkomma, ungültige Werte leer.
