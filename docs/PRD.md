# Product Requirements Document

## Vision
Ein kleines, autarkes Gerät zeigt jederzeit **Temperatur, Luftfeuchte, Luftdruck und den
Luftqualität-Trend** (BME680) auf einen Blick. Ein optionales PC-Tool liest die Werte aus,
konfiguriert das Gerät und schreibt ein CSV-Messprotokoll. Technische Details: `docs/SPEC.md`.

## Target Users
- **Personen am Gerät:** lesen die Werte ab und bedienen es per Touch.
- **Auswertende am PC:** nutzen das Messprotokoll, ändern Messintervall und Schwellwerte.

Schmerzpunkt: Raumklimawerte sind heute nicht auf einen Blick sichtbar und werden nicht aufgezeichnet.

## Core Features (Roadmap)

| Priority | Feature | Status |
|----------|---------|--------|
| P0 | PROJ-1 Bestandsgerät analysieren und dokumentieren | Roadmap |
| P0 (MVP) | PROJ-2 Firmware-Grundgerüst: Display, Touch, BME680, Übersichtsseite | Roadmap |
| P0 (MVP) | PROJ-3 Serielles Protokoll (Firmware + PC-Client + Tests) | Roadmap |
| P0 (MVP) | PROJ-4 PC-Tool CLI/GUI mit `monitor` | Roadmap |
| P0 (MVP) | PROJ-5 Messprotokoll (CSV) | Roadmap |
| P1 | PROJ-6 Schwellwerte, Alarm, Einstellungen im EEPROM | Roadmap |
| P2 | PROJ-7 Verlauf/Trend auf dem Gerät | Roadmap |

Neue Features: siehe `features/INDEX.md`.

## Success Metrics
- Alle vier Werte sind am Gerät in < 2 s ablesbar, ohne Flackern oder Reste von Ziffern
- Gerät läuft wochenlang ohne Reset
- Werte plausibel (−20…60 °C, 0…100 %rF, 800…1100 hPa); fehlender Sensor ist sichtbar, nie „0"
- CSV-Protokoll lückenlos bei laufendem PC-Tool

## Constraints
- **Hardware:** Arduino Uno R3 (2 KB RAM, 32 KB Flash, 1 KB EEPROM) an COM9, Joy-IT RB-TFT1.8-T
  (ST7735R 160×128, XPT2046-Touch, Pegelwandler), BME680 per I2C
- **Bestandsgerät:** läuft bereits unbekannte Firmware; erst analysieren, nie blind überschreiben
- **Sensor:** kein BSEC auf AVR → nur Gaswiderstand und Trend, kein IAQ-Index; Selbsterwärmung
  erfordert Temperatur-Offset
- **Bibliothek:** BME680-Treiber (Bibliothek oder eigener) ist Architekturentscheidung (Flash)
- **Autarkie:** Anzeige und Grundeinstellungen am Gerät ohne PC; Protokoll und Feinkonfiguration am PC
- **Zeit:** keine Echtzeituhr; Zeitstempel kommen vom PC
- **PC-Tool:** Windows 10/11, Python ≥ 3.11, einzige Abhängigkeit `pyserial`
- **Datenablage:** CSV lokal (`~/umwelt_messwerte.csv`), keine Personendaten, keine automatische
  Löschung; Aufbewahrung entscheidet der Nutzer
- **Design system:** keins — große, kontrastreiche Werte auf dem Gerät; am PC nativer Tk-Stil

## Non-Goals
- Keine Netzwerk-/Cloud-/MQTT-Anbindung, kein Dashboard über mehrere Sensorknoten
- Keine Steuerung von Lüftung/Heizung
- Kein BSEC/IAQ-Index
- Keine dauerhafte Messhistorie auf dem Gerät (EEPROM-Verschleiß)

---

Use `/write-spec` to create detailed feature specifications for items on the roadmap.
