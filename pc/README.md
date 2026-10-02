# umwelt-ctl — PC-Tool für Umgebungssensoren

Optionales PC-Tool für die Umgebungssensoren-Anzeige (Arduino Uno + BME680). Das Gerät
arbeitet ohne PC; das Tool liest Werte aus, ändert Einstellungen und schreibt ein
CSV-Messprotokoll. Vertrag: `docs/SPEC.md`.

```bash
pip install -e "pc[dev]"
umwelt ping                    # Verbindung + Firmware-Version
umwelt status                  # Sensorzustand, Intervall, Alarme
umwelt read                    # aktuelle Messwerte
umwelt config                  # alle Einstellungen
umwelt config T_HI 28,5        # Schwellwert in °C setzen (OFF = aus)
umwelt config reset            # Standardwerte (mit Rückfrage)
umwelt ack                     # Alarm quittieren
umwelt time sync               # Geräteuhr auf PC-Zeit stellen
umwelt monitor --csv           # live, CSV nach ~/umwelt_messwerte.csv
umwelt gui                     # grafische Oberfläche
```

Port: automatisch (USB-VID 0x2341), sonst `--port COM9` oder `UMWELT_PORT=COM9`.
Das Messprotokoll liegt standardmäßig in `~/umwelt_messwerte.csv` (lokal, außerhalb des
Repos); Aufbewahrung und Löschen entscheidet der Nutzer.

Tests: `python -m pytest pc/tests` (ohne Gerät), `python -m pytest pc/tests -m hardware`
(Gerät an COM9 bzw. `UMWELT_PORT`).
