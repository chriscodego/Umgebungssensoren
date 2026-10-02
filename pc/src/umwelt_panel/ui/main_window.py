"""Main window: connection banner, alarm banner, tabs „Live" and „Verlauf", log strip.

* Connection banner — always visible: state in colour AND text, port choice, firmware.
* Alarm banner — only with an alarm; blinks while unacknowledged; „Quittieren" sends ACK.
* „Live" — four tiles (temperature, humidity, pressure, gas + trend) with sparklines.
* „Verlauf" — :class:`~umwelt_panel.ui.history_view.HistoryView` (database, export, clear).
* Log strip — automatic recording on/off, number of values, size and path of the database.

No SQL and no serial I/O in here: the device goes through
:class:`~umwelt_panel.ui.device_controller.DeviceController`, the database through the
services (statistics in the thread pool).
"""

from __future__ import annotations

import datetime as _dt
import logging
from importlib import resources

from PySide6.QtCore import QByteArray, Qt, QTimer, Slot
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QSizePolicy,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from umwelt_ctl import protocol as p
from umwelt_ctl.protocol import DeviceStatus, Measurement
from umwelt_panel import APP_NAME, __version__
from umwelt_panel.core.models import LogStats, format_count, format_size
from umwelt_panel.core.services.device_session import ConnectInfo
from umwelt_panel.core.services.log_service import MeasurementLog
from umwelt_panel.core.services.settings_service import SettingsService
from umwelt_panel.core.trend import GasTrend
from umwelt_panel.ui import dialogs
from umwelt_panel.ui.device_controller import (
    STATE_CONNECTED,
    STATE_CONNECTING,
    STATE_DISCONNECTED,
    DeviceController,
)
from umwelt_panel.ui.history_view import HistoryView, error_text
from umwelt_panel.ui.metrics import METRICS
from umwelt_panel.ui.settings_dialog import SettingsDialog
from umwelt_panel.ui.tasks import run_in_pool, wait_for_pool
from umwelt_panel.ui.widgets.alarm_banner import AlarmBanner
from umwelt_panel.ui.widgets.connection_banner import ConnectionBanner
from umwelt_panel.ui.widgets.value_box import ValueBox

log = logging.getLogger(__name__)

BLINK_MS = 500
STATS_MS = 5000
MIN_WIDTH, MIN_HEIGHT = 900, 620

#: alarm flags that mark a tile (SPEC: 1 T_HI, 2 T_LO, 4 RH_HI, 8 RH_LO)
TILE_ALARMS = {"t": p.ALARM_T_HI | p.ALARM_T_LO, "rh": p.ALARM_RH_HI | p.ALARM_RH_LO}


def load_stylesheet() -> str:
    """``ui/resources/app.qss`` via importlib.resources; missing -> native style."""
    try:
        return (resources.files("umwelt_panel.ui.resources").joinpath("app.qss")
                .read_text(encoding="utf-8"))
    except (OSError, ModuleNotFoundError):
        log.warning("Stylesheet app.qss nicht ladbar – native Darstellung")
        return ""


