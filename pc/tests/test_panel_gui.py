"""Control Panel GUI (PROJ-8) against the fake device — PySide6 offscreen, no hardware."""

from __future__ import annotations

import datetime as dt

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtWidgets import QApplication, QDialog, QMessageBox  # noqa: E402

from umwelt_ctl.device import UmweltDevice  # noqa: E402
from umwelt_ctl.protocol import Measurement  # noqa: E402
from umwelt_panel.core.models import TimeRange  # noqa: E402
from umwelt_panel.core.services.log_service import MeasurementLog  # noqa: E402
from umwelt_panel.core.services.settings_service import SettingsService  # noqa: E402
from umwelt_panel.data.db import Database  # noqa: E402
from umwelt_panel.ui import device_controller as dc_mod  # noqa: E402
from umwelt_panel.ui import dialogs  # noqa: E402
from umwelt_panel.ui import settings_dialog as sd_mod  # noqa: E402
from umwelt_panel.ui.device_controller import DeviceController  # noqa: E402
from umwelt_panel.ui.main_window import MainWindow, load_stylesheet  # noqa: E402
from umwelt_panel.ui.settings_dialog import SettingsDialog  # noqa: E402

from conftest import FakeTransport, FakeUmwelt  # noqa: E402

pytestmark = pytest.mark.gui

WAIT = 5000


class Env:
    def __init__(self, qtbot, tmp_path, monkeypatch, auto_log=True):
        self.qtbot = qtbot
        self.model = FakeUmwelt()
        self.transports: list[FakeTransport] = []
        self.plugged = True
        self.dialogs: list[tuple[str, str, str]] = []
        self.confirm = True
        self.save_path = str(tmp_path / "export_messwerte.csv")

        monkeypatch.setattr(dc_mod, "RECONNECT_MS", 100)
        monkeypatch.setattr(dc_mod, "RETRY_AFTER_FAIL_S", 0.2)
        monkeypatch.setattr(dialogs, "show_error",
                            lambda _p, t, m: self.dialogs.append(("error", t, m)))
        monkeypatch.setattr(dialogs, "show_info",
                            lambda _p, t, m: self.dialogs.append(("info", t, m)))
        monkeypatch.setattr(dialogs, "ask_yes_no",
                            lambda _p, t, m: self.dialogs.append(("ask", t, m)) or self.confirm)
        monkeypatch.setattr(dialogs, "save_file_name", lambda _p, _t, _s: self.save_path)

        self.db = Database(tmp_path / "messwerte.db")
        self.db.open()
        self.log = MeasurementLog(self.db)
        self.settings = SettingsService(self.db)
        self.settings.set_auto_log(auto_log)
        self.controller = DeviceController(self.log, open_device=self.open_device,
                                           scan_ports=self.scan)
        QApplication.instance().setStyleSheet(load_stylesheet())
        self.window = MainWindow(self.controller, self.log, self.settings)
        qtbot.addWidget(self.window)
        self.window.show()

    def scan(self):
        return ["COM99"] if self.plugged else []

    def open_device(self, port):
        if not self.plugged:
            from umwelt_ctl.device import DeviceDisconnected
            raise DeviceDisconnected("Kein Arduino (USB-VID 0x2341) gefunden.")
        tr = FakeTransport(self.model)
        tr.port = port or "COM99"
        self.transports.append(tr)
        dev = UmweltDevice(tr, timeout=0.5)
        dev.start()
        try:
            dev.wait_ready(boot_wait=0.5)
        except BaseException:
            dev.close()
            raise
        return dev

    def start(self):
        self.window.start()
        self.wait_connected()

    def wait_connected(self):
        self.qtbot.waitUntil(lambda: self.window.connection_state() == "verbunden"
                             and self.window.view_state() != "laden", timeout=WAIT)

    def close(self):
        self.window.close()


@pytest.fixture
def env(qtbot, tmp_path, monkeypatch):
    e = Env(qtbot, tmp_path, monkeypatch)
    yield e
    e.close()


def test_connects_automatically_and_shows_values(env):
    w = env.window
    assert w.view_state() == "getrennt"
    assert "keine Verbindung" in w.tiles["t"].sub_text()
    env.start()
    assert w.banner.severity() == "ok"
    assert w.banner.message() == "Verbunden"
    assert "Firmware 0.1.0" in w.banner.detail() and "COM99" in w.banner.detail()
    assert w.tiles["t"].value_text() == "21,34 °C"
    assert w.tiles["rh"].value_text() == "45,12 % rF"
    assert w.tiles["p"].value_text() == "1013,2 hPa"
    assert w.tiles["gas"].value_text() == "85,0 kΩ"
    assert env.model.stream is True and env.model.clock is not None
    assert w.banner.button().text() == "&Trennen"


