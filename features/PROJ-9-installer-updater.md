# PROJ-9: Installer und Update-Funktion für das Control Panel

## Status: In Review
**Created:** 2026-10-02
**Last Updated:** 2026-10-02 (Umsetzung, Build und Tests)

## Dependencies
- Requires: PROJ-8 (Control Panel) — das ist die Anwendung, die installiert und aktualisiert wird

## Summary
Das Control Panel (`umwelt_panel`) wird als Windows-Installer `UmgebungssensorenPanel-Setup-<Version>.exe`
ausgeliefert (PyInstaller One-Dir + Inno Setup, pro Benutzer, ohne Adminrechte) und findet neue Versionen
selbst im Update-Ordner auf dem Institutslaufwerk. 1:1 nach dem Vorbild des Schwesterprojekts
„RFB Controll Panel“ (dort PROJ-6 Windows-Installer und PROJ-10 Update-Funktion).

## User Stories
- Als Nutzer möchte ich das Control Panel mit einer Setup-Datei installieren, ohne Python oder Adminrechte
- Als Nutzer möchte ich beim Start erfahren, dass eine neuere Version bereitliegt, ohne selbst zu suchen
- Als Nutzer möchte ich jederzeit über „Nach Updates suchen“ selbst prüfen können
- Als Nutzer möchte ich, dass erst nach meinem Klick aktualisiert wird und meine Messwerte erhalten bleiben
- Als Entwickler möchte ich mit einem Befehl bauen und eine Version im Update-Ordner bereitstellen

## Placement
- **Gerät:** —
- **Protokoll:** keine Änderung
- **PC-Tool:** Control Panel: Menüleisten-Eintrag „Nach Updates suchen“ (rechts neben „Gerät“), nicht-modaler
  Hinweis unter dem Alarmbanner, Ergebnis- und Fortschrittsdialog; `packaging/` für Build und Veröffentlichung
- **Ohne PC nutzbar:** ja — das Gerät ist nicht betroffen

## Update-Ordner
`\\131.234.237.14\Gutmann\01_Interna\05_Software\Umgebungssensoren` mit `latest.json` (Version, Installer-Name,
SHA-256, Veröffentlichungszeit UTC, Änderungsnotizen) und den Installern (ältere bleiben liegen). Suche:
1. `UMWELT_UPDATE_DIR`, falls gesetzt
2. UNC-Pfad oben
3. jeder verbundene Netzlaufwerksbuchstabe + `01_Interna\05_Software\Umgebungssensoren`

Jede Probe hat 5 s Zeitlimit (eigener Daemon-Thread); die Anwendung liest nur, schreibt nie in den Ordner.
Nur `packaging/release.py` schreibt dorthin.

## Out of Scope
- Automatische Installation ohne Klick, Downgrade, Delta-Updates
- Code-Signatur des Installers
- Update der Firmware (das ist `/flash`)
- Update-Quellen außerhalb des Institutslaufwerks, Internet

## Acceptance Criteria
- [x] Angenommen PyInstaller und Inno Setup 6 sind installiert, wenn `python packaging/build.py` läuft, dann
  entsteht `dist/installer/UmgebungssensorenPanel-Setup-<Version>.exe`; weichen `__version__` (Panel, CLI) und
  `pc/pyproject.toml` voneinander ab, bricht der Build vorher mit deutscher Meldung ab
- [x] Angenommen das gebaute Bundle wird gestartet, dann läuft es ohne Konsolenfenster, schreibt sein Log nach
  `%LOCALAPPDATA%\Umgebungssensoren\Logs\panel.log` und nichts neben die EXE
