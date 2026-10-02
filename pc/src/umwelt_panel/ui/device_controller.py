"""Serial I/O off the GUI thread: a worker object in its own ``QThread`` plus a controller.

* :class:`SerialWorker` lives in the worker thread and owns the Qt-free
  :class:`~umwelt_panel.core.services.device_session.DeviceSession`. Its slots are only ever
  invoked through queued signals; results go back as signals.
* Device events arrive in the dispatcher thread of ``umwelt_ctl.device`` and are emitted as
  signals as well — Qt queues them into the GUI thread. No widget is touched outside the
  GUI thread and the GUI thread never waits for the device.
* :class:`DeviceController` lives in the GUI thread: connection state, automatic
  reconnect (USB unplugged, board reset), status polling. The UI talks only to it.
"""

from __future__ import annotations

import datetime as _dt
import logging
import time
from collections.abc import Callable

from PySide6.QtCore import QObject, QThread, QTimer, Signal, Slot

from umwelt_ctl.device import (
    DeviceDisconnected,
    FirmwareTooOld,
    UmweltDevice,
    find_ports,
)
from umwelt_ctl.protocol import ERR_WRONG_STATE, DeviceError, Measurement
from umwelt_panel.core.services.device_session import (
    DeviceSession,
    OpenDevice,
    SessionListener,
    describe_error,
)
from umwelt_panel.core.services.log_service import MeasurementLog

log = logging.getLogger(__name__)

POLL_MS = 5000          # STATUS (alarm flags, uptime) while connected
RECONNECT_MS = 2000     # look for the device while disconnected
RETRY_AFTER_FAIL_S = 6.0
SHUTDOWN_WAIT_MS = 6000

STATE_DISCONNECTED = "getrennt"
STATE_CONNECTING = "verbinde"
STATE_CONNECTED = "verbunden"


def default_scan() -> list[str]:
    return [device for device, _ in find_ports()]


class _Listener(SessionListener):
    """Turns session callbacks (dispatcher thread) into worker signals."""

    def __init__(self, worker: SerialWorker) -> None:
        self._w = worker

    def on_measurement(self, m: Measurement, ts: _dt.datetime, logged: bool) -> None:
        self._w.measurement.emit(m, ts, logged)

    def on_log_error(self, message: str) -> None:
        self._w.log_error.emit(message)

    def on_alarm(self, flag: int, active: bool) -> None:
        self._w.alarm.emit(flag, active)

    def on_sensor(self, state: str) -> None:
        self._w.sensor.emit(state)

    def on_boot(self, fw_version: str) -> None:
        self._w.booted.emit(fw_version)

    def on_disconnected(self, reason: str) -> None:
        self._w.disconnected.emit(reason)