def test_evt_data_updates_tiles_sparkline_and_log(env):
    env.start()
    w = env.window
    env.model.measure((2250, 5000, 10100, 120000))
    env.qtbot.waitUntil(lambda: w.tiles["t"].value_text() == "22,50 °C", timeout=WAIT)
    assert w.tiles["t"].sparkline().values() == (22.5,)
    assert "↑ steigend" in w.tiles["gas"].sub_text()
    env.qtbot.waitUntil(lambda: env.log.count() == 1, timeout=WAIT)
    w.refresh_stats()
    env.qtbot.waitUntil(lambda: w.stats() is not None and w.stats().count == 1, timeout=WAIT)
    assert "1 Messwerte" in w.log_stats.text()
    assert "Aufzeichnung läuft" in w.log_stats.text()
    assert str(env.db.path) in w.log_stats.text()


def test_invalid_value_shows_dashes_never_zero(env):
    env.start()
    w = env.window
    env.model.measure((2134, "-", 10132, "-"))
    env.qtbot.waitUntil(lambda: w.tiles["rh"].sub_text() == "ungültig", timeout=WAIT)
    assert w.tiles["rh"].value_text() == "--"
    assert w.tiles["gas"].value_text() == "--"
    env.qtbot.waitUntil(lambda: env.log.count() == 1, timeout=WAIT)
    s = env.log.samples(TimeRange.ALL, now=dt.datetime.now(dt.UTC) + dt.timedelta(seconds=5))
    assert s[0].measurement.rh is None and s[0].measurement.gas is None


def test_auto_log_off_records_nothing(env):
    env.window.auto_log.setChecked(False)
    assert env.settings.auto_log() is False
    env.start()
    env.model.measure((2300, 5000, 10100, 90000))
    env.qtbot.waitUntil(lambda: env.window.tiles["t"].value_text() == "23,00 °C", timeout=WAIT)
    assert env.log.count() == 0
    assert "Aufzeichnung aus" in env.window.log_stats.text()


def test_alarm_banner_and_acknowledge(env):
    env.start()
    w = env.window
    assert not w.alarm_banner.isVisible()
    env.model.raise_alarm(1)
    env.qtbot.waitUntil(lambda: w.alarm_banner.isVisible(), timeout=WAIT)
    assert "Temperatur zu hoch" in w.alarm_banner.message()
    assert "nicht quittiert" in w.alarm_banner.message()
    assert w.tiles["t"].property("alarm") is True
    assert w.alarm_banner.button().isEnabled()
    w.alarm_banner.button().click()
    env.qtbot.waitUntil(lambda: "ACK" in env.transports[0].written, timeout=WAIT)
    env.qtbot.waitUntil(lambda: w.alarm_flags() == (1, 0), timeout=WAIT)
    assert "(quittiert)" in w.alarm_banner.message()
    assert not w.alarm_banner.button().isEnabled()
    env.model.alarm = env.model.unacked = 0
    env.model.emit("EVT ALARM 1 0")
    env.qtbot.waitUntil(lambda: not w.alarm_banner.isVisible(), timeout=WAIT)


def test_sensor_missing_state(env):
    env.model.sensor = "MISSING"
    env.model.alarm = env.model.unacked = 16
    env.start()
    w = env.window
    assert w.view_state() == "sensorfehler"
    assert w.banner.severity() == "warning"
    assert "Sensor nicht erreichbar" in w.banner.message()
    assert w.tiles["t"].value_text() == "--"
    assert "Sensor nicht erreichbar" in w.tiles["t"].sub_text()
    assert "keine Messdaten" in w.alarm_banner.message()


def test_usb_loss_and_automatic_reconnect(env):
    env.start()
    w = env.window
    env.plugged = False
    env.transports[0].fail(OSError("USB getrennt"))
    env.qtbot.waitUntil(lambda: w.connection_state() != "verbunden", timeout=WAIT)
    env.qtbot.waitUntil(lambda: w.banner.severity() == "error", timeout=WAIT)
    assert "warte auf das Gerät" in w.banner.message()
    assert w.tiles["t"].value_text() == "--"
    assert env.transports[0].closed
    assert not [d for d in env.dialogs if d[0] == "error"]  # no dialog for an automatic retry
    env.plugged = True
    env.wait_connected()
    assert len(env.transports) == 2
    assert env.model.stream is True


