# Feature Index

> Central tracking for all features. Updated by skills automatically.

## Status Legend
- **Roadmap** - `/init` done, feature identified in the feature map, no spec file yet
- **Planned** - `/write-spec` done, full spec written, architecture not yet designed
- **Architected** - `/architecture` done, tech design approved, ready to build
- **In Progress** - `/firmware` or `/pc` active or completed, not yet in QA
- **In Review** - `/qa` active, testing in progress
- **Approved** - `/qa` passed, no critical/high bugs, ready to ship
- **Released** - `/release` done, flashed on the device and PC tool installed

## Released (Archived)

Noch keine Features ausgeliefert.

## Active Features

| ID | Feature | Beschreibung | Prio | Abhängigkeiten | Status | Spec | Created |
|----|---------|--------------|------|----------------|--------|------|---------|
| PROJ-1 | Bestandsgerät analysieren | Ausgabe der vorhandenen Firmware auf COM9 beobachten, Quelle/Flash-Backup klären, Befund ins Handbuch | P0 | — | Released | [PROJ-1](PROJ-1-bestandsgeraet.md) | 2026-10-02 |
| PROJ-2 | Firmware-Grundgerüst | Pins/config.h, Display, Touch (eigener XPT2046-Treiber, Kalibrierung), BME680 nicht blockierend, Übersichtsseite mit vier Werten, Sensor-fehlt-Zustand | P0 | PROJ-1 | Released | [PROJ-2](PROJ-2-firmware-grundgeruest.md) | 2026-10-02 |
| PROJ-3 | Serielles Protokoll | Zeilenbasiertes Protokoll (PING, STATUS, READ, TIME, EVT DATA/BOOT), Fehlercodes, Firmware + PC-Client + Vertragstests | P0 | PROJ-2 | Released | [PROJ-3](PROJ-3-serielles-protokoll.md) | 2026-10-02 |
| PROJ-4 | PC-Tool CLI/GUI | Paket `umwelt_ctl`: Port-Erkennung, CLI, `monitor`, Tkinter-GUI mit Live-Werten | P0 | PROJ-3 | Released | [PROJ-4](PROJ-4-pc-tool-cli-gui.md) | 2026-10-02 |
| PROJ-5 | Messprotokoll (CSV) | CSV mit PC-Zeitstempel (`monitor --csv`, GUI), Standard `~/umwelt_messwerte.csv` | P0 | PROJ-4 | Released | [PROJ-5](PROJ-5-messprotokoll-csv.md) | 2026-10-02 |
| PROJ-6 | Schwellwerte, Alarm, Einstellungen | Messintervall/Schwellwerte/Einheiten im EEPROM, Alarm mit Hysterese (Farbe, optional Piezo), Konfiguration am Gerät und PC, Reset auf Defaults | P1 | PROJ-3, PROJ-4 | Released | [PROJ-6](PROJ-6-schwellwerte-alarm-einstellungen.md) | 2026-10-02 |
| PROJ-7 | Verlauf auf dem Gerät | Kurzer RAM-Verlauf/Trend-Anzeige (nur wenn RAM/Flash reichen) | P2 | PROJ-2 | ersetzt durch PROJ-10 | — | 2026-10-02 |
| PROJ-8 | Control Panel (PySide6) | Desktop-Panel: Live-Kacheln + Sparklines, Verbindungs-/Alarmbanner, Einstellungen, dauerhaftes SQLite-Log, Verlauf, CSV-Export | P0 | PROJ-4, PROJ-5 | Released | [PROJ-8](PROJ-8-control-panel.md) | 2026-10-02 |
| PROJ-9 | Installer + Updater (Control Panel) | Windows-Installer (PyInstaller + Inno Setup, pro Benutzer) und Update-Suche im NAS-Ordner `05_Software\Umgebungssensoren` (latest.json, SHA-256), analog RFB | P1 | PROJ-8 | Released | [PROJ-9](PROJ-9-installer-updater.md) | 2026-10-02 |
| PROJ-10 | Live-Verlaufsdiagramm auf dem Gerät | Seite „Verlauf": RAM-Ringpuffer (64 Punkte à 30 s) je Messwert, Liniendiagramm mit Min/Max, Kacheltipp öffnet, Diagrammtipp wechselt den Wert; keine Protokolländerung (ersetzt PROJ-7) | P2 | PROJ-2 | Released | [PROJ-10](PROJ-10-live-diagramm-geraet.md) | 2026-10-02 |

<!-- Add features above this line -->

## Empfohlene Baureihenfolge

1. **P0:** PROJ-1 → PROJ-2 → PROJ-3 → PROJ-4 → PROJ-5 (MVP)
2. **P1:** PROJ-6 Schwellwerte/Alarm
3. **P2:** PROJ-7 nur bei verbleibendem Speicher
4. Offene Entscheidungen: BME680-Bibliothek vs. eigener Treiber (in `/architecture` PROJ-2),
   Pegel/Adresse des BME680-Moduls (Hardware prüfen)

## Next Available ID: PROJ-11
