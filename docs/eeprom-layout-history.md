# EEPROM-Layout-Historie

| Layout-Version | Feature | FW-Version | Was sich an der gespeicherten Konfiguration geändert hat |
|---|---|---|---|
| 1 | PROJ-2/6 | 0.1.0 | Erstes Layout (29 B ab Adresse 0): off 0 Magic `0x554D5753` (LE), off 4 Layout `1`, off 5 Config 13 B (int16 interval, temp_offset, t_hi, t_lo, rh_hi, rh_lo; uint8 buzzer; OFF = −32768), off 18 CRC-8 (Poly 0x07) über Config, off 19 TouchCal 9 B (int16 left/right/top/bottom, uint8 flags), off 28 CRC-8 über TouchCal. Inhalt der Bestandsfirmware gilt als ungültig → Defaults; geschrieben wird erst bei einer Änderung |
