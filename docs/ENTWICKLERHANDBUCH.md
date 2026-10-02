# Entwicklerhandbuch — Umgebungssensoren

> Stand: 2026-10-02 · Verbindlich laut `.claude/rules/developer-handbook.md`. Vertrag: `docs/SPEC.md`.

## 1. Vision & Leitplanken
Autarke, robuste Umgebungsdaten-Anzeige (BME680 → Touch-Display); der PC ist Zusatz, nie Voraussetzung.
Kein Web, kein Server, keine Cloud. Ausführlich: `docs/PRD.md` (nach `/init`).

## 2. Projektstruktur & Architektur
Siehe `CLAUDE.md` (Abschnitt „Project Structure") und `.claude/rules/general.md`.

## 3. Konventionen
Siehe `.claude/rules/` (general, firmware, protocol, pc, security, code-integrity).

## 4. Bestandsgerät (COM9)
Auf dem Arduino läuft bereits eine Firmware, die nicht dokumentiert ist.
- [ ] Ausgabe des Geräts beobachten (Port nur lesend, DTR/RTS aus)
- [ ] Originalquelle beim Nutzer erfragen
- [ ] Entscheiden: Flash-Backup per avrdude vor dem ersten Upload ja/nein
- [ ] Befund hier eintragen

## 5. Bekannte Fallstricke
- `arduino-cli.exe` liegt in `C:\Program Files\Arduino CLI\`, nicht im PATH
- Projekt liegt in OneDrive: Build-Ordner können gesperrt sein → Kompilieren bei Sperrfehler wiederholen
- Übernommen aus GloveboxControl: Port öffnen resettet den Uno nicht (DTR/RTS aus), ein Upload schon;
  SPI-Bus teilen sich Display und Touch; kein `%f` auf AVR; nie `fillScreen()` in `loop()`

## 6. Entwicklungschronik
| Datum | PROJ | Änderung |
|---|---|---|
| 2026-10-02 | Chore | Projektgerüst aus GloveboxControl übernommen und auf Umgebungssensoren (BME680) angepasst: Rules, Agents, Skills, Doku-Skelett |