class SerialWorker(QObject):
    connected = Signal(object)            # ConnectInfo
    connect_failed = Signal(str, bool)    # German message, fatal (no automatic retry)
    disconnected = Signal(str)
    status = Signal(object)               # DeviceStatus
    measurement = Signal(object, object, bool)  # Measurement, local datetime, logged
    alarm = Signal(int, bool)
    sensor = Signal(str)
    booted = Signal(str)
    config_loaded = Signal(object)        # dict[str, int | None]
    ports = Signal(list)
    done = Signal(str)                    # success message for the status bar
    failed = Signal(str, str)             # title, German message
    log_error = Signal(str)

    def __init__(self, log_service: MeasurementLog | None, open_device: OpenDevice | None,
                 scan_ports: Callable[[], list[str]]) -> None:
        super().__init__()
        self._scan = scan_ports
        self.session = DeviceSession(_Listener(self), log_service,
                                     open_device=open_device or UmweltDevice.open)

    @Slot(str)
    def connect_device(self, port: str) -> None:
        try:
            info = self.session.connect(port or None)
        except FirmwareTooOld as exc:
            self.connect_failed.emit(str(exc), True)
        except Exception as exc:  # expected: port busy, not found, timeout, ERR
            log.info("Verbindung fehlgeschlagen: %s", exc)
            self.connect_failed.emit(describe_error(exc), False)
        else:
            self.connected.emit(info)

    @Slot()
    def disconnect_device(self) -> None:
        self.session.close()

    @Slot()
    def poll(self) -> None:
        if not self.session.connected:
            return
        try:
            self.status.emit(self.session.poll())
        except DeviceDisconnected as exc:
            self.session.close()
            self.disconnected.emit(describe_error(exc))
        except Exception as exc:
            log.debug("STATUS fehlgeschlagen: %s", exc)

    @Slot()
    def scan_ports(self) -> None:
        try:
            self.ports.emit(list(self._scan()))
        except Exception as exc:  # pragma: no cover - pyserial enumeration problem
            log.warning("Portliste nicht lesbar: %s", exc)

    @Slot(bool)
    def set_recording(self, on: bool) -> None:
        self.session.recording = bool(on)

    def _run(self, title: str, fn: Callable[[], str | None]) -> None:
        try:
            msg = fn()
        except DeviceDisconnected as exc:
            self.session.close()
            self.failed.emit(title, describe_error(exc))
            self.disconnected.emit(describe_error(exc))
        except Exception as exc:
            self.failed.emit(title, describe_error(exc))
        else:
            if isinstance(msg, str) and msg:
                self.done.emit(msg)

    @Slot()
    def ack(self) -> None:
        def job() -> str:
            try:
                self.session.ack()
                text = "Alarm quittiert."
            except DeviceError as exc:
                if exc.code != ERR_WRONG_STATE:
                    raise
                text = "Kein unquittierter Alarm."
            self.status.emit(self.session.status())
            return text

        self._run("Quittieren fehlgeschlagen", job)

    @Slot(object)
    def apply_config(self, changes: dict[str, str]) -> None:
        def job() -> str | None:
            errors = self.session.apply_config(changes)
            self.config_loaded.emit(self.session.get_config())
            self.status.emit(self.session.status())
            if errors:
                self.failed.emit("Einstellungen nicht übernommen", "\n".join(errors))
                return None
            return "Einstellungen auf dem Gerät gespeichert."

        self._run("Einstellungen nicht übernommen", job)

    @Slot()
    def reset_config(self) -> None:
        def job() -> str:
            self.session.reset_config()
            self.config_loaded.emit(self.session.get_config())
            self.status.emit(self.session.status())
            return "Einstellungen auf Standardwerte zurückgesetzt."

        self._run("Zurücksetzen fehlgeschlagen", job)

    @Slot()
    def sync_time(self) -> None:
        def job() -> str:
            sent = self.session.sync_time()
            return f"Geräteuhr auf PC-Zeit {sent:%H:%M:%S} gestellt."

        self._run("Uhr stellen fehlgeschlagen", job)

    @Slot()
    def load_config(self) -> None:
        def job() -> None:
            self.config_loaded.emit(self.session.get_config())

        self._run("Einstellungen nicht lesbar", job)

    @Slot()
    def refresh_status(self) -> None:
        def job() -> None:
            self.status.emit(self.session.status())

        self._run("Status nicht lesbar", job)

    @Slot()
    def shutdown(self) -> None:
        """Last job of the thread: close the port (never leak the handle), end the loop."""
        try:
            self.session.close()
        finally:
            thread = QThread.currentThread()
            if thread is not None:
                thread.quit()


