"""One connection to the device plus automatic logging — blocking, Qt-free.

All methods block and are meant for ONE worker thread (the panel's ``QThread``). Events of
the device (``EVT DATA/ALARM/SENSOR/BOOT``, connection loss) arrive in the dispatcher thread
of :class:`umwelt_ctl.device.UmweltDevice`; the session records ``EVT DATA`` into the
measurement log right there (never on the GUI thread) and hands everything on to a
:class:`SessionListener`.

The wire protocol is spoken only by ``umwelt_ctl``: :class:`UmweltDevice` opens the port
without resetting the Uno (DTR/RTS off, quick ``PING``, fallback to ``EVT BOOT``), restores
``STATUS``/``TIME``/``STREAM`` after a mid-session ``EVT BOOT`` and drops garbage ``EVT DATA``
lines before they reach this module.
"""

from __future__ import annotations

import datetime as _dt
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from umwelt_ctl import protocol as p
from umwelt_ctl.device import DeviceDisconnected, DeviceTimeout, FirmwareTooOld, UmweltDevice
from umwelt_ctl.protocol import DeviceError, DeviceStatus, Event, Measurement, ProtocolError
from umwelt_panel.core.errors import PanelError
from umwelt_panel.core.services.log_service import MeasurementLog

log = logging.getLogger(__name__)

OpenDevice = Callable[[str | None], UmweltDevice]

MAX_POLL_FAILURES = 3


def describe_error(exc: BaseException) -> str:
    """German one-line message for an expected failure (no traceback for the user)."""
    if isinstance(exc, DeviceError):
        return exc.message_de  # the one ERR table in umwelt_ctl.protocol
    if isinstance(exc, DeviceTimeout):
        return "Das Gerät antwortet nicht (Zeitüberschreitung). USB-Kabel prüfen."
    if isinstance(exc, DeviceDisconnected):
        return str(exc) or "Keine Verbindung zum Gerät."
    if isinstance(exc, FirmwareTooOld | PanelError | ValueError):
        return str(exc)
    if isinstance(exc, ProtocolError):
        return f"Unerwartete Antwort vom Gerät: {exc}"
    return str(exc) or exc.__class__.__name__


@dataclass(frozen=True)
class ConnectInfo:
    port: str
    fw_version: str
    status: DeviceStatus
    measurement: Measurement | None  # None: sensor missing (READ -> ERR 5)
    config: dict[str, int | None]


class SessionListener:
    """Callbacks of a session (called from the device's dispatcher thread). No-op base."""

    def on_measurement(self, m: Measurement, ts: _dt.datetime, logged: bool) -> None: ...

    def on_log_error(self, message: str) -> None: ...

    def on_alarm(self, flag: int, active: bool) -> None: ...

    def on_sensor(self, state: str) -> None: ...

    def on_boot(self, fw_version: str) -> None: ...

    def on_disconnected(self, reason: str) -> None: ...


