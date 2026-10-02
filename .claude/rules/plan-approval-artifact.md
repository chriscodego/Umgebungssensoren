# Plan zeigen → Bestätigung holen → umsetzen, als Artefakt (MANDATORY)

> Nutzer-Vorgabe (übernommen aus LabPilot, 2026-09-27): Der Nutzer will jeden Plan und
> jedes Ergebnis **sehen**, als Artefakt und nicht nur als Terminal-Text, und er will vor
> der Umsetzung **gefragt** werden.

## Ablauf bei jeder Aufgabe, die Code, Firmware auf dem Gerät, Konfiguration oder Git ändert
1. **Erst verstehen:** Recherche und Analyse (lesen, suchen, Explore-Subagents,
   `arduino-cli board list`, Kompilieren ohne Upload) sind ohne Rückfrage erlaubt.
2. **Plan als Artefakt zeigen:** Den Plan als Artefakt veröffentlichen (Artifact-Tool;
   vorher `artifact-design` laden bzw. `quickstart`) und dem Nutzer den Link geben.
   Der Plan enthält:
   - Ziel
   - betroffene Dateien/Module (Firmware, PC-Tool, SPEC.md, Tests)
   - Protokoll- oder EEPROM-Layout-Änderungen
   - Speicherbudget-Auswirkung (RAM/Flash grob)
   - Risiken und Auswirkungen auf bestehende Features
   - offene Entscheidungen mit Empfehlung
   - Aufteilung auf parallele Subagents (siehe `subagent-execution.md`)
3. **Bestätigung einholen:** per AskUserQuestion ausdrücklich fragen, ob der Plan so
   umgesetzt werden soll (Optionen: umsetzen / anpassen / verwerfen). **Vor der Freigabe
   keine Änderung** an Code, Gerät, Konfiguration oder Git-Historie.
4. **Ergebnis als Artefakt zeigen:** Nach der Umsetzung Bericht als Artefakt (dasselbe
   aktualisieren oder ein neues) mit Link: was geändert wurde, Commits, Prüfergebnisse
   (Compile inkl. RAM/Flash, pytest, Hardware-Smoke-Test), offene Punkte.

## Ausnahmen
- Reine Fragen/Auskünfte ohne Änderung: Antwort direkt im Chat.
- Hat der Nutzer einen konkreten Schritt bereits ausdrücklich freigegeben (z. B.
  „wenn alles grün ist, flashen"), gilt die Freigabe für genau diesen Schritt. Das
  Ergebnis wird trotzdem gezeigt.
- Einzel-Freigaben (Upload auf das Gerät (COM9), EEPROM-Layout-Wechsel,
  Protokolländerung) bleiben **zusätzlich** bestehen.

## Hinweise
- Artefakte sind privat; der Nutzer entscheidet selbst über das Teilen.
- Keine Messprotokolle (CSV-Inhalte) oder sonstige
  personenbezogene Daten ins Artefakt.