class MainWindow(QMainWindow):
    def __init__(self, controller: DeviceController, log_service: MeasurementLog,
                 settings: SettingsService, *, port: str | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctl = controller
        self._log = log_service
        self._settings = settings
        self._port = port if port is not None else (settings.port() or "")
        self._closing = False

        self._conn_state = STATE_DISCONNECTED
        self._conn_text = ""
        self._info: ConnectInfo | None = None
        self._status: DeviceStatus | None = None
        self._measurement: Measurement | None = None
        self._measured_at: _dt.datetime | None = None
        self._config: dict[str, int | None] = {}
        self._alarm = 0
        self._unacked = 0
        self._trend = GasTrend()
        self._stats: LogStats | None = None
        self._stats_dirty = True
        self._stats_loading = False

        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(MIN_WIDTH, MIN_HEIGHT)
        self._build()
        self._build_menu()
        self._wire()
        self._restore_geometry()
        self._render()

        self._blink = QTimer(self)
        self._blink.setInterval(BLINK_MS)
        self._blink.timeout.connect(self.alarm_banner.toggle_blink)
        self._blink.start()
        self._stats_timer = QTimer(self)
        self._stats_timer.setInterval(STATS_MS)
        self._stats_timer.timeout.connect(self._refresh_stats_if_dirty)
        self._stats_timer.start()

    # ------------------------------------------------------------------ build

    def _build(self) -> None:
        central = QWidget(self)
        root = QVBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 6)
        root.setSpacing(8)

        self.banner = ConnectionBanner(central)
        self.banner.set_ports([], self._port)
        root.addWidget(self.banner)
        self.alarm_banner = AlarmBanner(central)
        root.addWidget(self.alarm_banner)

        self.tabs = QTabWidget(central)
        live = QWidget(self.tabs)
        grid = QGridLayout(live)
        grid.setContentsMargins(4, 8, 4, 4)
        grid.setSpacing(10)
        self.tiles: dict[str, ValueBox] = {}
        for n, (key, metric) in enumerate(METRICS.items()):
            tile = ValueBox(metric.title, metric.min_span, live)
            tile.setObjectName("valueBox")
            self.tiles[key] = tile
            grid.addWidget(tile, n // 2, n % 2)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        self.tabs.addTab(live, self.tr("&Live"))
        self.history = HistoryView(self._log, self._settings, self.tabs)
        self.tabs.addTab(self.history, self.tr("&Verlauf"))
        root.addWidget(self.tabs, 1)

        strip = QFrame(central)
        strip.setObjectName("logStrip")
        strip.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        sl = QHBoxLayout(strip)
        sl.setContentsMargins(10, 6, 10, 6)
        self.auto_log = QCheckBox(self.tr("Messwerte automatisch &aufzeichnen"), strip)
        self.auto_log.setToolTip(self.tr(
            "Solange das Gerät verbunden ist, wird jede Messung in der Datenbank gespeichert. "
            "Es wird nie automatisch etwas gelöscht."))
        self.auto_log.setChecked(self._settings.auto_log())
        sl.addWidget(self.auto_log)
        self.log_stats = QLabel(strip)
        self.log_stats.setObjectName("logStatsLabel")
        self.log_stats.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.log_stats.setWordWrap(True)
        sl.addWidget(self.log_stats, 1)
        root.addWidget(strip)

        self.setCentralWidget(central)
        self.device_label = QLabel(self)
        self.statusBar().addPermanentWidget(self.device_label)

    def _build_menu(self) -> None:
        bar = self.menuBar()
        file_menu = bar.addMenu(self.tr("&Datei"))
        self.export_action = QAction(self.tr("Messwerte als CSV &exportieren …"), self)
        self.export_action.setShortcut(QKeySequence("Ctrl+E"))
        self.export_action.triggered.connect(self._export_from_menu)
        file_menu.addAction(self.export_action)
        file_menu.addSeparator()
        quit_action = QAction(self.tr("&Beenden"), self)
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        dev_menu = bar.addMenu(self.tr("&Gerät"))
        self.settings_action = QAction(self.tr("&Einstellungen …"), self)
        self.settings_action.setShortcut(QKeySequence("Ctrl+,"))
        self.settings_action.triggered.connect(self.open_settings)
        self.ack_action = QAction(self.tr("Alarm &quittieren"), self)
        self.ack_action.setShortcut(QKeySequence("F8"))
        self.ack_action.triggered.connect(self.acknowledge)
        self.sync_action = QAction(self.tr("&Uhr synchronisieren"), self)
        self.sync_action.triggered.connect(self._ctl.sync_time)
        for a in (self.settings_action, self.ack_action, self.sync_action):
            dev_menu.addAction(a)

        help_menu = bar.addMenu(self.tr("&Hilfe"))
        about = QAction(self.tr("Ü&ber …"), self)
        about.triggered.connect(self._about)
        help_menu.addAction(about)

    def _wire(self) -> None:
        b = self.banner
        b.connect_requested.connect(self._on_connect_clicked)
        b.disconnect_requested.connect(self._ctl.disconnect_device)
        b.settings_requested.connect(self.open_settings)
        b.ports_requested.connect(self._ctl.scan_ports)
        self.alarm_banner.ack_requested.connect(self.acknowledge)
        self.auto_log.toggled.connect(self._on_auto_log)
        self.history.log_changed.connect(self.refresh_stats)
        self.history.message.connect(self._say)

        c = self._ctl
        c.state_changed.connect(self._on_state)
        c.connected.connect(self._on_connected)
        c.connect_failed.connect(self._on_connect_failed)
        c.disconnected.connect(self._on_disconnected)
        c.status.connect(self._on_status)
        c.measurement.connect(self._on_measurement)
        c.alarm.connect(self._on_alarm)
        c.sensor.connect(self._on_sensor)
        c.booted.connect(self._on_booted)
        c.config_loaded.connect(self._on_config)
        c.ports.connect(self._on_ports)
        c.done.connect(self._say)
        c.failed.connect(self._on_failed)
        c.log_error.connect(self._on_log_error)
        c.set_recording(self.auto_log.isChecked())

    def start(self) -> None:
        """Begin auto-connecting; call after ``show()`` (errors land in a visible window)."""
        self._ctl.start(self._port)
        self.refresh_stats()

    # ------------------------------------------------------------------ geometry

    def _restore_geometry(self) -> None:
        geometry = self._settings.window_geometry()
        if geometry:
            self.restoreGeometry(QByteArray.fromBase64(geometry.encode("ascii")))
        else:
            self.resize(1040, 720)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - Qt override
        if not self._closing:
            self._closing = True
            self._blink.stop()
            self._stats_timer.stop()
            try:
                self._settings.set_window_geometry(
                    bytes(self.saveGeometry().toBase64().data()).decode("ascii"))
            except Exception:  # never block closing for a window position
                log.warning("Fenstergeometrie nicht gespeichert", exc_info=True)
            self._ctl.shutdown()   # closes the port in the worker thread
            wait_for_pool(5000)
        super().closeEvent(event)

    # ------------------------------------------------------------------ actions

    @Slot(str)
    def _on_connect_clicked(self, port: str) -> None:
        self._port = port
        try:
            self._settings.set_port(port or None)
        except Exception:
            log.warning("Port nicht gespeichert", exc_info=True)
        self._ctl.connect_device(port)

    @Slot()
    def acknowledge(self) -> None:
        if self._conn_state != STATE_CONNECTED:
            self._say(self.tr("Keine Verbindung zum Gerät."))
            return
        self._ctl.ack()

    @Slot()
    def open_settings(self) -> None:
        if self._conn_state != STATE_CONNECTED or not self._config:
            dialogs.show_error(self, self.tr("Nicht verbunden"),
                               self.tr("Die Einstellungen liegen auf dem Gerät. Bitte zuerst "
                                       "verbinden (USB-Kabel prüfen)."))
            return
        dlg = SettingsDialog(self._config, sync_time=self._ctl.sync_time,
                             reset_config=self._ctl.reset_config, parent=self)
        self._settings_dialog = dlg
        if dlg.exec() == QDialog.DialogCode.Accepted:
            changes = dlg.changes()
            if changes:
                self._say(self.tr("Sende Einstellungen …"))
                self._ctl.apply_config(changes)
            else:
                self._say(self.tr("Keine Änderung."))
        self._settings_dialog = None

    @Slot(bool)
    def _on_auto_log(self, on: bool) -> None:
        try:
            self._settings.set_auto_log(on)
        except Exception as exc:
            log.warning("Einstellung nicht gespeichert: %s", exc)
        self._ctl.set_recording(on)
        self._render_log_strip()

    @Slot()
    def _export_from_menu(self) -> None:
        self.tabs.setCurrentWidget(self.history)
        self.history.export_csv()

    @Slot()
    def _about(self) -> None:
        dialogs.show_info(self, self.tr("Über {0}").format(APP_NAME), self.tr(
            "{0} Control Panel {1}\n\nMesswert-Datenbank:\n{2}\n\nProtokoll: docs/SPEC.md "
            "(Version 1).").format(APP_NAME, __version__, self._log.path))

    def _say(self, text: str) -> None:
        self.statusBar().showMessage(text, 8000)

    # ------------------------------------------------------------------ controller events

    @Slot(str, str)
    def _on_state(self, state: str, text: str) -> None:
        self._conn_state = state
        self._conn_text = text
        if state != STATE_CONNECTED:
            self._status = None
            self._info = None
        self._render()

    @Slot(object)
    def _on_connected(self, info: ConnectInfo) -> None:
        self._info = info
        self._config = dict(info.config)
        self._measurement = info.measurement
        self._measured_at = _dt.datetime.now() if info.measurement else None
        self._trend.reset()
        if info.measurement is not None:
            self._trend.update(info.measurement.gas)
        self._on_status(info.status)
        self._say(self.tr("Verbunden mit {0} (Firmware {1}); Uhr gestellt.").format(
            info.port, info.fw_version))

    @Slot(str, bool, bool)
    def _on_connect_failed(self, message: str, fatal: bool, manual: bool) -> None:
        self._say(self.tr("Verbindung fehlgeschlagen: {0}").format(message))
        if fatal or manual:
            dialogs.show_error(self, self.tr("Verbindung fehlgeschlagen"), message)

    @Slot(str)
    def _on_disconnected(self, reason: str) -> None:
        self._say(reason)

    @Slot(object)
    def _on_status(self, st: DeviceStatus) -> None:
        if self._conn_state != STATE_CONNECTED:
            return
        self._status = st
        self._alarm, self._unacked = st.alarm_flags, st.unacked_flags
        if st.sensor == p.SENSOR_MISSING:
            self._measurement = None
        self._render()

    @Slot(object, object, bool)
    def _on_measurement(self, m: Measurement, ts: _dt.datetime, logged: bool) -> None:
        self._measurement = m
        self._measured_at = ts
        self._trend.update(m.gas)
        for key, metric in METRICS.items():
            self.tiles[key].append_history(metric.value(m))
        if logged:
            self._stats_dirty = True
        self._render()

    @Slot(int, bool)
    def _on_alarm(self, flag: int, active: bool) -> None:
        text = p.ALARM_TEXT_DE.get(flag, str(flag))
        if active:
            self._alarm |= flag
            self._unacked |= flag
            self._say(self.tr("Alarm: {0}").format(text))
            if self.isActiveWindow() is False:
                self.activateWindow()
        else:
            self._alarm &= ~flag
            self._unacked &= ~flag
            self._say(self.tr("Alarm beendet: {0}").format(text))
        self._render()
        self._ctl.refresh_status()

    @Slot(str)
    def _on_sensor(self, state: str) -> None:
        self._say(p.SENSOR_TEXT_DE.get(state, state))
        self._ctl.refresh_status()

    @Slot(str)
    def _on_booted(self, fw: str) -> None:
        self._say(self.tr("Gerät wurde neu gestartet (Firmware {0}) – Uhr und Datenstrom neu "
                          "gesetzt.").format(fw or "?"))
        self._ctl.refresh_status()
        self._ctl.load_config()

    @Slot(object)
    def _on_config(self, cfg: dict[str, int | None]) -> None:
        self._config = dict(cfg)

    @Slot(list)
    def _on_ports(self, ports: list[str]) -> None:
        self.banner.set_ports(ports, self.banner.selected_port() or self._port)

    @Slot(str, str)
    def _on_failed(self, title: str, message: str) -> None:
        self._say(f"{title}: {message}")
        dialogs.show_error(self, title, message)

    @Slot(str)
    def _on_log_error(self, message: str) -> None:
        self._say(self.tr("Messwert nicht gespeichert: {0}").format(message))
        dialogs.show_error(self, self.tr("Aufzeichnung gestört"), message)

    # ------------------------------------------------------------------ statistics

    @Slot()
    def refresh_stats(self) -> None:
        if self._stats_loading or self._closing:
            self._stats_dirty = True
            return
        self._stats_loading = True
        self._stats_dirty = False

        def ok(stats: LogStats) -> None:
            self._stats_loading = False
            self._stats = stats
            self.history.set_stats(stats)
            self._render_log_strip()

        def err(exc: BaseException) -> None:
            self._stats_loading = False
            self.log_stats.setText(self.tr("Log nicht lesbar: {0}").format(error_text(exc)))

        run_in_pool(self._log.stats, ok, err)

    @Slot()
    def _refresh_stats_if_dirty(self) -> None:
        if self._stats_dirty:
            self.refresh_stats()

    # ------------------------------------------------------------------ rendering

    def view_state(self) -> str:
        """``getrennt`` / ``laden`` / ``sensorfehler`` / ``werte`` (for tests too)."""
        if self._conn_state != STATE_CONNECTED:
            return "getrennt"
        if self._status is None:
            return "laden"
        if self._status.sensor != p.SENSOR_OK and (self._measurement is None
                                                   or not self._measurement.any_valid):
            return "sensorfehler"
        return "werte"

    def _render(self) -> None:
        self._render_banner()
        self._render_tiles()
        self._render_alarm()
        self._render_log_strip()
        connected = self._conn_state == STATE_CONNECTED
        for a in (self.settings_action, self.sync_action):
            a.setEnabled(connected)
        self.ack_action.setEnabled(connected and bool(self._unacked))

    def _render_banner(self) -> None:
        st = self._status
        if self._conn_state == STATE_CONNECTED:
            info = self._info
            parts = [info.port if info else "?"]
            if info and info.fw_version:
                parts.append(self.tr("Firmware {0}").format(info.fw_version))
            if st is not None:
                parts.append(st.sensor_text)
            detail = " · ".join(parts)
            if st is not None and st.sensor != p.SENSOR_OK:
                self.banner.show_state("warning", self.tr("Verbunden – {0}").format(
                    st.sensor_text), detail, connected=True)
            else:
                self.banner.show_state("ok", self.tr("Verbunden"), detail, connected=True)
        elif self._conn_state == STATE_CONNECTING:
            where = self._conn_text or self.tr("automatisch erkanntem Port")
            self.banner.show_state("busy", self.tr("Verbinde mit {0} …").format(where), "",
                                   connected=False, busy=True)
        elif not self._ctl.auto_connect:
            self.banner.show_state("idle", self.tr("Getrennt"), self._conn_text,
                                   connected=False)
        else:
            self.banner.show_state(
                "error", self.tr("Nicht verbunden – warte auf das Gerät …"),
                self._conn_text or self.tr("USB-Kabel einstecken; die Verbindung wird "
                                           "automatisch aufgebaut."), connected=False)
        if st is not None and self._conn_state == STATE_CONNECTED:
            self.device_label.setText(self.tr("{0} · Intervall {1} s · Laufzeit {2}").format(
                st.sensor_text, st.interval, p.format_uptime(st.uptime_sec)))
        else:
            self.device_label.setText(self.tr("Keine Verbindung zum Gerät"))

    def _render_tiles(self) -> None:
        state = self.view_state()
        m = self._measurement
        for key, tile in self.tiles.items():
            tile.set_alarm(state != "getrennt" and bool(self._alarm & TILE_ALARMS.get(key, 0)))
        if state == "getrennt":
            text = self.tr("Verbinde …") if self._conn_state == STATE_CONNECTING else self.tr(
                "keine Verbindung")
            for tile in self.tiles.values():
                tile.show_placeholder(text)
            return
        if state == "laden":
            for tile in self.tiles.values():
                tile.show_placeholder(self.tr("lade Werte vom Gerät"), text="…")
            return
        if state == "sensorfehler":
            assert self._status is not None
            for tile in self.tiles.values():
                tile.show_placeholder(self._status.sensor_text, error=True)
            return
        if m is None or not m.any_valid:
            for tile in self.tiles.values():
                tile.show_placeholder(self.tr("noch keine gültige Messung"))
            return
        when = (self.tr("gemessen {0:%H:%M:%S}").format(self._measured_at)
                if self._measured_at else "")
        for key, metric in METRICS.items():
            valid = metric.value(m) is not None
            sub = when
            if key == "gas" and valid and self._trend.text():
                sub = f"{self._trend.text()} · {when}" if when else self._trend.text()
            self.tiles[key].show_value(metric.text(m), sub if valid else self.tr("ungültig"),
                                       valid=valid)

    def _render_alarm(self) -> None:
        flags = self._alarm if self._conn_state == STATE_CONNECTED else 0
        if not flags:
            self.alarm_banner.clear()
            return
        self.alarm_banner.show_alarm(p.alarm_texts(flags), bool(self._unacked & flags))

    def _render_log_strip(self) -> None:
        stats = self._stats
        if stats is None:
            text = self.tr("Datenbank: {0}").format(self._log.path)
        else:
            text = self.tr("{0} Messwerte · {1} · {2}").format(
                format_count(stats.count), format_size(stats.size_bytes), stats.path)
        if not self.auto_log.isChecked():
            state = self.tr("Aufzeichnung aus")
        elif self._conn_state == STATE_CONNECTED:
            state = self.tr("Aufzeichnung läuft")
        else:
            state = self.tr("Aufzeichnung wartet auf das Gerät")
        self.log_stats.setText(f"{state} — {text}")

    # ------------------------------------------------------------------ test helpers

    def connection_state(self) -> str:
        return self._conn_state

    def alarm_flags(self) -> tuple[int, int]:
        return self._alarm, self._unacked

    def config(self) -> dict[str, int | None]:
        return dict(self._config)

    def stats(self) -> LogStats | None:
        return self._stats