class DeviceSession:
    def __init__(self, listener: SessionListener | None = None,
                 log_service: MeasurementLog | None = None, *,
                 open_device: OpenDevice | None = None,
                 now: Callable[[], _dt.datetime] = lambda: _dt.datetime.now().astimezone(),
                 monotonic: Callable[[], float] = time.monotonic):
        self.listener = listener or SessionListener()
        self.log_service = log_service
        self._open = open_device or (lambda port: UmweltDevice.open(port))
        self._now = now
        self._mono = monotonic
        self.dev: UmweltDevice | None = None
        self.recording = False
        self.alarm_flags: int | None = None
        self._last_sync = 0.0
        self._poll_failures = 0
        self._lock = threading.Lock()
        self._unsubscribe: Callable[[], None] | None = None
        self._log_error_shown = False

    @property
    def connected(self) -> bool:
        return self.dev is not None and self.dev.connected

    # ------------------------------------------------------------------ lifecycle

    def connect(self, port: str | None) -> ConnectInfo:
        """Open (auto-detect if ``port`` is None), enable STREAM, set TIME, load state.

        Raises DeviceDisconnected/PortBusy, DeviceTimeout, FirmwareTooOld, DeviceError.
        """
        self.close()
        dev = self._open(port)
        try:
            self._unsubscribe = dev.subscribe(self._on_event)
            dev.set_stream(True)
            dev.sync_time()
            self._last_sync = self._mono()
            st = dev.status()
            try:
                m: Measurement | None = dev.read()
            except DeviceError as exc:
                if exc.code != p.ERR_SENSOR:
                    raise
                m = None  # sensor missing: its own state, not a connection failure
            cfg = dev.get_config()
        except BaseException:
            dev.close()
            raise
        with self._lock:
            self.dev = dev
            self.alarm_flags = st.alarm_flags
            self._poll_failures = 0
            self._log_error_shown = False
        return ConnectInfo(dev.port or port or "?", dev.fw_version or "", st, m, cfg)

    def close(self) -> None:
        with self._lock:
            dev, self.dev = self.dev, None
            unsub, self._unsubscribe = self._unsubscribe, None
            self.alarm_flags = None
        if unsub is not None:
            unsub()
        if dev is not None:
            try:
                if dev.connected:
                    dev.set_stream(False)
            except (DeviceError, DeviceTimeout, DeviceDisconnected, ProtocolError):
                pass
            dev.close()

    def _require(self) -> UmweltDevice:
        dev = self.dev
        if dev is None or not dev.connected:
            raise DeviceDisconnected("Keine Verbindung zum Gerät.")
        return dev

    # ------------------------------------------------------------------ periodic

    def poll(self) -> DeviceStatus:
        """``STATUS`` (alarm flags, uptime) and, every 10 min, ``TIME`` again.

        Raises DeviceDisconnected when the link is gone or failed repeatedly.
        """
        dev = self._require()
        try:
            st = dev.status()
            if self._mono() - self._last_sync >= p.TIME_RESYNC_SEC:
                dev.sync_time()
                self._last_sync = self._mono()
        except DeviceDisconnected:
            raise
        except (DeviceTimeout, ProtocolError, DeviceError) as exc:
            self._poll_failures += 1
            if self._poll_failures >= MAX_POLL_FAILURES:
                raise DeviceDisconnected(
                    f"Das Gerät antwortet nicht mehr ({describe_error(exc)}).") from exc
            raise
        self._poll_failures = 0
        self.alarm_flags = st.alarm_flags
        return st

    # ------------------------------------------------------------------ commands

    def status(self) -> DeviceStatus:
        st = self._require().status()
        self.alarm_flags = st.alarm_flags
        return st

    def ack(self) -> None:
        self._require().ack()

    def get_config(self) -> dict[str, int | None]:
        return self._require().get_config()

    def apply_config(self, changes: dict[str, str]) -> list[str]:
        """Send ``CFG <key> <value>`` for each change (user text in physical units).

        Every value is validated with :func:`umwelt_ctl.protocol.parse_config_input` first;
        returns German error lines (empty list = all accepted).
        """
        dev = self._require()
        errors: list[str] = []
        for key, text in changes.items():
            try:
                dev.set_config(key, p.parse_config_input(key, text))
            except DeviceDisconnected:
                raise
            except (ValueError, DeviceError, DeviceTimeout, ProtocolError) as exc:
                label = p.CONFIG_KEYS[key].label_de if key in p.CONFIG_KEYS else key
                errors.append(f"{label}: {describe_error(exc)}")
        return errors

    def reset_config(self) -> None:
        self._require().reset_config()

    def sync_time(self) -> _dt.datetime:
        sent = self._require().sync_time()
        self._last_sync = self._mono()
        return sent

    # ------------------------------------------------------------------ events

    def _on_event(self, ev: Event) -> None:
        """Dispatcher thread of the device: record, then notify."""
        if ev.kind == "DISCONNECTED":
            self.listener.on_disconnected(
                f"Verbindung verloren ({ev.raw or 'USB getrennt'}).")
        elif ev.kind == p.EVT_DATA and ev.measurement is not None:
            self._on_data(ev.measurement)
        elif ev.kind == p.EVT_ALARM and ev.flag is not None:
            flags = self.alarm_flags or 0
            self.alarm_flags = (flags | ev.flag) if ev.active else (flags & ~ev.flag)
            self.listener.on_alarm(ev.flag, bool(ev.active))
        elif ev.kind == p.EVT_SENSOR and ev.sensor is not None:
            self.listener.on_sensor(ev.sensor)
        elif ev.kind == p.EVT_BOOT:
            # The device layer has re-read STATUS and re-sent TIME/STREAM already.
            self._last_sync = self._mono()
            dev = self.dev
            if dev is not None and dev.last_status is not None:
                self.alarm_flags = dev.last_status.alarm_flags
            self.listener.on_boot(ev.fw_version or "")

    def _on_data(self, m: Measurement) -> None:
        ts = self._now()
        logged = False
        if self.recording and self.log_service is not None:
            try:
                self.log_service.record(m, self.alarm_flags, ts)
                logged = True
                self._log_error_shown = False
            except PanelError as exc:
                log.warning("Messwert nicht gespeichert: %s", exc)
                if not self._log_error_shown:  # one message per failure streak, no spam
                    self._log_error_shown = True
                    self.listener.on_log_error(str(exc))
        self.listener.on_measurement(m, ts, logged)
