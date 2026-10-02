"""Control Panel core/data layer (PROJ-8) — Qt-free, no hardware."""

from __future__ import annotations

import datetime as dt
import sqlite3
import sys
import time

import pytest

from umwelt_ctl import messlog
from umwelt_ctl.device import DeviceDisconnected, UmweltDevice
from umwelt_ctl.protocol import DeviceError, Measurement
from umwelt_panel.core.errors import (
    DatabaseCorruptError,
    DatabaseNewerError,
    ExportError,
)
from umwelt_panel.core.models import TimeRange, format_count, format_size, to_epoch_ms
from umwelt_panel.core.services.device_session import (
    DeviceSession,
    SessionListener,
    describe_error,
)
from umwelt_panel.core.services.log_service import MeasurementLog
from umwelt_panel.core.services.settings_service import SettingsService
from umwelt_panel.core.trend import FALLING, RISING, STEADY, GasTrend
from umwelt_panel.data.db import MIGRATIONS, Database

from conftest import FakeTransport, FakeUmwelt

UTC = dt.UTC
NOW = dt.datetime(2026, 10, 2, 12, 0, 0, tzinfo=UTC)
M = Measurement(2134, 4512, 10132, 85000)


@pytest.fixture
def db(tmp_path):
    d = Database(tmp_path / "sub" / "messwerte.db")
    d.open()
    return d


@pytest.fixture
def mlog(db):
    return MeasurementLog(db, now=lambda: NOW)


def wait_for(cond, timeout=3.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.02)
    return cond()


# --------------------------------------------------------------------------- Qt-free layering


def test_core_and_data_import_no_qt():
    import importlib

    for mod in ("umwelt_panel.core.services.device_session",
                "umwelt_panel.core.services.log_service",
                "umwelt_panel.core.services.settings_service",
                "umwelt_panel.data.db", "umwelt_panel.config"):
        importlib.import_module(mod)
    src = __import__("pathlib").Path(__file__).parents[1] / "src" / "umwelt_panel"
    for folder in ("core", "data"):
        for f in (src / folder).rglob("*.py"):
            assert "PySide6" not in f.read_text(encoding="utf-8"), f


# --------------------------------------------------------------------------- database


def test_open_creates_folder_schema_and_wal(tmp_path):
    d = Database(tmp_path / "neu" / "messwerte.db")
    assert d.open() == 0
    assert d.path.exists()
    with sqlite3.connect(d.path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == d.schema_version
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"measurements", "settings"} <= tables
        cols = [r[1] for r in conn.execute("PRAGMA table_info(measurements)")]
        assert cols[1:] == ["ts_utc", "t", "rh", "p", "gas", "alarm"]
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    assert d.open() == d.schema_version  # second start: nothing to do


