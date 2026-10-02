# Konfiguration

| Was | Wert |
|---|---|
| Serieller Port | `--port COM9` > Umgebungsvariable `UMWELT_PORT=COM9` > automatisch (USB-VID 0x2341) |
| Verbinden | DTR/RTS aus — das Öffnen des Ports startet den Uno nicht neu |
| Messprotokoll (CSV) | Standard `~/umwelt_messwerte.csv` (außerhalb des Repos, lokal; Aufbewahrung entscheidet der Nutzer) |
| Control Panel: Messwert-Datenbank | Standard `%LOCALAPPDATA%\Umgebungssensoren\messwerte.db` (platformdirs `user_data_dir`, lokal, nicht im Repo); anders mit `umwelt-panel --db DATEI` |
| Control Panel: Logdatei | `%LOCALAPPDATA%\Umgebungssensoren\Logs\panel.log` (rotierend, 3 × 1 MB) |
| Control Panel: Update-Ordner | `\\131.234.237.14\Gutmann\01_Interna\05_Software\Umgebungssensoren`, sonst jedes Netzlaufwerk + `01_Interna\05_Software\Umgebungssensoren`; vorrangig Umgebungsvariable `UMWELT_UPDATE_DIR` (siehe unten) |
| Control Panel: Installation | `%LOCALAPPDATA%\Programs\Umgebungssensoren Control Panel\` (Installer, siehe [installation.md](installation.md)) |
| arduino-cli | `C:\Program Files\Arduino CLI\arduino-cli.exe` (nicht im PATH) |

## PC-Tool (`umwelt`)
`ping`, `status`, `ports`, `read`, `config [SCHLÜSSEL [WERT]]`, `config reset [-y]`, `ack`, `time [sync]`,
`monitor [--csv [DATEI]] [--interval S]`, `gui`. Exit-Code 0 = ok, 1 = Gerätefehler/Zeitüberschreitung,
2 = keine Verbindung/falsche Argumente.

`config`-Werte werden in physikalischen Einheiten eingegeben (Komma oder Punkt), das Tool rechnet in die
Ganzzahlen der SPEC um:

| Schlüssel | Eingabe | Bereich | Standard |
|---|---|---|---|
| `INTERVAL` | Sekunden | 1 … 3600 | 10 |
| `TEMP_OFFSET` | °C | −50 … 50 | 0 |
| `T_HI`, `T_LO` | °C oder `OFF` | −40 … 85 | OFF |
| `RH_HI`, `RH_LO` | % oder `OFF` | 0 … 100 | OFF |
| `BUZZER` | `0`/`1` bzw. `aus`/`an` | — | 0 |

`monitor` ohne `--interval` schaltet `STREAM 1` ein (eine Zeile je Messung des Geräts) und am Ende wieder aus;
mit `--interval S` fragt er alle S Sekunden per `READ` ab (das Gerät behält sein Messintervall).

## Messprotokoll (CSV)
- Trennzeichen `;`, UTF-8 mit BOM, Kopfzeile nur bei neuer/leerer Datei, sonst wird angehängt
- Spalten: `zeit;temperatur_c;feuchte_proz;druck_hpa;gas_ohm;alarm`
- `zeit`: PC-Zeit, ISO 8601 mit Offset (`2026-10-02T14:03:12+02:00`)
- Werte in °C, % rF, hPa mit Dezimalkomma; Gaswiderstand in Ω als Ganzzahl; ungültig/fehlend → leer (nie 0)
- `alarm`: Alarm-Bitmaske laut SPEC (1 T_HI, 2 T_LO, 4 RH_HI, 8 RH_LO, 16 Sensor/keine Daten; 0 = kein Alarm,
  leer = unbekannt)
- Jede Zeile wird sofort geschrieben; ist die Datei gesperrt (z. B. in Excel geöffnet), warten die Zeilen und
  werden mit der nächsten Zeile nachgetragen
- Die Datei wächst unbegrenzt; Löschen/Archivieren entscheidet der Nutzer. Nie ins Repository legen
  (`.gitignore`: `*messwerte*.csv`)

## Control Panel (`umwelt-panel`, PROJ-8)
Installation: `pip install -e "pc[panel]"` (PySide6, platformdirs). Start: `umwelt-panel` oder
`python -m umwelt_panel`; Optionen `--port PORT` (sonst `UMWELT_PORT`, sonst automatisch) und `--db DATEI`.

- **Datenbank (SQLite):** Tabelle `measurements(ts_utc, t, rh, p, gas, alarm)` — `ts_utc` = PC-Zeit als
  Unix-Millisekunden (UTC), Werte als Ganzzahlen der SPEC (0,01 °C, 0,01 %rF, 0,1 hPa, Ω), ungültig = NULL;
  Tabelle `settings` (automatisch aufzeichnen, Port, Ansicht, Fenstergröße). Schema-Version in
  `PRAGMA user_version` (aktuell 1); eine Datei einer neueren Version wird abgelehnt, nicht verändert.
- **Aufzeichnung:** standardmäßig an („Messwerte automatisch aufzeichnen"), jede `EVT DATA`-Messung wird
  gespeichert, solange das Gerät verbunden ist. Anzahl, Größe und Pfad stehen unten im Fenster.
- **Löschen:** nur über „Verlauf → Log löschen …" mit Rückfrage. Keine automatische Aufbewahrungsfrist.
- **CSV-Export:** „Verlauf → CSV exportieren …" (oder Strg+E) für den gewählten Zeitraum (letzte Stunde,
  24 Stunden, 7 Tage, alles); Format identisch zum Messprotokoll oben (`;`, UTF-8 mit BOM, Kopfzeile,
  Dezimalkomma, Zeit ISO 8601 mit Offset, ungültig leer). Standardordner: Dokumente.

## Update-Ordner (PROJ-9)
Das Control Panel liest — schreibt nie — einen Ordner auf dem Institutslaufwerk: `latest.json` plus die Installer
`UmgebungssensorenPanel-Setup-<Version>.exe` (ältere bleiben als Rückweg liegen). Suchreihenfolge, der erste Ordner
mit gültiger `latest.json` gewinnt:

1. Umgebungsvariable **`UMWELT_UPDATE_DIR`** (z. B. `set UMWELT_UPDATE_DIR=D:\Test\Updates` für Tests oder
   Sonderfälle)
2. UNC-Pfad `\\131.234.237.14\Gutmann\01_Interna\05_Software\Umgebungssensoren` (ohne Laufwerksbuchstaben)
3. jeder verbundene **Netz**laufwerksbuchstabe + `01_Interna\05_Software\Umgebungssensoren`

Jede Probe hat ein Zeitlimit von 5 s und läuft im Hintergrund; ein getrenntes Laufwerk blockiert das Panel nicht.
Kein Zugangsdatum wird gespeichert — die Freigabe wird mit der Windows-Anmeldung erreicht. Kein Internetzugriff.

`latest.json` (UTF-8, höchstens 64 KB):

```json
{
  "version": "0.2.0",
  "installer": "UmgebungssensorenPanel-Setup-0.2.0.exe",
  "sha256": "<64 Hex-Zeichen>",
  "published": "2026-10-02T12:00:00Z",
  "notes": "- Änderung 1\n- Änderung 2"
}
```

Der Installer wird nach `%TEMP%\umwelt-panel-update\` kopiert, gegen `sha256` geprüft und erst dann gestartet; das
Panel beendet sich dafür. Beim Start prüft das Panel still (nur bei einer neueren Version erscheint ein Hinweis);
„Nach Updates suchen“ in der Menüleiste antwortet immer. Nur `packaging/release.py` schreibt in den Update-Ordner.
