import datetime as dt
import os
import re

import pytest

from umwelt_ctl import messlog
from umwelt_ctl.messlog import HEADER, MessLogger, default_log_path
from umwelt_ctl.protocol import Measurement

TZ = dt.timezone(dt.timedelta(hours=2))
FIXED = dt.datetime(2026, 10, 2, 14, 3, 12, 345678, tzinfo=TZ)


def read_bytes(path):
    with open(path, "rb") as f:
        return f.read()


def test_default_path_is_in_home_outside_repo():
    path = default_log_path()
    assert path == os.path.join(os.path.expanduser("~"), "umwelt_messwerte.csv")


def test_new_file_gets_bom_header_and_rows(tmp_path):
    path = tmp_path / "m.csv"
    log = MessLogger(path, now=lambda: FIXED)
    log.write(Measurement(2134, 4512, 10132, 85000), 0)
    data = read_bytes(path)
    assert data.startswith(b"\xef\xbb\xbf")
    text = data.decode("utf-8-sig")
    lines = text.splitlines()
    assert lines[0] == ";".join(HEADER) == "zeit;temperatur_c;feuchte_proz;druck_hpa;gas_ohm;alarm"
    assert lines[1] == "2026-10-02T14:03:12+02:00;21,34;45,12;1013,2;85000;0"


def test_invalid_values_are_empty_never_zero(tmp_path):
    path = tmp_path / "m.csv"
    log = MessLogger(path, now=lambda: FIXED)
    log.write(Measurement(), 16)
    log.write(Measurement(-512, None, 10132, None), None)
    lines = read_bytes(path).decode("utf-8-sig").splitlines()
    assert lines[1] == "2026-10-02T14:03:12+02:00;;;;;16"
    assert lines[2] == "2026-10-02T14:03:12+02:00;-5,12;;1013,2;;"


def test_append_without_second_bom_or_header(tmp_path):
    path = tmp_path / "m.csv"
    MessLogger(path, now=lambda: FIXED).write(Measurement(2000, 5000, 10000, 1), 0)
    MessLogger(path, now=lambda: FIXED).write(Measurement(2100, 5000, 10000, 1), 1)
    data = read_bytes(path)
    assert data.count(b"\xef\xbb\xbf") == 1
    lines = data.decode("utf-8-sig").splitlines()
    assert len(lines) == 3 and lines.count(";".join(HEADER)) == 1


def test_existing_empty_file_gets_header(tmp_path):
    path = tmp_path / "m.csv"
    path.write_bytes(b"")
    MessLogger(path, now=lambda: FIXED).write(Measurement(2000, 5000, 10000, 1), 0)
    assert read_bytes(path).decode("utf-8-sig").splitlines()[0] == ";".join(HEADER)


def test_each_row_is_on_disk_immediately(tmp_path):
    path = tmp_path / "m.csv"
    log = MessLogger(path, now=lambda: FIXED)
    for i in range(3):
        log.write(Measurement(2000 + i, 5000, 10000, 1), 0)
        assert len(read_bytes(path).decode("utf-8-sig").splitlines()) == 2 + i  # no close()
    assert log.rows_written == 3


def test_real_timestamp_has_local_offset(tmp_path):
    path = tmp_path / "m.csv"
    MessLogger(path).write(Measurement(2000, 5000, 10000, 1), 0)
    stamp = read_bytes(path).decode("utf-8-sig").splitlines()[1].split(";")[0]
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d[+-]\d\d:\d\d", stamp)


def test_locked_file_keeps_rows_and_writes_them_later(tmp_path, monkeypatch):
    path = tmp_path / "m.csv"
    log = MessLogger(path, now=lambda: FIXED)
    log.write(Measurement(2000, 5000, 10000, 1), 0)
    real_open = open
    locked = {"on": True}

    def fake_open(file, mode="r", *a, **kw):
        if locked["on"] and "a" in mode:
            raise PermissionError(13, "Datei wird von Excel verwendet")
        return real_open(file, mode, *a, **kw)

    monkeypatch.setattr(messlog, "open", fake_open, raising=False)
    with pytest.raises(OSError):
        log.write(Measurement(2001, 5000, 10000, 1), 0)
    assert log.pending == 1
    locked["on"] = False
    log.write(Measurement(2002, 5000, 10000, 1), 0)
    lines = read_bytes(path).decode("utf-8-sig").splitlines()
    assert [x.split(";")[1] for x in lines[1:]] == ["20,00", "20,01", "20,02"]
    assert log.pending == 0


def test_missing_folder_is_reported(tmp_path):
    with pytest.raises(OSError, match="Ordner"):
        MessLogger(tmp_path / "gibtsnicht" / "m.csv")