def test_migration_from_older_schema_keeps_data(tmp_path):
    path = tmp_path / "m.db"
    Database(path, migrations=MIGRATIONS).open()
    log1 = MeasurementLog(Database(path), now=lambda: NOW)
    log1.record(M, 0)
    v2 = (*MIGRATIONS, (2, ("ALTER TABLE measurements ADD COLUMN note TEXT",)))
    d2 = Database(path, migrations=v2)
    assert d2.open() == 1
    with sqlite3.connect(path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 2
        assert "note" in [r[1] for r in conn.execute("PRAGMA table_info(measurements)")]
    assert MeasurementLog(d2).count() == 1


def test_failed_migration_rolls_back(tmp_path):
    path = tmp_path / "m.db"
    Database(path).open()
    bad = (*MIGRATIONS, (2, ("CREATE TABLE x (a)", "THIS IS NOT SQL")))
    with pytest.raises(Exception):  # noqa: B017 - translated DatabaseError
        Database(path, migrations=bad).open()
    with sqlite3.connect(path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE name='x'").fetchone()[0] == 0


def test_newer_database_is_refused_untouched(tmp_path):
    path = tmp_path / "m.db"
    Database(path).open()
    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA user_version=99")
    with pytest.raises(DatabaseNewerError) as exc:
        Database(path).open()
    assert "neueren Version" in str(exc.value)


def test_corrupt_file_gives_german_error(tmp_path):
    path = tmp_path / "kaputt.db"
    path.write_bytes(b"das ist keine datenbank" * 100)
    with pytest.raises(DatabaseCorruptError) as exc:
        Database(path).open()
    assert "keine gültige" in str(exc.value)


# --------------------------------------------------------------------------- log service


def test_record_keeps_invalid_values_null_never_zero(mlog, db):
    mlog.record(Measurement(None, 4512, None, None), 16)
    with sqlite3.connect(db.path) as conn:
        row = conn.execute("SELECT ts_utc, t, rh, p, gas, alarm FROM measurements").fetchone()
    assert row == (to_epoch_ms(NOW), None, 4512, None, None, 16)


def test_time_ranges(mlog):
    for age in (dt.timedelta(minutes=10), dt.timedelta(hours=5), dt.timedelta(days=3),
                dt.timedelta(days=30)):
        mlog.record(M, 0, NOW - age)
    assert mlog.count(TimeRange.HOUR) == 1
    assert mlog.count(TimeRange.DAY) == 2
    assert mlog.count(TimeRange.WEEK) == 3
    assert mlog.count(TimeRange.ALL) == 4
    s = mlog.samples(TimeRange.DAY)
    assert [x.ts_utc for x in s] == sorted(x.ts_utc for x in s)
    assert s[0].measurement == M and s[0].alarm == 0


def test_series_is_bucketed_above_max_points(mlog):
    for i in range(100):
        mlog.record(Measurement(2000 + i, None, 10000, 50000), 0,
                    NOW - dt.timedelta(seconds=10 * (100 - i)))
    raw = mlog.series(TimeRange.HOUR, max_points=200)
    assert len(raw) == 100
    agg = mlog.series(TimeRange.HOUR, max_points=10)
    assert 5 <= len(agg) <= 11
    assert all(s.measurement.rh is None for s in agg)  # all-invalid bucket stays invalid
    assert agg[0].measurement.t < agg[-1].measurement.t
    assert mlog.series(TimeRange.ALL, max_points=10)


def test_series_empty_log(mlog):
    assert mlog.series(TimeRange.ALL) == []
    assert mlog.series(TimeRange.HOUR) == []


def test_stats_and_clear(mlog):
    st = mlog.stats()
    assert st.count == 0 and st.first_utc is None and st.size_bytes > 0
    mlog.record(M, 0, NOW - dt.timedelta(hours=1))
    mlog.record(M, 1, NOW)
    st = mlog.stats()
    assert st.count == 2 and st.first_utc < st.last_utc == NOW
    assert mlog.clear() == 2
    assert mlog.stats().count == 0


def test_export_csv_format(mlog, tmp_path):
    mlog.record(Measurement(-5, 4512, 10132, 85000), 0, NOW - dt.timedelta(minutes=1))
    mlog.record(Measurement(None, None, None, None), 16, NOW)
    mlog.record(M, 0, NOW - dt.timedelta(days=2))  # outside 24 h
    target = tmp_path / "export.csv"
    assert mlog.export_csv(TimeRange.DAY, target) == 2
    raw = target.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    lines = raw.decode("utf-8-sig").splitlines()
    assert lines[0] == ";".join(messlog.HEADER)
    zeit, *vals = lines[1].split(";")
    local = (NOW - dt.timedelta(minutes=1)).astimezone()
    assert zeit == local.isoformat(timespec="seconds")
    assert dt.datetime.fromisoformat(zeit).utcoffset() is not None
    assert vals == ["-0,05", "45,12", "1013,2", "85000", "0"]
    assert lines[2].split(";")[1:] == ["", "", "", "", "16"]
    assert not (tmp_path / "export.csv.tmp").exists()


def test_export_empty_period_has_header_only(mlog, tmp_path):
    target = tmp_path / "leer.csv"
    assert mlog.export_csv(TimeRange.HOUR, target) == 0
    assert target.read_text(encoding="utf-8-sig").splitlines() == [";".join(messlog.HEADER)]


def test_export_to_missing_folder_is_german_error(mlog, tmp_path):
    with pytest.raises(ExportError) as exc:
        mlog.export_csv(TimeRange.ALL, tmp_path / "gibtsnicht" / "x.csv")
    assert "konnte nicht geschrieben werden" in str(exc.value)


def test_format_helpers():
    assert format_size(500) == "500 B"
    assert format_size(1536) == "1,5 KB"
    assert format_size(3 * 1024 * 1024) == "3,0 MB"
    assert format_count(12345) == "12.345"
    assert TimeRange.WEEK.label_de == "letzte 7 Tage"


# --------------------------------------------------------------------------- settings / trend


def test_settings_defaults_and_roundtrip(db):
    s = SettingsService(db)
    assert s.auto_log() is True
    assert s.port() is None
    assert s.history_range() is TimeRange.DAY
    assert s.history_metric() == "t"
    assert s.window_geometry() is None
    s.set_auto_log(False)
    s.set_port("COM9")
    s.set_history_range(TimeRange.WEEK)
    s.set_history_metric("gas")
    s.set_window_geometry("AAAA")
    s2 = SettingsService(db)
    assert (s2.auto_log(), s2.port(), s2.history_range(), s2.history_metric(),
            s2.window_geometry()) == (False, "COM9", TimeRange.WEEK, "gas", "AAAA")
    s2.set_port(None)
    assert s2.port() is None
    with pytest.raises(ValueError):
        s2.set_history_metric("co2")


def test_gas_trend():
    tr = GasTrend()
    assert tr.text() == ""
    assert tr.update(100000) == STEADY
    assert tr.update(None) == STEADY
    assert tr.update(120000) == RISING
    assert tr.text() == "↑ steigend"
    assert tr.update(80000) == FALLING
    tr.reset()
    assert tr.direction is None


# --------------------------------------------------------------------------- device session


class Recorder(SessionListener):
    def __init__(self):
        self.events: list[tuple] = []

    def on_measurement(self, m, ts, logged):
        self.events.append(("data", m, logged))

    def on_log_error(self, message):
        self.events.append(("log_error", message))

    def on_alarm(self, flag, active):
        self.events.append(("alarm", flag, active))

    def on_sensor(self, state):
        self.events.append(("sensor", state))

    def on_boot(self, fw):
        self.events.append(("boot", fw))

    def on_disconnected(self, reason):
        self.events.append(("lost", reason))

    def kinds(self):
        return [e[0] for e in self.events]


@pytest.fixture
def session_env(mlog):
    model = FakeUmwelt()
    transports: list[FakeTransport] = []
    opened: list[str | None] = []

    def open_device(port):
        opened.append(port)
        tr = FakeTransport(model)
        tr.port = port or "COM99"
        transports.append(tr)
        dev = UmweltDevice(tr, timeout=0.5)
        dev.start()
        try:
            dev.wait_ready(boot_wait=0.5)
        except BaseException:
            dev.close()
            raise
        return dev

    rec = Recorder()
    session = DeviceSession(rec, mlog, open_device=open_device)
    yield session, model, transports, rec, mlog, opened
    session.close()


def test_connect_enables_stream_sets_time_and_loads_state(session_env):
    session, model, transports, rec, mlog, opened = session_env
    info = session.connect(None)
    assert opened == [None]  # auto detection is umwelt_ctl.device.detect_port's job
    assert info.fw_version == "0.1.0" and info.port == "COM99"
    assert info.status.sensor == "OK" and info.measurement.t == 2134
    assert info.config["INTERVAL"] == 10
    assert model.stream is True and model.clock is not None
    w = transports[0].written
    assert w.index("STREAM 1") < w.index("STATUS")
    session.close()
    assert model.stream is False and transports[0].closed


def test_evt_data_is_logged_with_alarm_flags(session_env):
    session, model, _tr, rec, mlog, _ = session_env
    model.alarm = 4
    session.connect(None)
    session.recording = True
    model.measure((2200, 6000, 10100, 90000))
    assert wait_for(lambda: "data" in rec.kinds())
    assert rec.events[-1] == ("data", Measurement(2200, 6000, 10100, 90000), True)
    rows = mlog.samples(TimeRange.ALL, now=dt.datetime.now(UTC) + dt.timedelta(seconds=5))
    assert len(rows) == 1 and rows[0].alarm == 4


def test_recording_off_writes_nothing(session_env):
    session, model, _tr, rec, mlog, _ = session_env
    session.connect(None)
    session.recording = False
    model.measure()
    assert wait_for(lambda: "data" in rec.kinds())
    assert rec.events[-1][2] is False
    assert mlog.count() == 0


def test_garbage_evt_data_is_never_a_row(session_env):
    session, model, transports, rec, mlog, _ = session_env
    session.connect(None)
    session.recording = True
    transports[0].send("EVT DATA 21x4 4512 10132 85000", "EVT DATA 1 2", "EVT DATA")
    model.measure((2134, 4512, 10132, 85000))
    assert wait_for(lambda: "data" in rec.kinds())
    time.sleep(0.1)
    assert [e for e in rec.events if e[0] == "data"] == [("data", M, True)]
    assert mlog.stats().count == 1


def test_sensor_missing_is_logged_empty_with_flag_16(session_env):
    session, model, _tr, rec, mlog, _ = session_env
    model.sensor = "MISSING"
    model.alarm = model.unacked = 16
    info = session.connect(None)
    assert info.measurement is None and info.status.sensor == "MISSING"
    session.recording = True
    model.measure()
    assert wait_for(lambda: "data" in rec.kinds())
    s = mlog.samples(TimeRange.ALL, now=dt.datetime.now(UTC) + dt.timedelta(seconds=5))[0]
    assert not s.measurement.any_valid and s.alarm == 16


def test_alarm_events_update_flags(session_env):
    session, model, _tr, rec, _mlog, _ = session_env
    session.connect(None)
    model.raise_alarm(1)
    assert wait_for(lambda: ("alarm", 1, True) in rec.events)
    assert session.alarm_flags == 1
    model.set_sensor("MISSING")
    assert wait_for(lambda: ("sensor", "MISSING") in rec.events)
    assert wait_for(lambda: session.alarm_flags == 17)


def test_config_with_interleaved_event(session_env):
    session, model, _tr, rec, _mlog, _ = session_env
    session.connect(None)
    session.recording = True
    model.cfg_interleave = ["EVT DATA 2000 5000 10000 70000"]
    cfg = session.get_config()
    assert cfg["BUZZER"] == 0 and len(cfg) == 7
    assert wait_for(lambda: "data" in rec.kinds())


def test_apply_config_validates_and_reports_german_errors(session_env):
    session, model, _tr, _rec, _mlog, _ = session_env
    session.connect(None)
    assert session.apply_config({"INTERVAL": "30", "T_HI": "28,5", "BUZZER": "1",
                                 "RH_LO": "OFF"}) == []
    assert model.cfg["INTERVAL"] == 30 and model.cfg["T_HI"] == 2850 and model.cfg["BUZZER"] == 1
    errors = session.apply_config({"T_LO": "200", "INTERVAL": "abc"})
    assert len(errors) == 2 and errors[0].startswith("Temperatur unterer Schwellwert")
    session.reset_config()
    assert model.cfg["INTERVAL"] == 10


def test_ack_without_alarm_is_err_7_with_german_text(session_env):
    session, *_ = session_env
    session.connect(None)
    with pytest.raises(DeviceError) as exc:
        session.ack()
    assert exc.value.code == 7
    assert "kein unquittierter Alarm" in describe_error(exc.value)


def test_usb_loss_reports_disconnect(session_env):
    session, _model, transports, rec, _mlog, _ = session_env
    session.connect(None)
    transports[0].fail(OSError("USB getrennt"))
    assert wait_for(lambda: "lost" in rec.kinds())
    assert not session.connected
    with pytest.raises(DeviceDisconnected):
        session.poll()


def test_mid_session_boot_resends_time(session_env):
    session, model, transports, rec, _mlog, _ = session_env
    session.connect(None)
    n_time = sum(1 for w in transports[0].written if w.startswith("TIME "))
    model.reboot()
    assert wait_for(lambda: ("boot", "0.1.0") in rec.events, timeout=5)
    assert sum(1 for w in transports[0].written if w.startswith("TIME ")) == n_time + 1
    assert model.stream is True and model.clock is not None


def test_poll_resyncs_time_and_fails_after_repeated_timeouts(mlog):
    model = FakeUmwelt()
    clock = {"t": 0.0}

    def open_device(port):
        dev = UmweltDevice(FakeTransport(model), timeout=0.3)
        dev.start()
        dev.wait_ready(boot_wait=0.3)
        return dev

    s = DeviceSession(None, mlog, open_device=open_device, monotonic=lambda: clock["t"])
    try:
        s.connect(None)
        model.clock = None
        clock["t"] = 700.0
        s.poll()
        assert model.clock is not None
        model.silent = True
        for _ in range(2):
            with pytest.raises(Exception):  # noqa: B017 - DeviceTimeout
                s.poll()
        with pytest.raises(DeviceDisconnected):
            s.poll()
    finally:
        s.close()


def test_connect_failure_closes_device(mlog):
    model = FakeUmwelt(fw="0.0.1")
    trs = []

    def open_device(port):
        tr = FakeTransport(model)
        trs.append(tr)
        dev = UmweltDevice(tr, timeout=0.3)
        dev.start()
        try:
            dev.wait_ready(boot_wait=0.3)
        except BaseException:
            dev.close()
            raise
        return dev

    from umwelt_ctl.device import FirmwareTooOld

    s = DeviceSession(None, mlog, open_device=open_device)
    with pytest.raises(FirmwareTooOld) as exc:
        s.connect(None)
    assert "zu alt" in describe_error(exc.value)
    assert trs[0].closed and not s.connected


def test_log_error_is_reported_once(session_env, monkeypatch):
    session, model, _tr, rec, mlog, _ = session_env
    from umwelt_panel.core.errors import DatabaseError

    def boom(*_a, **_k):
        raise DatabaseError("Datenbank gesperrt")

    monkeypatch.setattr(mlog, "record", boom)
    session.connect(None)
    session.recording = True
    model.measure()
    model.measure()
    assert wait_for(lambda: rec.kinds().count("data") == 2)
    assert rec.kinds().count("log_error") == 1


@pytest.mark.skipif(sys.platform != "win32", reason="Pfadschema von Windows")
def test_default_database_path_is_local_appdata():
    pytest.importorskip("platformdirs")
    from umwelt_panel.config import database_path

    path = database_path()
    assert path.name == "messwerte.db" and path.parent.name == "Umgebungssensoren"
    assert "AppData" in str(path) and "Roaming" not in str(path)
