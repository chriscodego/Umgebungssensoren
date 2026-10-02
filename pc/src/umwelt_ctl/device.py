"""Serial connection to the Umgebungssensoren device (Arduino Uno + BME680).

Threading model
---------------
* A *reader thread* assembles incoming bytes into lines. ``EVT`` lines are parsed and go to
  an event queue (malformed or unknown ones are logged and dropped); all other lines go to
  the currently pending request, lines without a pending request are discarded.
* A *dispatcher thread* delivers events to subscriber callbacks. Callbacks run outside the
  reader thread and may issue requests themselves without deadlocking.
* :meth:`UmweltDevice.request` is thread-safe; requests are serialized.

Opening the port does not reset the Uno (DTR/RTS off). :meth:`UmweltDevice.wait_ready`
handles both cases: no reset (quick PING) and a reset anyway (wait for ``EVT BOOT``).
An ``EVT BOOT`` in the middle of a session means the device restarted: the device layer
re-reads ``STATUS``, re-sends ``TIME`` and re-enables ``STREAM`` if it was on, before the
event is passed on to subscribers.
"""

from __future__ import annotations

import datetime as _dt
import logging
import os
import queue
import threading
import time
from collections.abc import Callable
from typing import Protocol

from . import protocol as p
from .protocol import DeviceError, DeviceStatus, Event, Measurement, ProtocolError, Reply

log = logging.getLogger(__name__)

ARDUINO_VID = 0x2341
PORT_ENV = "UMWELT_PORT"
DEFAULT_TIMEOUT = 2.0
QUICK_WAIT = 0.3           # wait this long for EVT BOOT before probing with PING
QUICK_PING_TIMEOUT = 0.6
BOOT_WAIT = 4.0            # if the board reset anyway: EVT BOOT comes ~2-3 s after reset

EventCallback = Callable[[Event], None]

_SENTINEL_DISCONNECT = object()


class DeviceTimeout(TimeoutError):
    """No (complete) answer within the timeout."""


class DeviceDisconnected(ConnectionError):
    """Serial connection lost, closed, or port not available."""


class PortBusy(DeviceDisconnected):
    """The port exists but another program holds it."""


class FirmwareTooOld(Exception):
    """The connected firmware is older than :data:`protocol.MIN_FW_VERSION`."""

    def __init__(self, version: str):
        self.version = version
        super().__init__(
            f"Die Firmware auf dem Gerät ist zu alt (Version {version or '?'}). Dieses PC-Tool "
            f"braucht mindestens Firmware {p.MIN_FW_VERSION}. Bitte die Firmware aktualisieren.")


class Transport(Protocol):
    """Minimal byte transport (pyserial wrapper and test fakes)."""

    def read_some(self) -> bytes:
        """Return available bytes; block at most a short time (~0.1 s); b"" if none."""

    def write(self, data: bytes) -> None: ...

    def close(self) -> None: ...


class SerialTransport:
    """pyserial transport; DTR/RTS stay low while opening so the Uno is not reset."""

    def __init__(self, port: str, baudrate: int = p.BAUDRATE, read_timeout: float = 0.1,
                 reset_on_open: bool = False):
        import serial  # lazy: protocol/tests do not need pyserial

        self.port = port
        ser = serial.Serial()
        ser.port = port
        ser.baudrate = baudrate
        ser.timeout = read_timeout          # never block forever on read
        ser.write_timeout = 2.0
        if not reset_on_open:
            ser.dtr = False
            ser.rts = False
        try:
            ser.open()
        except serial.SerialException as exc:
            raise _port_error(port, exc) from None
        self._ser = ser

    def read_some(self) -> bytes:
        n = self._ser.in_waiting
        return self._ser.read(n if n > 0 else 1)

    def write(self, data: bytes) -> None:
        self._ser.write(data)
        self._ser.flush()

    def close(self) -> None:
        self._ser.close()


def _port_error(port: str, exc: Exception) -> DeviceDisconnected:
    text = str(exc)
    low = text.lower()
    if any(s in low for s in ("permissionerror", "access is denied", "zugriff verweigert",
                              "busy", "errno 13", "errno 16")):
        return PortBusy(f"Port {port} ist belegt – ein anderes Programm (Arduino IDE, "
                        f"serieller Monitor, GUI, Upload) hält ihn offen. Bitte schließen.")
    return DeviceDisconnected(f"Port {port} kann nicht geöffnet werden ({text}).")


# --------------------------------------------------------------------------- port detection


