# Product Requirements Document

> _Describe what you are building_ — Platzhalter: dieses PRD ist **noch nicht ausgefüllt**.
> Führe `/init` aus; der Skill interviewt dich und ersetzt diese Datei.

## Bereits bekannte Randbedingungen (Input für `/init`)
- **Hardware:** Arduino Uno R3 (2 KB RAM, 32 KB Flash, 1 KB EEPROM) an COM9, Joy-IT RB-TFT1.8-T
  (ST7735R 160×128 + XPT2046-Touch), Sensor **BME680** (I2C)
- **Bestandsgerät:** Auf dem Arduino läuft bereits eine Firmware (Inhalt unbekannt) → analysieren,
  nicht blind überschreiben
- **Anzeige:** Temperatur, relative Luftfeuchte, Luftdruck, Gaswiderstand (Luftqualität nur als Trend,
  kein BSEC auf AVR)
- **PC-Tool:** Python ≥ 3.11 + pyserial, CLI, `monitor` mit CSV-Messprotokoll, Tkinter-GUI —
  Serial-Protokoll als Vertrag (`docs/SPEC.md`)
- **Referenzprojekt:** GloveboxControl (gleiche Hardware-Basis, gleicher Workflow)

## Vision
_offen_

## Target Users
_offen_

## Core Features (Roadmap)
_offen — Vorschlag siehe `features/INDEX.md`_

## Success Metrics
_offen_

## Constraints
_offen_

## Non-Goals
_offen_
