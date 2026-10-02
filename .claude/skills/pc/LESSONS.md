# Lessons Learned

> Wird aktualisiert, wenn Fehler auftreten oder Korrekturen nötig sind. Vor jedem Durchlauf lesen und befolgen.
> Jede Lesson beantwortet: Was ist passiert? Warum? Was gilt ab jetzt?

---

<!-- Neue Lessons werden hier eingefügt -->

## 2026-10-02 — Doppelte Backslashes gehen in Bash-Heredocs verloren (PROJ-9)
- **Was:** Ein per Bash-Heredoc angehängter Doku-Text machte aus dem UNC-Pfad `\131.234…` ein `\131.234…`; ein Python-Heredoc mit `\U…` brach mit SyntaxError ab.
- **Warum:** Das Bash-Werkzeug reicht `\` nicht unverändert durch.
- **Ab jetzt:** Texte mit Windows-/UNC-Pfaden nur mit Write/Edit schreiben, nie per Heredoc; danach `grep -n "131.234"` o. ä. prüfen.
