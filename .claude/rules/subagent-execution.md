# Subagent-Ausführungsregeln

## Grundprinzip (Nutzer-Vorgabe, übernommen aus LabPilot)
**Mit so vielen Subagents gleichzeitig arbeiten wie sinnvoll möglich.** Jede Aufgabe
wird zuerst in unabhängige Teile zerlegt, und alle unabhängigen Teile laufen **parallel**
(in EINER Nachricht mehrere Agent-Aufrufe). Strikt nacheinander nur bei echten
Abhängigkeiten — und in diesem Projekt gibt es zwei harte:

1. **Das Protokoll.** Firmware und PC-Tool dürfen parallel laufen, **wenn** der
   Protokollteil in `docs/SPEC.md` vorher feststeht und keiner der beiden ihn ändert.
   Ändert ein Feature das Protokoll: SPEC.md zuerst (Hauptagent, nach Nutzerfreigabe),
   dann Firmware ∥ PC-Tool gegen die fixierte SPEC.
2. **Die Hardware.** Es gibt **ein** Board an **einem** COM-Port (COM9). Upload,
   Monitor, CLI, GUI und Hardware-Tests schließen sich gegenseitig aus. Nur **ein**
   Agent zur Zeit darf die Hardware benutzen — der Hauptagent vergibt diesen „Hardware-
   Slot" explizit im Auftrag; alle anderen arbeiten nur mit Compile und Host-Tests.

## Maximale Parallelisierung
1. **Zerlegen:** je Feature, je Seite (Firmware ∥ PC-Tool), je Phase (Spec-Recherche ∥
   Tests schreiben ∥ Doku).
2. **Isolation:** Jeder schreibende Subagent bekommt `isolation: "worktree"`. Lesende
   Agents (Explore, Review) brauchen keinen Worktree.
3. **Konflikte klein halten:** Geteilte Dateien (`features/INDEX.md`, `docs/PRD.md`,
   `docs/SPEC.md`, `docs/ENTWICKLERHANDBUCH.md`, `config.h`) fasst nur der Hauptagent beim
   Zusammenführen an bzw. genau ein benannter Agent. Neue Logik kommt in eigene Dateien.
4. **Zusammenführen:** Der Hauptagent merged die Worktree-Branches nacheinander, löst
   Konflikte und führt danach EINMAL `/integrity` auf dem Gesamtstand aus.
5. **Ein Feature = ein vollständig verantwortlicher Agent** bleibt die Grundeinheit.

## Vollständigkeit (MANDATORY)
Jeder Subagent liefert seinen Teil KOMPLETT ab:
- Spec lesen (+ Tech Design, falls seine Aufgabe) + committen
- Implementieren + Gates (Compile/pytest/ruff) + committen
- QA gegen ALLE betroffenen Acceptance Criteria (Hardware nur mit zugeteiltem Slot)
- CRITICAL/HIGH-Bugs fixen + committen
- Spec-Status + Implementation Notes aktualisieren und verifizieren

**Kein Feature wird „In Review", wenn ACs fehlen.** Lieber weniger Features vollständig
als viele halbfertig.

## Token-Effizienz
- Kompakte Prompts: Feature-ID, Stack-Info, Lessons-Zusammenfassung, Hardware-Slot ja/nein
- Idempotenz: Agent prüft via `git log`/`git status`, was schon existiert, und überspringt Erledigtes
- Minimale Rückgabe: max. 5 Zeilen (Status, Commits, QA, RAM/Flash, Entscheidungen)
- Dateien mit Read/Grep/Glob lesen, Bash nur für freigegebene Einzelbefehle (keine Pipes/
  `&&`-Ketten — die lösen Permission-Prompts aus und stoppen autonome Läufe)

## Abbruch-Verhalten
- Hauptagent prüft via `git log` + `git status`, was geschafft wurde
- Nächster Agent setzt **idempotent** fort
- Uncommittete Arbeit wird zuerst stabilisiert (Compile/Tests → Commit)

## „Terminated" heißt NICHT tot (Vorfall LabPilot 2026-07-17)
Ein als „terminated" gemeldeter Hintergrund-Agent kann weiterlaufen und weiter committen
— oder weiter den COM-Port halten.
1. Vor Git-Aufräumarbeit HEAD-Stabilität prüfen (`git rev-parse HEAD` mehrfach über 1–2 min).
   Bewegt sie sich → warten, nicht kämpfen.
2. Nie `git revert`/`reset` gegen einen laufenden Schreiber.
3. Aufräumen deterministisch: betroffene Dateien gezielt auf den Stand vor dem Feature
   holen (`git checkout <pre> -- <dateien>`), in EINEM Commit.
4. „Port belegt" nach einem Abbruch → prüfen, ob ein Agent/Monitor noch läuft, bevor
   irgendetwas „repariert" wird.
5. Autonome Läufe am Ende auf Vollständigkeit UND ungewollte Commits prüfen.
