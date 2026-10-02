---
name: archive
description: Archive released features, update memory, and reset tracking for the next development cycle. Use after the current features are running on the production device.
argument-hint: "optional: specific PROJ-IDs to archive, e.g. PROJ-1 PROJ-2"
user-invocable: true
allowed-tools: Read, Write, Edit, Glob, Grep, Bash
model: sonnet
---

# Feature Archiver & Context Optimizer

## Role
Du räumst nach einem Feature-Zyklus auf: ausgelieferte Feature-Specs archivieren, das Langzeitgedächtnis aktualisieren, Tracking-Dateien zurücksetzen und den Token-Verbrauch künftiger Gespräche senken.

## Before Starting
1. **Lies [LESSONS.md](LESSONS.md)** — bekannte Fehler und Learnings anwenden

## When Invoked

### Step 1: Analyze Current State
1. **Lies `features/INDEX.md`** und finde alle Features mit Status **"Released"**
2. **Argumente prüfen** — wenn PROJ-IDs angegeben sind, nur diese archivieren, sonst ALLE "Released"
3. **Lies den Memory-Index** `MEMORY.md` im Memory-Verzeichnis und prüfe, ob `project_released_features.md` existiert

**Nur wirklich ausgelieferte Features archivieren:** "Released" heißt: die Firmware läuft auf dem Produktivgerät und das passende PC-Tool ist installiert und verifiziert. "Approved" ist getestet, aber noch nicht ausgeliefert.

Bei "Approved" ohne "Released":
> "PROJ-X ist getestet, aber noch nicht ausgeliefert. Führe zuerst `/release` aus — archiviert wird erst, was tatsächlich auf dem Gerät läuft."

Wenn nichts zu archivieren ist:
> "Keine Features zum Archivieren gefunden. Alle Features in INDEX.md haben noch Status 'Planned', 'In Progress', 'In Review' oder 'Approved'."

### Step 2: Update Long-Term Memory
1. Bestehende Memory-Datei `project_released_features.md` lesen (falls vorhanden)
2. Neu ausgelieferte Features an die Tabelle **anhängen** — nichts überschreiben
3. Datum im Header aktualisieren; `MEMORY.md` ergänzen, falls die Datei neu ist

```markdown
---
name: project_released_features
description: Übersicht aller ausgelieferten Umgebungssensoren-Features mit Firmware-/Tool-Version
metadata:
  type: project
---

# Ausgelieferte Features (Stand YYYY-MM-DD)

Alle archivierten Feature-Specs liegen in `features/archive/`.

| ID | Feature | FW-Version | Tool-Version | Beschreibung |
|----|---------|------------|--------------|--------------|
| PROJ-X | Name | X.Y.Z | X.Y.Z | Kurzbeschreibung |
```

Die **Versionen** machen den Eintrag später nützlich: bei einem Problem mit dem Gerät ist die erste Frage, welche Firmware auf dem Gerät läuft (`PING`) und was darin enthalten war.

### Step 3: EEPROM-Layout und Protokoll dokumentieren, bevor die Spec verschwindet
Hat ein Feature das **EEPROM-Layout** geändert? → Zeile in `docs/eeprom-layout-history.md` prüfen/ergänzen:
```markdown
| Layout-Version | Feature | FW-Version | Was sich an der gespeicherten Konfiguration geändert hat |
|----------------|---------|------------|-----------------------------------------------------------|
| 2 | PROJ-X | X.Y.Z | Schwellwerte und Kalibrier-Offsets ergänzt; alte Konfiguration fällt auf Defaults zurück |
```
Hat ein Feature das **Protokoll** geändert? → prüfen, dass `docs/SPEC.md` und `docs/release-notes.md` die Änderung samt Kompatibilität nennen.

Diese Dateien wandern nie ins Archiv: Geräte werden über beliebig alte Versionen hinweg neu geflasht, die Kette muss nachvollziehbar bleiben.

### Step 4: Archive Feature Specs
```bash
mkdir -p features/archive
mv features/PROJ-X-*.md features/archive/
```
Nur die tatsächlich zu archivierenden Features verschieben (per PROJ-ID prüfen).

**Tests und Code bleiben, wo sie sind.** `pc/tests/` ist die dauerhafte Regressions-Suite.

### Step 5: Reset INDEX.md
Archivierte Features aus der aktiven Tabelle entfernen, Struktur erhalten (Status-Legende, Tabelle, „Next Available ID"). Der Abschnitt „Released (Archived)" nennt den **gesamten** archivierten Bereich inkl. früherer IDs und die zuletzt ausgelieferte Firmware-/Tool-Version.

### Step 6: Update PRD Roadmap
`docs/PRD.md`: archivierte Features als "Released X.Y.Z" (Einzeiler); Verweis auf `features/INDEX.md` bleibt.

### Step 7: Summary
```
## Archivierung abgeschlossen

**Archiviert:** PROJ-X bis PROJ-Y (Z Features, Firmware X.Y.Z / PC-Tool X.Y.Z)
**Langzeitgedächtnis:** Aktualisiert
**EEPROM-Layout-Historie:** [N neue Einträge / keine Änderung]
**INDEX.md:** Bereit für neue Features ab PROJ-Z

Nächster Schritt: `/write-spec` um neue Features anzulegen.
```

## Important Rules
- NIEMALS Feature-Specs löschen — nur ins Archiv VERSCHIEBEN
- NIEMALS Tests oder Code archivieren — nur die Spec-Datei
- NIEMALS Daten verlieren — an das Memory anhängen, nicht überschreiben
- NIEMALS "Approved"-Features archivieren
- `docs/eeprom-layout-history.md`, `docs/release-notes.md`, `docs/SPEC.md` bleiben außerhalb des Archivs
- Verschiebungen verifizieren (Verzeichnis nach dem `mv` erneut auflisten)
- "Next Available ID" korrekt setzen
- Auf Deutsch kommunizieren
