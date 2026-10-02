# QA Test Results Template

Add this section to the END of the feature spec `features/PROJ-X-*.md`:

```markdown
---

## QA Test Results

**Tested:** YYYY-MM-DD
**Firmware:** FW_VERSION x.y.z, commit abc1234 — auf Dev-Board / Produktivgerät
**PC-Tool:** umwelt-ctl x.y.z, Python 3.11.x, Windows 11
**Hardware-Slot:** ja (COM9) / nein
**Tester:** QA Engineer (AI)

### Automated Suite
| Check | Result |
|-------|--------|
| `arduino-cli compile … --warnings all` | Pass / Fail (neue Warnungen: n) |
| RAM global / Flash | xxx B (xx %) / xxxxx B (xx %) |
| `python -m pytest pc/tests` | X passed, Y failed |
| `python -m pytest pc/tests -m hardware` | X passed, Y failed / nicht ausgeführt |
| `ruff check pc` | Pass / Fail |

### Acceptance Criteria Status

#### AC-1: [Kriterium]
- [x] Passed

#### AC-2: [Kriterium]
- [ ] BUG: [was schiefging]

#### AC-3: [Kriterium]
- [ ] Nicht getestet (kein Hardware-Slot)

### Edge Cases Status

#### EC-1: [Edge Case]
- [x] Handled correctly

### Device & Runtime Behaviour

| Dimension | Result | Note |
|-----------|--------|------|
| Protokoll-Konformität (alle Befehle, Fehlercodes laut SPEC.md) | Pass / Fail / n. g. | |
| Zeilenlänge (Grenze laut SPEC, Nicht-ASCII = Bytes), `\r\n`, Groß-/Kleinschreibung | Pass / Fail / n. g. | |
| `EVT` zwischen Antwortzeilen | Pass / Fail / n. g. | |
| Grenzen (Intervall min/max, Schwellwerte, `TIME`-Format, Ganzzahl-Skalierung, negative Temperaturen) | Pass / Fail / n. g. | |
| Messgenauigkeit gegen Referenz (Temperatur, Feuchte, Druck; Gas nur Trend) | Pass / Fail / n. g. | |
| Sensorausfall (BME680 abgezogen/falsche Adresse): Fehleranzeige, kein Hänger, Wiederanlauf | Pass / Fail / n. g. | |
| Zeitgenauigkeit (Messintervall, Drift über ≥ 10 min), `loop()` nie > 100 ms blockiert | Pass / Fail / n. g. | |
| `EVT ALARM` genau einmal je Schwellwertverletzung (Hysterese), Buzzer einmal | Pass / Fail / n. g. | |
| Touch: Kalibrierung, Ziele (Seitenwechsel, Zurück, Einstellungen +/−) | Pass / Fail / n. g. | |
| Anzeige ohne Flackern / Pixelreste (Wertbreitenwechsel, Umlaute, °) | Pass / Fail / n. g. | |
| Autark ohne PC-Tool | Pass / Fail / n. g. | |
| Persistenz über Stromausfall (Intervall, Schwellwerte, Einheiten, Offsets, Touch-Kalibrierung; Uhr endet) | Pass / Fail / n. g. | |
| Kein Reset beim Verbinden (laufendes `umwelt monitor` überlebt `umwelt status`), Reconnect, `EVT BOOT` mitten im Betrieb | Pass / Fail / n. g. | |
| CSV-Messprotokoll (Format, BOM, ISO-8601, Anhängen ohne doppelten Header, Datei gesperrt) | Pass / Fail / n. g. | |
| Gleichzeitige Änderung Gerät/PC (`CFG SET`) | Pass / Fail / n. g. | |
| Dauerlauf ≥ 1 h | Pass / Fail / n. g. | |
| millis()-Überlauf (Code-Review) | Pass / Fail | Zeilen: |

### Robustness & Security Audit
- [x] Serial-Fuzzing: Gerät bleibt bedienbar, kein Reset, EEPROM intakt
- [x] Alle Puffer-Kopien begrenzt, alle Indizes/Wertebereiche vor Zugriff geprüft
- [x] Leeres/korruptes EEPROM → Defaults, kein Absturz
- [x] Kein `eval`/`exec`/`pickle`/`shell=True` im PC-Tool
- [x] Keine Geheimnisse/Pfade in Debug-Logs; CSV enthält keine Personendaten, Ort dem Nutzer genannt, nicht committet
- [ ] BUG: [Befund]

### Bugs Found

#### BUG-1: [Titel]
- **Severity:** Critical | High | Medium | Low
- **Steps to Reproduce:**
  1. [Schritt]
  2. [Schritt]
  3. Erwartet: [was passieren sollte]
  4. Tatsächlich: [was passiert]
- **Serial-Mitschnitt:** [relevante Zeilen, gesendet `>` / empfangen `<`]
- **Foto:** [bei Anzeige-/Touch-Bugs]
- **Priority:** Vor Release beheben | Nächster Zyklus | Nice to have

### Summary
- **Acceptance Criteria:** X/Y bestanden, Z nicht getestet
- **Bugs Found:** N gesamt (C critical, H high, M medium, L low)
- **Robustheit/Security:** [Pass / Befunde vorhanden]
- **Release Ready:** YES / NO
- **Empfehlung:** [Ausliefern / Erst Bugs beheben / Hardware-Test nachholen]
```