class DeviceController(QObject):
    """GUI-thread side: owns the worker thread, connection state and timers."""

    state_changed = Signal(str, str)      # state, port/message
    # worker results, re-exposed so the UI never touches the worker
    connected = Signal(object)
    connect_failed = Signal(str, bool, bool)  # message, fatal, manual
    disconnected = Signal(str)
    status = Signal(object)
    measurement = Signal(object, object, bool)
    alarm = Signal(int, bool)
    sensor = Signal(str)
    booted = Signal(str)
    config_loaded = Signal(object)
    ports = Signal(list)
    done = Signal(str)
    failed = Signal(str, str)
    log_error = Signal(str)

    # requests into the worker thread (queued)
    _req_connect = Signal(str)
    _req_disconnect = Signal()
    _req_poll = Signal()
    _req_scan = Signal()
    _req_ack = Signal()
    _req_apply = Signal(object)
    _req_reset = Signal()
    _req_sync = Signal()
    _req_config = Signal()
    _req_status = Signal()
    _req_recording = Signal(bool)
    _req_shutdown = Signal()

    def __init__(self, log_service: MeasurementLog | None = None, *,
                 open_device: OpenDevice | None = None,
                 scan_ports: Callable[[], list[str]] | None = None,
                 parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.state = STATE_DISCONNECTED
        self.auto_connect = False
        self.port = ""                      # "" = automatic detection
        self._manual = False
        self._next_try = 0.0
        self._stopped = False

        self._thread = QThread()
        self._thread.setObjectName("umwelt-serial")
        self._worker = SerialWorker(log_service, open_device, scan_ports or default_scan)
        self._worker.moveToThread(self._thread)

        w = self._worker
        self._req_connect.connect(w.connect_device)
        self._req_disconnect.connect(w.disconnect_device)
        self._req_poll.connect(w.poll)
        self._req_scan.connect(w.scan_ports)
        self._req_ack.connect(w.ack)
        self._req_apply.connect(w.apply_config)
        self._req_reset.connect(w.reset_config)
        self._req_sync.connect(w.sync_time)
        self._req_config.connect(w.load_config)
        self._req_status.connect(w.refresh_status)
        self._req_recording.connect(w.set_recording)
        self._req_shutdown.connect(w.shutdown)

        w.connected.connect(self._on_connected)
        w.connect_failed.connect(self._on_connect_failed)
        w.disconnected.connect(self._on_disconnected)
        for name in ("status", "measurement", "alarm", "sensor", "booted", "config_loaded",
                     "ports", "done", "failed", "log_error"):
            getattr(w, name).connect(getattr(self, name))

        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(POLL_MS)
        self._poll_timer.timeout.connect(self._poll)
        self._reconnect_timer = QTimer(self)
        self._reconnect_timer.setInterval(RECONNECT_MS)
        self._reconnect_timer.timeout.connect(self._reconnect_tick)
        self._thread.start()

    # -- lifecycle -------------------------------------------------------------------

    def start(self, port: str = "") -> None:
        """Enable automatic connecting (called once the window is visible)."""
        self.port = port
        self.auto_connect = True
        self._next_try = 0.0
        self._poll_timer.start()
        self._reconnect_timer.start()
        self.scan_ports()
        QTimer.singleShot(0, self._reconnect_tick)

    def shutdown(self) -> None:
        """Close the port in the worker thread and stop the thread (window closes)."""
        if self._stopped:
            return
        self._stopped = True
        self.auto_connect = False
        self._poll_timer.stop()
        self._reconnect_timer.stop()
        self._req_shutdown.emit()  # queued behind a running job; quits the thread itself
        if not self._thread.wait(SHUTDOWN_WAIT_MS):  # pragma: no cover - hung driver
            log.warning("Serieller Worker beendet sich nicht rechtzeitig")
            self._thread.quit()
            self._thread.wait(1000)

    # -- requests from the UI ----------------------------------------------------------

    def connect_device(self, port: str = "") -> None:
        if self.state != STATE_DISCONNECTED or self._stopped:
            return
        self.port = port
        self.auto_connect = True
        self._start_connect(manual=True)

    def disconnect_device(self) -> None:
        """User clicked „Trennen": stay disconnected until „Verbinden"."""
        self.auto_connect = False
        self._req_disconnect.emit()
        self._set_state(STATE_DISCONNECTED, "Getrennt (automatisches Verbinden aus).")

    def scan_ports(self) -> None:
        self._req_scan.emit()

    def ack(self) -> None:
        self._req_ack.emit()

    def apply_config(self, changes: dict[str, str]) -> None:
        if changes:
            self._req_apply.emit(dict(changes))

    def reset_config(self) -> None:
        self._req_reset.emit()

    def sync_time(self) -> None:
        self._req_sync.emit()

    def load_config(self) -> None:
        self._req_config.emit()

    def refresh_status(self) -> None:
        self._req_status.emit()

    def set_recording(self, on: bool) -> None:
        self._req_recording.emit(bool(on))

    # -- internals -------------------------------------------------------------------

    def _set_state(self, state: str, text: str) -> None:
        self.state = state
        self.state_changed.emit(state, text)

    def _start_connect(self, manual: bool) -> None:
        self._manual = manual
        self._set_state(STATE_CONNECTING, self.port or "")
        self._req_connect.emit(self.port)

    @Slot()
    def _reconnect_tick(self) -> None:
        if (self._stopped or self.state != STATE_DISCONNECTED or not self.auto_connect
                or time.monotonic() < self._next_try):
            return
        self._start_connect(manual=False)

    @Slot()
    def _poll(self) -> None:
        if self.state == STATE_CONNECTED:
            self._req_poll.emit()

    @Slot(object)
    def _on_connected(self, info: object) -> None:
        if self._stopped:
            return
        self._set_state(STATE_CONNECTED, getattr(info, "port", ""))
        self.connected.emit(info)

    @Slot(str, bool)
    def _on_connect_failed(self, message: str, fatal: bool) -> None:
        self._next_try = time.monotonic() + RETRY_AFTER_FAIL_S
        if fatal:
            self.auto_connect = False  # firmware too old: retrying cannot help
        self._set_state(STATE_DISCONNECTED, message)
        self.connect_failed.emit(message, fatal, self._manual)

    @Slot(str)
    def _on_disconnected(self, reason: str) -> None:
        if self.state == STATE_DISCONNECTED:
            return
        self._req_disconnect.emit()  # close the port in the worker thread
        self._next_try = 0.0
        self._set_state(STATE_DISCONNECTED, reason)
        self.disconnected.emit(reason)
