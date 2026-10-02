# Installation und Auslieferung — Control Panel

Diese Seite beschreibt beides: was beim Installieren, Aktualisieren und Deinstallieren des
**Umgebungssensoren Control Panels** passiert (für Nutzerinnen und Nutzer) und wie aus dem Quellcode ein
Windows-Installer entsteht und im Update-Ordner bereitgestellt wird (für Entwickler). Aufbau und Verhalten
entsprechen dem Schwesterprojekt „RFB Controll Panel“. Die Firmware des Geräts ist davon nicht betroffen
(die wird mit `/flash` aufgespielt).

---

## Für Nutzer

### Was Sie bekommen

Eine einzelne Datei `UmgebungssensorenPanel-Setup-<Version>.exe` (ca. 34 MB). Sie enthält alles: die
Anwendung, Python und Qt. **Auf dem Zielrechner muss nichts vorinstalliert sein.** Voraussetzung ist
Windows 10 oder 11 (64 Bit) und ein freier USB-Anschluss für das Gerät.

### Installation

1. Setup-Datei doppelklicken.
2. **SmartScreen-Warnung** — siehe unten. Der Installer ist nicht signiert.
3. Der Assistent führt auf Deutsch durch Zielordner, optionale Desktop-Verknüpfung und Installation.
4. Am Ende kann das Panel direkt gestartet werden.

**Es erscheint keine Nachfrage nach Administratorrechten.** Die Installation läuft im Benutzerprofil:

