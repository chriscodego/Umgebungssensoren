# Entwicklerhandbuch — Umgebungssensoren

> Stand: 2026-10-02 · Verbindlich laut `.claude/rules/developer-handbook.md`. Vertrag: `docs/SPEC.md`.

## 1. Vision & Leitplanken
Autarke, robuste Umgebungsdaten-Anzeige (BME680 → Touch-Display); der PC ist Zusatz, nie Voraussetzung.
Kein Web, kein Server, keine Cloud. Ausführlich: `docs/PRD.md` (nach `/init`).

## 2. Projektstruktur & Architektur
Siehe `CLAUDE.md` (Abschnitt „Project Structure") und `.claude/rules/general.md`.
Firmware-Module (`firmware/Umgebungssensoren/`, FW 0.1.0):

| Modul | Aufgabe |
|---|---|
| `config.h` | alle Pins, I2C-Adressen, Grenzen, Timings, `FW_VERSION` |
| `sensor` | einziger I2C-Nutzer: eigener gepollter TWI-Master + BME680-Treiber (Bosch-Ganzzahlkompensation), Zustandsmaschine Probe → Reset → Konfig → Trigger → Warten → Lesen |
| `storage` | EEPROM Layout 1 (Config + Touch-Kalibrierung, je CRC-8), Bereichsprüfung |
| `input` | XPT2046-Treiber (aus GloveboxControl), Entprellung, Kalibrierung |
| `display` | Grafik-Primitive, Übersichtsseite mit Dirty-Tracking (max. eine Kachel je Durchlauf) |
| `ui` | Seiten Übersicht / Einstellung / Kalibrierung, Seitenleiste, Hit-Tests aus denselben PROGMEM-Tabellen |
| `protocol` | Zeilenparser, Antworten, Events, RAM-Uhr (`TIME`), Uptime |
| `signal` | Alarm-Flags mit Hysterese, Quittierung, Piezo (Timer2) |

## 3. Konventionen
Siehe `.claude/rules/` (general, firmware, protocol, pc, security, code-integrity).
- I2C nur über den eigenen TWI-Master in `sensor.cpp` (kein `Wire`); jede Wartezeit begrenzt (`I2C_SPIN_MAX`).
- Boot schreibt nie ins EEPROM; geschrieben wird nur bei einer Einstellungsänderung (update-Semantik).

## 4. Bestandsgerät (COM9)
Befund 2026-10-02 (PROJ-1):
- [x] Ausgabe beobachtet (Port nur lesend, DTR/RTS aus): **9600 Baud**, CSV-Zeilen `24.22,53.59,1013.91`
  (Temperatur °C, Feuchte %, Druck hPa) etwa alle 4 s; im Flash außerdem Kopfzeile
  `temperatur_c,feuchte_prozent,druck_hpa` und Texte „Temperatur“, „Feuchtigkeit“, „Luftdruck“,
  „BME680 Messfehler“, „BME680 Fehler“, „BME680 -> PC“. Nutzt `float`-Ausgabe (vermutlich Adafruit-BME680-Bibliothek).
- [x] BME680 ist angeschlossen und liefert plausible Werte. Die Bestandsfirmware probiert `begin(0x76)`, dann
  `begin(0x77)` (Disassembly) — welche Adresse antwortet, zeigt erst die neue Firmware.
- [x] Flash-Sicherung: `docs/backup/bestandsfirmware_flash.hex` (Anwendung 29 000 B + Bootloader).
- [ ] **EEPROM-Sicherung ungültig:** `bestandsfirmware_eeprom.hex` ist byte-gleich mit den ersten 1024 B des Flash
  (Optiboot liefert beim EEPROM-Lesen Flash). Die neue Firmware schreibt das EEPROM erst bei der ersten Einstellungsänderung.
- [ ] Originalquelle beim Nutzer erfragen (offen)
- [ ] Überschreiben: Freigabe des Nutzers selbst steht aus (Upload noch nicht erfolgt)

## 5. Bekannte Fallstricke
- `arduino-cli.exe` liegt in `C:\Program Files\Arduino CLI\`, nicht im PATH
- Projekt liegt in OneDrive: Build-Ordner können gesperrt sein → Kompilieren bei Sperrfehler wiederholen
- Übernommen aus GloveboxControl: Port öffnen resettet den Uno nicht (DTR/RTS aus), ein Upload schon;
  SPI-Bus teilen sich Display und Touch; kein `%f` auf AVR; nie `fillScreen()` in `loop()`
- Optiboot (Uno) kann das EEPROM nicht per avrdude auslesen — eine „EEPROM-Sicherung“ enthält dann Flash-Bytes
- Adafruit GFX bindet über BusIO `Wire.h` ein: der TWI-ISR der Wire-Bibliothek (~0,8 KB) wird immer gelinkt
- Bezeichner `u16` ist in den AVR/Arduino-Headern ein Typ — eigene Funktionen nicht so nennen
- Bosch-Feuchtekompensation (int32) läuft bei gesättigten Rohwerten (> 100 %rF) über → vorher abfangen (in `sensor.cpp` umgesetzt)

## 6. Speicherbudget
| Stand | Flash | RAM (global) |
|---|---|---|
| FW 0.1.0 (PROJ-2/3/6), 2026-10-02 | 31 506 B (97,7 %) | 806 B (39 %) |
Mit `Wire` lag der Build bei 32 524 B (> 100 %). > 95 % ist ein Architekturthema: PROJ-7 nur mit Einsparungen.

## 7. EEPROM
Layout 1 (29 B ab Adresse 0): siehe `storage.cpp` und `docs/eeprom-layout-history.md`. Schwellwert „OFF“ = −32768.

## 8. Auslegung von SPEC-Lücken (Firmware 0.1.0, zur Bestätigung)
- `CFG <Schlüssel ohne OFF> OFF` → `ERR 2` (nicht numerisch); `CFG <unbekannt>` → `ERR 3`; `CFG <bekannt>` ohne Wert → `ERR 2`
- `T_LO ≥ T_HI` bzw. `RH_LO ≥ RH_HI` (beide gesetzt) → `ERR 3`
- Sensor `ERROR` = T, RH oder P ungültig bzw. keine Daten nach 1 s; nur Gas ungültig (Heizer nicht stabil) → Gas `-`, Zustand `OK`
- `READ` bei `ERROR` → `OK` mit `-`; `EVT DATA` auch nach einer ungültigen Messung
- Schwellwert-Flags bleiben bei fehlendem Sensor stehen; nur Flag 16 wechselt. Setzen nach 2 Messungen, Löschen nach 1 Messung im Hysteresebereich
- Gerätseitige Einstellungsänderungen erzeugen kein Event (SPEC hat keins)
- Anzeige: Uhr zeigt `--:--`, solange nicht gestellt; Druck mit 1 Nachkommastelle, Temperatur/Feuchte auf 0,1 gerundet;
  Gas-Trendpfeil gegen gleitenden Mittelwert (Gewicht 1/8, ±5 %); Seitenleiste „Übersicht“ | „Einstellung“
- Diagnose: `EVT TOUCH <rawX> <rawY> <z> <x> <y>`, `OK CAL <l> <r> <t> <b> <swap> <user>`

## 9. Entwicklungschronik
| Datum | PROJ | Änderung |
|---|---|---|
| 2026-10-02 | Chore | Projektgerüst aus GloveboxControl übernommen und auf Umgebungssensoren (BME680) angepasst: Rules, Agents, Skills, Doku-Skelett |
| 2026-10-02 | PROJ-1 | Bestandsgerät analysiert (9600-Baud-CSV, BME680 funktioniert, EEPROM-Sicherung ungültig) |
| 2026-10-02 | PROJ-2/3/6 | Firmware 0.1.0: eigener BME680-/TWI-Treiber, Übersicht + Einstellungsseite, Protokoll v1, Alarm/Piezo, EEPROM Layout 1; noch nicht geflasht |
| 2026-10-02 | PROJ-4/5 | PC-Tool umwelt_ctl (CLI, monitor, GUI, Fake-Device-Tests) und CSV-Messprotokoll |