def find_ports(vid: int = ARDUINO_VID) -> list[tuple[str, str]]:
    """``[(device, description), ...]`` of serial ports with the given USB VID."""
    from serial.tools import list_ports

    return [(info.device, info.description or "")
            for info in sorted(list_ports.comports(), key=lambda i: i.device)
            if info.vid == vid]


def list_all_ports() -> list[tuple[str, str, bool]]:
    """All serial ports: ``(device, description, is_arduino)``."""
    from serial.tools import list_ports

    return [(info.device, info.description or "", info.vid == ARDUINO_VID)
            for info in sorted(list_ports.comports(), key=lambda i: i.device)]


def detect_port(explicit: str | None = None, vid: int = ARDUINO_VID) -> str:
    """``explicit`` (``--port``) > env ``UMWELT_PORT`` > first port with the Arduino VID."""
    if explicit and explicit.strip():
        return explicit.strip()
    env = os.environ.get(PORT_ENV, "").strip()
    if env:
        return env
    ports = find_ports(vid)
    if not ports:
        raise DeviceDisconnected(
            f"Kein Arduino (USB-VID 0x{vid:04X}) gefunden. Ist das Gerät angesteckt? "
            f"Sonst Port mit --port oder {PORT_ENV} angeben.")
    if len(ports) > 1:
        log.warning("Mehrere Arduinos gefunden (%s), verwende %s",
                    ", ".join(d for d, _ in ports), ports[0][0])
    return ports[0][0]


# --------------------------------------------------------------------------- device