- [ ] Angenommen der Installer läuft, dann fragt er nicht nach Adminrechten, installiert nach
  `%LOCALAPPDATA%\Programs\Umgebungssensoren Control Panel\`, legt einen Startmenü-Eintrag an und bietet eine
  Desktop-Verknüpfung (standardmäßig aus) an — *auf einem Zielrechner zu prüfen*
- [ ] Angenommen das Panel wird deinstalliert, dann bleiben Datenbank und Logs erhalten und der Deinstaller nennt
  den Ordner — *auf einem Zielrechner zu prüfen*
- [x] Angenommen im Update-Ordner liegt eine neuere Version, wenn das Panel startet, dann erscheint nach ca. 1 s
  ein nicht-modaler Hinweis „Version X ist verfügbar“ mit „Jetzt aktualisieren“ / „Später“; die Live-Anzeige
  läuft weiter
- [x] Angenommen das Laufwerk ist nicht erreichbar oder `latest.json` fehlt/ist kaputt, wenn das Panel startet,
  dann passiert nichts Sichtbares (nur Logeintrag)
- [x] Angenommen der Nutzer klickt „Nach Updates suchen“, dann gibt es immer eine Antwort: neuere Version
  (Dialog mit installierter/verfügbarer Version, Datum, Notizen, Größe), „bereits aktuell“, „Laufwerk nicht
  erreichbar“ oder „Versionsdatei ungültig“
- [x] Angenommen der Nutzer bestätigt, dann wird der Installer nach `%TEMP%\umwelt-panel-update\` kopiert
  (Fortschritt, abbrechbar), gegen die SHA-256 geprüft, gestartet und das Panel geschlossen; bei falscher
  Prüfsumme wird die Kopie gelöscht und nichts gestartet

## Edge Cases
- Hängendes Netzlaufwerk → höchstens ein Zeitlimit (5 s) im Hintergrund, GUI bleibt bedienbar
- Installer-Name in `latest.json` mit Pfad/`..`/falscher Version → abgelehnt
- Klick während der Hintergrundprüfung → keine zweite Suche, die laufende antwortet sichtbar
- Panel läuft während der Installation → Inno Setup (Restart Manager) fordert zum Schließen auf
- Gleichzeitiger Zugriff auf COM9: das Panel wird für das Update beendet und gibt den Port frei

## Device & Runtime Behaviour
| Aspekt | Verhalten |
|--------|-----------|
| Autarkie | Gerät unberührt; misst und alarmiert während des Updates weiter |
| Protokoll | keine Änderung |
| PC-Tool | Prüfung im QThreadPool, nie im GUI-Thread; Hintergrundprüfung still |
| Datenablage | Installation in `%LOCALAPPDATA%\Programs\…`, Daten unverändert in `%LOCALAPPDATA%\Umgebungssensoren\`; Installer-Kopie in `%TEMP%\umwelt-panel-update\` |
| Destruktive Aktionen | keine; Deinstallation lässt Daten stehen |

## Technical Requirements
- Python 3.11, PySide6 (Extra `panel`), Build-Werkzeuge PyInstaller ≥ 6 und Inno Setup ≥ 6.3 (nicht Laufzeit)
- Keine neue Laufzeitabhängigkeit (Update-Service: nur Standardbibliothek)

## Open Questions
- [ ] Update-Ordner `…\05_Software\Umgebungssensoren` auf dem NAS anlegen (existiert am 2026-10-02 noch nicht)
- [ ] PyInstaller in die `dev`-Extras aufnehmen? (neue Entwicklungsabhängigkeit → Nutzerfreigabe)
- [ ] Installer auf einem Zielrechner ohne Entwicklungsumgebung prüfen (Installation, Update, Deinstallation)

## Decision Log

### Product Decisions
| Entscheidung | Begründung | Datum |
|--------------|------------|-------|
| Vorgehen 1:1 wie im RFB Control Panel | Gleiche Nutzer, gleiches Institutslaufwerk, bewährter Ablauf | 2026-10-02 |
| Update-Ordner `01_Interna\05_Software\Umgebungssensoren` | Analog zum RFB-Ordner auf derselben Freigabe | 2026-10-02 |

### Technical Decisions
| Entscheidung | Begründung | Datum |
|--------------|------------|-------|
| `packaging/` im Repo-Wurzelordner, Ausgabe `dist/`, `build/` (gitignored) | Wie RFB; Befehl `python packaging/build.py` | 2026-10-02 |
| Version 0.1.0 bleibt Startversion; Panel, CLI und `pc/pyproject.toml` müssen übereinstimmen | Noch nichts ausgeliefert; ein `pyproject` beschreibt beide Pakete | 2026-10-02 |
| Tag `panel-v<Version>` lokal; Push nur mit `--push-tag` | `vX.Y.Z` gehört dem Gesamt-Release (`/release`); Push nur mit Freigabe | 2026-10-02 |
| Logdatei bleibt `panel.log` (statt RFB `app.log`) | Das Panel schrieb schon rotierend nach `…\Logs\panel.log`; Doku verweist darauf | 2026-10-02 |
| Keine Pumpenwarnung (RFB) — stattdessen Hinweis im Dialog, dass Verbindung/Aufzeichnung bis zum Neustart pausieren | Das Gerät arbeitet autark | 2026-10-02 |

---

## Implementation Notes
- `pc/src/umwelt_panel/core/services/update_service.py` — Qt-freier Port des RFB-Service (Versionsvergleich
  SemVer, `latest.json`-Prüfung mit Größengrenze, Suche mit Zeitlimit, Kopie mit SHA-256, Start per Argumentliste)
- `core/errors.py` — Update-Fehler mit deutschen Meldungen; `config.update_dir_override()` liest `UMWELT_UPDATE_DIR`
- `ui/update_controller.py`, `ui/update_dialogs.py`, `ui/widgets/update_notice.py`; Einbindung in
  `ui/main_window.py` (Menüleiste, Hinweis, `schedule_update_check()`), Start in `app.py`
- `app.py`: im gefrorenen Fenster-Bundle sind `sys.stdout/stderr` `None` → auf das Null-Gerät umgeleitet
- `packaging/`: Spec (One-Dir, kein UPX, Versionsressource, Icon), `installer.iss` (UTF-8 BOM, AppId
  `918D6EB2-1FCC-4E91-85C0-5A5CFCD0C4F3`), `build.py`, `release.py`, `version_source.py`, `make_icon.py`
- Tests: `pc/tests/test_update_service.py` (42, Qt-frei), `pc/tests/test_update_gui.py` (14, offscreen);
  `conftest.py` lenkt UNC-Pfad und Laufwerkssuche in jedem Test um (nie echtes NAS)
- Build 2026-10-02: Installer 33,6 MB, Bundle 119 MB; Bundle startet (5 s, Log ok, keine Datei neben der EXE,
  Hintergrundprüfung meldet still „nicht erreichbar“, weil der Ordner noch fehlt)

## QA Test Results
_To be added by /qa_

## Release
_To be added by /release_
