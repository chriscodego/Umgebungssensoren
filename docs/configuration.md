# Konfiguration

| Was | Wert |
|---|---|
| Serieller Port | `--port COM9` > Umgebungsvariable `UMWELT_PORT=COM9` > automatisch (USB-VID 0x2341) |
| Verbinden | DTR/RTS aus — das Öffnen des Ports startet den Uno nicht neu |
| Messprotokoll (CSV) | Standard `~/umwelt_messwerte.csv` (außerhalb des Repos, lokal; Aufbewahrung entscheidet der Nutzer) |
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