| Was | Wohin |
|-----|-------|
| Programmdateien | `%LOCALAPPDATA%\Programs\Umgebungssensoren Control Panel\` |
| Startmenü-Eintrag | „Umgebungssensoren Control Panel“ (nur für den aktuellen Benutzer) |
| Desktop-Verknüpfung | optional, standardmäßig **aus** |
| Benutzerdaten | `%LOCALAPPDATA%\Umgebungssensoren\` (wie bisher) |

### SmartScreen-Warnung („Der Computer wurde durch Windows geschützt“)

Die Setup-Datei trägt keine Code-Signatur. Auf **„Weitere Informationen“** und dann **„Trotzdem ausführen“**
klicken. Prüfen Sie trotzdem, dass die Datei aus dem Update-Ordner auf dem Institutslaufwerk stammt.
Schlägt ein Virenscanner an: als Fehlalarm melden bzw. die IT fragen — den Scanner bitte nicht abschalten.

### Wo liegen meine Daten?

| Datei | Inhalt |
|-------|--------|
| `%LOCALAPPDATA%\Umgebungssensoren\messwerte.db` (+ `-wal`, `-shm`) | Messwert-Datenbank und Einstellungen des Panels |
| `%LOCALAPPDATA%\Umgebungssensoren\Logs\panel.log` | Protokoll der Anwendung (rotierend, 3 × 1 MB) |

In das **Installationsverzeichnis schreibt die Anwendung nichts**. Details: [configuration.md](configuration.md).

### Aktualisieren

- **Automatisch:** Kurz nach dem Start sucht das Panel im Hintergrund im Update-Ordner auf dem
  Institutslaufwerk. Liegt dort eine neuere Version, erscheint unter dem Alarmbanner ein Hinweis
  „Version X ist verfügbar“ mit **„Jetzt aktualisieren“** und **„Später“**. Ist das Laufwerk nicht erreichbar
  (z. B. ohne VPN), passiert nichts Sichtbares.
- **Von Hand:** Menüleiste **„Nach Updates suchen“** — hier gibt es immer eine Antwort (neue Version, bereits
  aktuell, Laufwerk nicht erreichbar, Versionsdatei ungültig).
- Nach „Jetzt aktualisieren“ wird der Installer in den Temp-Ordner kopiert, seine Prüfsumme kontrolliert, dann
  wird er gestartet und das Panel beendet sich. Die Verbindung zum Gerät wird getrennt und die Aufzeichnung
  pausiert bis zum nächsten Start; **das Gerät selbst misst und warnt weiter**.
- Eine neue Setup-Datei kann auch einfach von Hand über die vorhandene Installation ausgeführt werden. Der
  Installer erkennt die Installation, fordert ggf. zum Schließen des Panels auf und lässt den Datenordner
  unangetastet.

### Deinstallation

Über **Einstellungen → Apps → Installierte Apps → „Umgebungssensoren Control Panel“ → Deinstallieren**.
Entfernt werden nur Programmdateien, Startmenü-Eintrag und ggf. die Desktop-Verknüpfung. **Ihre Messwerte
bleiben erhalten**; der Deinstaller nennt zum Schluss den Datenordner. Wer alles entfernen möchte, löscht
`%LOCALAPPDATA%\Umgebungssensoren\` danach von Hand.

### Wenn das Panel nicht startet

| Symptom | Ursache und Abhilfe |
|---------|---------------------|
| Nichts passiert nach dem Doppelklick | Das Panel hat kein Konsolenfenster; Grund steht in `%LOCALAPPDATA%\Umgebungssensoren\Logs\panel.log` |
| „Datenbank kann nicht geöffnet werden“ | Datenordner schreibgeschützt/gesperrt; der Meldungstext nennt den Fall |
| Keine Verbindung zum Gerät | USB-Kabel prüfen; nur ein Programm darf COM-Port gleichzeitig nutzen (CLI, Arduino-IDE, zweites Panel schließen) |

---

## Für Entwickler

### Voraussetzungen

```powershell
pip install -e "pc[dev,panel]"     # PySide6, platformdirs, pytest, ruff
pip install pyinstaller            # nur Build-Werkzeug (getestet: 6.22)
```

Dazu **Inno Setup 6.3 oder neuer** (<https://jrsoftware.org/isdl.php>). `build.py` sucht `ISCC.exe` im `PATH`,
unter `%LOCALAPPDATA%\Programs\Inno Setup 6\` (Installation pro Benutzer) und unter `Program Files` /
`Program Files (x86)`. Fehlt es, bricht der Build **vor** dem langen PyInstaller-Lauf mit deutschem Hinweis ab.

### Bauen

```powershell
python packaging/build.py                 # Bundle + Installer
python packaging/build.py --no-installer  # nur das PyInstaller-Bundle
```

Ergebnis (beides gitignored):

```
dist/UmgebungssensorenPanel/                                 One-Dir-Bundle (UmgebungssensorenPanel.exe + _internal/)
dist/installer/UmgebungssensorenPanel-Setup-<Version>.exe    fertiger Installer
```

### Version anheben

Drei Stellen, **müssen übereinstimmen** (ein `pyproject` liefert CLI und Panel aus); `build.py` und
`release.py` brechen sonst ab:

- `__version__` in `pc/src/umwelt_panel/__init__.py` (maßgeblich)
- `__version__` in `pc/src/umwelt_ctl/__init__.py`
- `version` in `pc/pyproject.toml`

Der Updater vergleicht nach Semantic Versioning: nur eine **höhere** Version wird angeboten.

### Veröffentlichen im Update-Ordner

```powershell
python packaging/release.py --dry-run     # alles prüfen, nichts ändern
python packaging/release.py               # Gates, Build, Kopie + Prüfsumme, latest.json, lokales Tag
python packaging/release.py --push-tag    # zusätzlich Tag panel-v<Version> nach origin (nur mit Freigabe)
```

Ablauf: Versionen gleich, Arbeitsbaum sauber, Tag `panel-v<Version>` frei, Update-Ordner mit **derselben Suche
wie die Anwendung** gefunden (er muss existieren), Installer dieser Version noch nicht vorhanden, `latest.json`
zeigt auf keine gleiche/neuere Version → `ruff check pc`, `pytest pc/tests` → `build.py` → Installer als
`.partial` kopieren, Prüfsumme vergleichen, umbenennen → **zuletzt** `latest.json` atomar schreiben → Tag.
Nichts wird überschrieben.

### Symbol neu erzeugen

`packaging/app.ico` (Thermometer, 16/32/48/256 px) ist eingecheckt; neu nur bei Motivänderung:
`python packaging/make_icon.py`.

### Welche Datei wofür

| Datei | Verantwortung |
|-------|---------------|
| `packaging/umgebungssensoren-panel.spec` | Was ins Bundle kommt: Stylesheet, versteckte Importe, Ausschlüsse, Symbol, Versionsressource |
| `packaging/installer.iss` | Wie installiert wird (UTF-8 **mit BOM**; `AppId` nie ändern) |
| `packaging/build.py` | Aufräumen, Versionen prüfen, beide Schritte starten |
| `packaging/release.py` | Veröffentlichen im Update-Ordner |
| `packaging/version_source.py` | Liest die Versionsnummern, ohne die Anwendung zu importieren |
| `packaging/make_icon.py` | Erzeugt `app.ico` aus der Standardbibliothek |

### Vor der Auslieferung prüfen (Zielrechner ohne Entwicklungsumgebung)

- [ ] Installer läuft ohne Administrator-Abfrage durch
- [ ] Panel startet über das Startmenü, verbindet sich mit dem Gerät
- [ ] Datenbank und Log entstehen unter `%LOCALAPPDATA%\Umgebungssensoren\`, nicht im Installationsverzeichnis
- [ ] Update über die Vorversion erhält die Messwerte
- [ ] Deinstallation entfernt das Programm und lässt die Daten stehen
