# Skill Lessons-Learned System

## Konzept
Jeder Skill hat eine `LESSONS.md`-Datei in seinem Verzeichnis
(`.claude/skills/<skill>/LESSONS.md`). Sie enthält konkrete Fehler, Korrekturen und
Learnings aus vergangenen Durchläufen. So vermeidet jeder Skill bekannte Fehler automatisch.

## Pflichten für JEDEN Skill und jeden Agenten

### Vor dem Start (MANDATORY)
- `LESSONS.md` des Skills lesen, BEVOR die Arbeit beginnt
- Alle dokumentierten Learnings aktiv anwenden
- Sagt eine Lesson „Mach X nicht, mach stattdessen Y" → befolgen

### Nach Fehlern / Korrekturen (MANDATORY)
Eine neue Lesson in die `LESSONS.md` des betroffenen Skills schreiben, wenn:
1. **Compile/Tests fehlschlagen** und der Fehler gefixt werden musste
2. **QA einen Bug findet**, der durch bessere Umsetzung vermeidbar gewesen wäre
3. **Der Nutzer eine Korrektur verlangt**
4. **Ein Muster nicht funktioniert** und ein Workaround nötig war
5. **Eine Annahme falsch war** (Pinbelegung, Display-Variante, Touch-Controller,
   Timing des Resets beim Port-Öffnen, Bibliotheksverhalten, Speicherbedarf)
6. **Die Hardware sich anders verhält als gedacht** (Flackern, Prellen, Stack-Überlauf,
   Reset-Schleifen)

Zuordnung: Firmware → `firmware/`, PC-Tool → `pc/`, Tests → `qa/`, Flashen →
`flash/`, Auslieferung → `release/`, Orchestrierung → `autonom/`, Struktur/Regression →
`integrity/`. Projektweite Stolperfallen zusätzlich ins Handbuch
(`docs/ENTWICKLERHANDBUCH.md`, Kapitel „Bekannte Fallstricke").

### Format für neue Lessons
```markdown
## Lesson N: Kurzer Titel (YYYY-MM-DD)

**Was ist passiert?** Konkreter Fehler / konkrete Korrektur.

**Warum?** Ursache — nicht nur Symptom.

**Was gilt ab jetzt?** Die Regel, die der Skill in Zukunft befolgt.
```

### Regeln
- Lessons sind **konkret und actionable** — keine vagen Hinweise
- Jede Lesson enthält die **Regel**, die in Zukunft gilt
- Veraltete Lessons (z. B. nach Bibliotheks-Updates) dürfen entfernt werden
- Doppelte Lessons zusammenführen statt wiederholen; Ergänzungen als „Nachtrag (Datum)"
- Max. ~30 Lessons pro Skill — älteste/unwichtigste entfernen, wenn nötig
- Neue Lessons unter `<!-- Neue Lessons werden hier eingefügt -->` anhängen