class UmweltDevice:
    def __init__(self, transport: Transport, *, timeout: float = DEFAULT_TIMEOUT,
                 now: Callable[[], _dt.datetime] = _dt.datetime.now):
        self._transport = transport
        self.timeout = timeout
        self.port: str | None = getattr(transport, "port", None)
        self.fw_version: str | None = None
        self.last_status: DeviceStatus | None = None
        self._now = now

        self._req_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._pending: queue.Queue | None = None
        self._resync = False

        self._subscribers: list[EventCallback] = []
        self._sub_lock = threading.Lock()
        self._events: queue.Queue = queue.Queue()
        self._boot = threading.Event()
        self._ready = False
        self._stream_on = False
        self.boot_count = 0  # mid-session restarts seen

        self._stop = threading.Event()
        self._closed = False
        self._disconnected: BaseException | None = None
        self._reader: threading.Thread | None = None
        self._dispatcher: threading.Thread | None = None

    # ------------------------------------------------------------------ lifecycle

    @classmethod
    def open(cls, port: str | None = None, *, timeout: float = DEFAULT_TIMEOUT,
             boot_wait: float = BOOT_WAIT) -> UmweltDevice:
        """Open the port (auto-detected if None) without resetting the board; wait until ready."""
        port = detect_port(port)
        transport = SerialTransport(port)
        dev = cls(transport, timeout=timeout)
        dev.port = port
        try:
            dev.start()
            dev.wait_ready(boot_wait)
        except BaseException:
            dev.close()
            raise
        return dev

    def start(self) -> None:
        if self._reader is not None:
            return
        self._reader = threading.Thread(target=self._read_loop, name="umwelt-reader",
                                        daemon=True)
        self._dispatcher = threading.Thread(target=self._dispatch_loop, name="umwelt-events",
                                            daemon=True)
        self._reader.start()
        self._dispatcher.start()

    def wait_ready(self, boot_wait: float = BOOT_WAIT, ping_attempts: int = 3,
                   require_min_fw: bool = True) -> str:
        """Ready check without reset; falls back to waiting for ``EVT BOOT``.

        1. short wait (~0.3 s) for ``EVT BOOT``
        2. none: blank line (flushes a stray byte), quick ``PING`` -> done
        3. no answer: the board did reset anyway -> wait for ``EVT BOOT``, ``PING`` with retries
        """
        t0 = time.monotonic()
        if self._boot.wait(min(QUICK_WAIT, boot_wait)):
            time.sleep(0.05)
        else:
            try:
                self._transport.write(b"\n")
            except Exception as exc:
                log.debug("Leerzeile vor PING fehlgeschlagen: %s", exc)
            try:
                version = self.ping(timeout=QUICK_PING_TIMEOUT)
            except (DeviceTimeout, ProtocolError, DeviceError) as exc:
                log.debug("Schnell-PING ohne Antwort (Gerät startet neu?): %s", exc)
            else:
                return self._accept(version, require_min_fw)
            if self._boot.wait(max(0.0, boot_wait - (time.monotonic() - t0))):
                time.sleep(0.05)
        last: Exception | None = None
        for _ in range(max(1, ping_attempts)):
            try:
                version = self.ping()
            except (DeviceTimeout, DeviceError) as exc:
                last = exc
                log.debug("PING fehlgeschlagen: %s", exc)
                continue
            return self._accept(version, require_min_fw)
        assert last is not None
        raise last

    def _accept(self, version: str, require_min_fw: bool) -> str:
        if require_min_fw and p.version_older(version, p.MIN_FW_VERSION):
            raise FirmwareTooOld(version)
        self._boot.clear()
        self._ready = True
        return version

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._stop.set()
        try:
            self._transport.close()
        except Exception:  # pragma: no cover - best effort
            pass
        self._fail_pending(DeviceDisconnected("Verbindung geschlossen"))
        self._events.put(_SENTINEL_DISCONNECT)
        for t in (self._reader, self._dispatcher):
            if t is not None and t is not threading.current_thread():
                t.join(timeout=1.0)

    def __enter__(self) -> UmweltDevice:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    @property
    def connected(self) -> bool:
        return not self._closed and self._disconnected is None

    # ------------------------------------------------------------------ events

    def subscribe(self, callback: EventCallback) -> Callable[[], None]:
        """Register an event callback (dispatcher thread). Returns an unsubscribe function.

        On connection loss a synthetic ``Event("DISCONNECTED")`` is delivered.
        """
        with self._sub_lock:
            self._subscribers.append(callback)

        def unsubscribe() -> None:
            with self._sub_lock:
                if callback in self._subscribers:
                    self._subscribers.remove(callback)

        return unsubscribe

    def _dispatch_loop(self) -> None:
        while True:
            item = self._events.get()
            if item is _SENTINEL_DISCONNECT:
                if self._disconnected is not None and not self._closed:
                    self._deliver(Event("DISCONNECTED", raw=str(self._disconnected)))
                return
            ev, mid_session = item
            if ev.kind == p.EVT_BOOT and mid_session:
                self._after_reboot()
            self._deliver(ev)

    def _after_reboot(self) -> None:
        """Mid-session ``EVT BOOT``: RAM state (clock, STREAM) is gone -> restore it."""
        self.boot_count += 1
        log.warning("Gerät wurde neu gestartet – Uhr und Status werden neu abgeglichen")
        try:
            self.status()
            self.sync_time()
            if self._stream_on:
                self.request(p.cmd_stream(True))
        except (DeviceError, DeviceTimeout, DeviceDisconnected, ProtocolError) as exc:
            log.warning("Abgleich nach Neustart fehlgeschlagen: %s", exc)

    def _deliver(self, ev: Event) -> None:
        with self._sub_lock:
            subs = list(self._subscribers)
        for cb in subs:
            try:
                cb(ev)
            except Exception:
                log.exception("Fehler im Event-Callback")

    # ------------------------------------------------------------------ reader

    def _read_loop(self) -> None:
        buf = b""
        while not self._stop.is_set():
            try:
                chunk = self._transport.read_some()
            except Exception as exc:
                if not self._stop.is_set():
                    log.debug("Lesefehler: %s", exc)
                    self._disconnected = exc
                    self._fail_pending(DeviceDisconnected(f"Verbindung verloren: {exc}"))
                    self._events.put(_SENTINEL_DISCONNECT)
                return
            if not chunk:
                continue
            buf += chunk
            while b"\n" in buf:
                raw, buf = buf.split(b"\n", 1)
                self._handle_line(p.clean_line(raw))
            if len(buf) > 1024:  # garbage without newline (e.g. bootloader noise)
                buf = b""

    def _handle_line(self, line: str) -> None:
        if not line:
            return
        log.debug("<< %s", line)
        if p.is_event_line(line):
            try:
                ev = p.parse_event(line)
            except ProtocolError as exc:
                log.warning("Ungültiges Ereignis ignoriert: %s", exc)
                return
            if ev.kind not in p.KNOWN_EVENTS:
                log.info("Unbekanntes Ereignis ignoriert: %s", line)
                return
            if ev.kind == p.EVT_BOOT:
                self.fw_version = ev.fw_version or self.fw_version
                self._boot.set()
            # A BOOT after the ready check = restart during the session (decided here, at
            # arrival time, so a BOOT that belongs to the ready check is never mistaken).
            self._events.put((ev, self._ready))
            return
        with self._state_lock:
            q = self._pending
        if q is not None:
            q.put(line)
        else:
            log.debug("Zeile ohne offene Anfrage verworfen: %s", line)

    def _fail_pending(self, exc: BaseException) -> None:
        with self._state_lock:
            q = self._pending
        if q is not None:
            q.put(exc)

    # ------------------------------------------------------------------ requests

    def request(self, command: str, *, expect_list: bool = False,
                timeout: float | None = None) -> Reply:
        """Send one command line and wait for its response.

        Raises DeviceError on ``ERR``, DeviceTimeout on timeout (also a missing ``END``),
        DeviceDisconnected if the connection is gone.
        """
        if "\n" in command or "\r" in command:
            raise ValueError("Befehl darf keinen Zeilenumbruch enthalten")
        timeout = self.timeout if timeout is None else timeout
        with self._req_lock:
            if self._closed:
                raise DeviceDisconnected("Verbindung geschlossen")
            if self._disconnected is not None:
                raise DeviceDisconnected(f"Verbindung verloren: {self._disconnected}")
            if self._resync:
                time.sleep(0.3)  # previous request timed out: let late answers be dropped
                self._resync = False
            q: queue.Queue = queue.Queue()
            with self._state_lock:
                self._pending = q
            try:
                log.debug(">> %s", command)
                try:
                    self._transport.write(p.encode_line(command))
                except Exception as exc:
                    raise DeviceDisconnected(f"Schreibfehler: {exc}") from exc
                return self._collect(q, command, expect_list, time.monotonic() + timeout)
            except DeviceTimeout:
                self._resync = True
                raise
            finally:
                with self._state_lock:
                    self._pending = None

    def _collect(self, q: queue.Queue, command: str, expect_list: bool,
                 deadline: float) -> Reply:
        def next_line() -> str:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise DeviceTimeout(f"Das Gerät antwortet nicht auf {command!r} "
                                    "(Zeitüberschreitung).")
            try:
                item = q.get(timeout=remaining)
            except queue.Empty:
                raise DeviceTimeout(f"Das Gerät antwortet nicht auf {command!r} "
                                    "(Zeitüberschreitung).") from None
            if isinstance(item, BaseException):
                raise item
            return item

        while True:  # skip noise before the response
            line = next_line()
            if p.is_err_line(line):
                raise p.parse_err(line)
            if p.is_ok_line(line):
                args = p.parse_ok_args(line)
                break
            log.debug("Unerwartete Zeile vor Antwort ignoriert: %s", line)

        if not expect_list:
            return Reply(args=args)
        body: list[str] = []
        while True:
            line = next_line()
            if p.is_end_line(line):
                return Reply(args=args, lines=tuple(body))
            if p.is_err_line(line):
                raise p.parse_err(line)
            body.append(line)

    # ------------------------------------------------------------------ high level API

    def ping(self, timeout: float | None = None) -> str:
        reply = self.request(p.cmd_ping(), timeout=timeout)
        self.fw_version = p.parse_pong(reply.args)
        return self.fw_version

    def status(self) -> DeviceStatus:
        st = p.parse_status(self.request(p.cmd_status()).args)
        self.last_status = st
        return st

    def read(self) -> Measurement:
        """Current values; ``DeviceError`` code 5 if the sensor is MISSING."""
        return p.parse_read(self.request(p.cmd_read()).args)

    def get_config(self) -> dict[str, int | None]:
        return p.parse_config(self.request(p.cmd_cfg_list(), expect_list=True).lines)

    def set_config(self, name: str, wire_value: str) -> None:
        """``wire_value`` as produced by :func:`protocol.parse_config_input`."""
        self.request(p.cmd_cfg_set(name, wire_value))

    def reset_config(self) -> None:
        self.request(p.cmd_cfg_reset())

    def set_stream(self, on: bool) -> None:
        self.request(p.cmd_stream(on))
        self._stream_on = on

    def ack(self) -> None:
        """Acknowledge alarms; ``DeviceError`` code 7 if nothing to acknowledge."""
        self.request(p.cmd_ack())

    def get_time(self) -> _dt.time | None:
        return p.parse_time_reply(self.request(p.cmd_time_get()).args)

    def set_time(self, t: _dt.time | _dt.datetime) -> None:
        self.request(p.cmd_time_set(t))

    def sync_time(self, sleep: Callable[[float], None] = time.sleep) -> _dt.datetime:
        """Set the device clock to PC local time, aligned to the start of a second."""
        current = self._now()
        if current.microsecond:
            sleep((1_000_000 - current.microsecond) / 1_000_000)
            current = self._now()
        sent = current.replace(microsecond=0)
        self.set_time(sent)
        return sent
