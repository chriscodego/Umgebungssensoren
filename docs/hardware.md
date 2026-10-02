# Hardware & Verdrahtung

> Ergänzt `docs/SPEC.md`. Bei Widersprüchen gilt SPEC.md; Pins im Code stehen nur in `config.h`.

## Komponenten
| Komponente | Details |
|---|---|
| Arduino Uno R3 | ATmega328P, 5 V, USB VID 2341 / PID 0043, aktuell COM9 |
| Display | Joy-IT RB-TFT1.8-T, ST7735R, SPI, 3,3 V Versorgung und Logik → Pegelwandler (z. B. 74HC4050) Pflicht |
| Touch | XPT2046, resistiv, SPI |
| Sensor | **BME680** (Temperatur, Feuchte, Druck, Gas), I2C 0x76/0x77 |

## Zu klären (BME680)
- Welches Breakout? (Adafruit/Pimoroni/China-Modul) → eigener Regler und Pegelwandler vorhanden? Ein
  nacktes 3,3-V-Modul darf nicht an die 5-V-I2C-Leitungen des Uno
- Adresse (SDO-Pin), Pull-ups vorhanden?
- Selbsterwärmung: Platzierung weg von Display/Regler, Temperatur-Offset später kalibrieren

## Fehlersuche
| Symptom | Mögliche Ursache |
|---|---|
| Sensor nicht gefunden | Adresse 0x76/0x77, SDA/SCL vertauscht, fehlende Versorgung |
| Temperatur zu hoch | Selbsterwärmung (Gasheizer, Display, Regler) |
| Gaswert driftet | Burn-in-Phase des Sensors (Stunden bis Tage) |
| Upload „Access is denied" | COM9 von Monitor/GUI/IDE belegt |
| Zufällige Resets | RAM-Mangel (Build-Ausgabe prüfen) oder Versorgung |
| Weißes Display / falsche Farben | Verdrahtung CS/DC/RST bzw. falsche `initR`-Variante |