def test_mid_session_boot_resyncs(env):
    env.start()
    n = sum(1 for x in env.transports[0].written if x.startswith("TIME "))
    env.model.reboot()
    env.qtbot.waitUntil(
        lambda: sum(1 for x in env.transports[0].written if x.startswith("TIME ")) == n + 1,
        timeout=WAIT)
    env.qtbot.waitUntil(lambda: "neu gestartet" in env.window.statusBar().currentMessage(),
                        timeout=WAIT)
    assert env.window.connection_state() == "verbunden"


def test_disconnect_button_stays_disconnected(env):
    env.start()
    w = env.window
    w.banner.button().click()
    env.qtbot.waitUntil(lambda: env.transports[0].closed, timeout=WAIT)
    assert w.banner.severity() == "idle"
    env.qtbot.wait(400)
    assert len(env.transports) == 1  # no automatic reconnect after „Trennen"
    w.banner.button().click()
    env.wait_connected()
    assert len(env.transports) == 2


def test_close_window_releases_port(env):
    env.start()
    env.window.close()
    assert env.transports[0].closed
    assert env.model.stream is False


def test_settings_dialog_sends_only_changes(env, monkeypatch):
    env.start()
    w = env.window

    def fake_exec(dlg):
        dlg.interval.setValue(30)
        dlg.thresholds["T_HI"].active.setChecked(True)
        dlg.thresholds["T_HI"].value.setValue(28.5)
        dlg.buzzer.setChecked(True)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(SettingsDialog, "exec", fake_exec)
    w.open_settings()
    env.qtbot.waitUntil(lambda: env.model.cfg["BUZZER"] == 1, timeout=WAIT)
    assert env.model.cfg["INTERVAL"] == 30 and env.model.cfg["T_HI"] == 2850
    cfg_cmds = [x for x in env.transports[0].written if x.startswith("CFG ")]
    assert sorted(cfg_cmds) == ["CFG BUZZER 1", "CFG INTERVAL 30", "CFG T_HI 2850"]
    env.qtbot.waitUntil(lambda: w.config().get("INTERVAL") == 30, timeout=WAIT)


def test_settings_device_error_is_german_dialog(env, monkeypatch):
    env.start()
    env.model.cfg["T_HI"] = 2000

    def fake_exec(dlg):
        dlg.thresholds["T_LO"].active.setChecked(True)
        dlg.thresholds["T_LO"].value.setValue(25)  # device refuses it (scripted ERR 3)
        return QDialog.DialogCode.Accepted

    original = env.model.__call__

    def refuse(cmd):
        if cmd.startswith("CFG T_LO"):
            return ["ERR 3 range"]
        return original(cmd)

    for tr in env.transports:
        tr.handler = refuse
    monkeypatch.setattr(SettingsDialog, "exec", fake_exec)
    env.window.open_settings()
    env.qtbot.waitUntil(lambda: any(d[0] == "error" for d in env.dialogs), timeout=WAIT)
    title, msg = [d[1:] for d in env.dialogs if d[0] == "error"][0]
    assert "nicht übernommen" in title
    assert "Wert außerhalb des erlaubten Bereichs" in msg


def test_config_reset_needs_confirmation(env, monkeypatch):
    env.start()
    env.model.cfg["INTERVAL"] = 60
    env.controller.load_config()
    env.qtbot.waitUntil(lambda: env.window.config().get("INTERVAL") == 60, timeout=WAIT)
    answers = iter([QMessageBox.StandardButton.No, QMessageBox.StandardButton.Yes])
    monkeypatch.setattr(sd_mod.QMessageBox, "question", lambda *a, **k: next(answers))
    dlg = SettingsDialog(env.window.config(), sync_time=env.controller.sync_time,
                         reset_config=env.controller.reset_config, parent=env.window)
    env.qtbot.addWidget(dlg)
    dlg.reset_button.click()   # "Nein"
    env.qtbot.wait(200)
    assert env.model.cfg["INTERVAL"] == 60 and not dlg.reset_requested
    dlg.reset_button.click()   # "Ja"
    env.qtbot.waitUntil(lambda: env.model.cfg["INTERVAL"] == 10, timeout=WAIT)
    assert "CFG RESET" in env.transports[0].written
    env.qtbot.waitUntil(lambda: env.window.config().get("INTERVAL") == 10, timeout=WAIT)


