# Entwicklerhandbuch als verbindlicher Standard (MANDATORY)

> `docs/ENTWICKLERHANDBUCH.md` ist die **verbindliche Referenz** für Leitplanken,
> Architektur, Konventionen und bekannte Fallstricke von Umgebungssensoren. Es gilt wie
> eine Rule und wird bei jeder Weiterentwicklung **fortgeschrieben**.
> Abgrenzung: `docs/SPEC.md` ist der fachliche/technische **Vertrag** (Hardware,
> Datenmodell, Protokoll). Das Handbuch beschreibt, **wie** gebaut wird.

## 1. Vor jeder Arbeit: Handbuch lesen
- Vor jedem Feature, Fix oder Refactor die relevanten Kapitel lesen (mindestens:
  Leitplanken, Architektur, Konventionen, Bekannte Fallstricke).
- Nach einer Kontext-Komprimierung erneut lesen, nicht aus dem Gedächtnis arbeiten.

## 2. Treue zu Design und Vision (keine Abweichung ohne Freigabe)
- **Vision** (Handbuch Kap. 1 + `docs/PRD.md`): autarke, robuste Umgebungsdaten-Anzeige;
  der PC ist Zusatz, nie Voraussetzung. **Non-Goals** aus dem PRD werden nicht
  „nebenbei" gebaut.
- **Architektur-Muster:** dünne `.ino`, Module je Verantwortung, nicht-blockierende
  Loop, `config.h` als einzige Quelle für Pins/Grenzen; PC-Client ohne GUI-Abhängigkeit.
- **„Genau so weitermachen":** Neue Bildschirme, Befehle und CLI-Kommandos folgen dem
  Vorbild der bestehenden (gleiche Tabelle, gleiche Namensgebung, gleiche Fehlerbehandlung).
- **Abweichungen** (neue Bibliothek, neues Muster, Bruch mit einer Konvention) nur nach
  **ausdrücklicher Rückfrage beim Nutzer**. Freigegebene Abweichungen werden als neue
  Konvention ins Handbuch geschrieben.

## 3. Nach jeder Änderung: Handbuch fortschreiben (MANDATORY)
Im **selben Commit oder direkt danach**:
1. **Entwicklungschronik:** neue Zeile mit Datum (YYYY-MM-DD), PROJ-ID bzw. „Fix/Chore",
   Kurzbeschreibung, ggf. Firmware-/Tool-Version.
2. **Betroffene Fachkapitel** anpassen, wenn sich Module, Pins, EEPROM-Layout,
   Speicherbudget, Befehle, CLI-Kommandos oder Konventionen geändert haben.
3. **Neue projektweite Stolperfallen** ins Kapitel „Bekannte Fallstricke"
   (skill-spezifische Lessons bleiben in `LESSONS.md`).
4. Kopfzeile „Stand:" auf das aktuelle Datum setzen.

Reine Tippfehler-/Formatierungs-Commits brauchen keinen Chronik-Eintrag.

## 4. Write-Then-Verify
Handbuch per Edit-Tool ändern, danach die Stelle erneut lesen. **Nie** behaupten, das
Handbuch sei aktualisiert, ohne es tatsächlich editiert zu haben.

## 5. Einbindung in den Workflow
- `/architecture`: Design muss zu den Handbuch-Mustern passen; Abweichungen markieren
  und freigeben lassen.
- `/firmware`, `/pc`: vor Abschluss Handbuch nachziehen (Abschnitt 3).
- `/qa`: prüft Handbuch-Konformität und ob die Chronik aktualisiert wurde.
- `/release`: Chronik-Eintrag mit Version/Tag vervollständigen.
- Nach jedem Feature: `/integrity` (siehe `code-integrity.md`).