def test_sync_time_from_dialog(env):
    env.start()
    env.model.clock = None
    dlg = SettingsDialog(env.window.config(), sync_time=env.controller.sync_time,
                         reset_config=env.controller.reset_config, parent=env.window)
    env.qtbot.addWidget(dlg)
    dlg.sync_button.click()
    env.qtbot.waitUntil(lambda: env.model.clock is not None, timeout=WAIT)
    env.qtbot.waitUntil(lambda: "Geräteuhr" in env.window.statusBar().currentMessage(),
                        timeout=WAIT)


def test_settings_unavailable_when_disconnected(env):
    env.window.open_settings()
    assert env.dialogs and env.dialogs[0][1] == "Nicht verbunden"


def test_history_view_export_and_clear(env, tmp_path):
    now = dt.datetime.now(dt.UTC)
    for i in range(30):
        env.log.record(Measurement(2000 + i, 4000, 10100, 80000), 0,
                       now - dt.timedelta(minutes=30 - i))
    env.log.record(Measurement(1500, 4000, 10100, 80000), 0, now - dt.timedelta(days=3))
    w = env.window
    h = w.history
    h.range_combo.setCurrentIndex(h.range_combo.findData("1h"))
    w.tabs.setCurrentWidget(h)
    env.qtbot.waitUntil(lambda: len(h.chart.points()) == 30 and not h.is_loading(),
                        timeout=WAIT)
    assert h.chart.points()[0][1] == pytest.approx(20.0)
    h.metric_combo.setCurrentIndex(h.metric_combo.findData("p"))
    assert h.chart.points()[0][1] == pytest.approx(1010.0)
    assert env.settings.history_metric() == "p"
    assert env.settings.history_range() is TimeRange.HOUR

    h.export_button.click()
    env.qtbot.waitUntil(lambda: any(d[0] == "info" for d in env.dialogs), timeout=WAIT)
    lines = open(env.save_path, encoding="utf-8-sig").read().splitlines()
    assert lines[0] == "zeit;temperatur_c;feuchte_proz;druck_hpa;gas_ohm;alarm"
    assert len(lines) == 31 and lines[1].split(";")[1:] == ["20,00", "40,00", "1010,0",
                                                              "80000", "0"]

    env.confirm = False
    h.clear_button.click()
    assert env.log.count() == 31
    env.confirm = True
    h.clear_button.click()
    env.qtbot.waitUntil(lambda: env.log.count() == 0, timeout=WAIT)
    env.qtbot.waitUntil(lambda: h.chart.placeholder().startswith("Keine Messwerte"),
                        timeout=WAIT)
    asks = [d for d in env.dialogs if d[0] == "ask"]
    assert len(asks) == 2 and "endgültig gelöscht" in asks[0][2]


def test_history_range_all_and_empty_state(env):
    h = env.window.history
    env.window.tabs.setCurrentWidget(h)
    env.qtbot.waitUntil(lambda: not h.is_loading(), timeout=WAIT)
    assert h.chart.placeholder().startswith("Keine Messwerte")
    env.log.record(Measurement(2100, None, None, None), 0,
                   dt.datetime.now(dt.UTC) - dt.timedelta(days=40))
    h.range_combo.setCurrentIndex(h.range_combo.findData("all"))
    env.qtbot.waitUntil(lambda: len(h.chart.points()) == 1 and not h.is_loading(),
                        timeout=WAIT)


def test_firmware_too_old_is_reported_once(qtbot, tmp_path, monkeypatch):
    e = Env(qtbot, tmp_path, monkeypatch)
    e.model.fw = "0.0.1"
    try:
        e.window.start()
        qtbot.waitUntil(lambda: any(d[0] == "error" for d in e.dialogs), timeout=WAIT)
        assert "zu alt" in e.dialogs[0][2]
        qtbot.wait(500)
        assert len(e.transports) == 1  # no retry loop
        assert e.window.banner.severity() == "idle"
    finally:
        e.close()


def test_main_entry_rejects_bad_database(tmp_path, monkeypatch):
    from umwelt_panel import app

    bad = tmp_path / "kaputt.db"
    bad.write_bytes(b"keine datenbank" * 200)
    shown = []
    monkeypatch.setattr("PySide6.QtWidgets.QMessageBox.exec",
                        lambda self: shown.append(self.text()))
    monkeypatch.setattr("umwelt_panel.logging_setup.setup_logging", lambda: None)
    assert app.main(["--db", str(bad)]) == 1
    assert shown and "keine gültige Messwert-Datenbank" in shown[0]
