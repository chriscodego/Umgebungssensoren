"""Shared fixtures: a scripted fake device per docs/SPEC.md (no hardware needed)."""

from __future__ import annotations

import os
import queue
import re
import sys
import threading
from collections.abc import Callable

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir, "src"))

from umwelt_ctl.device import UmweltDevice  # noqa: E402  (after sys.path setup)

# Control Panel GUI tests (marker ``gui``) run headless. pytest-qt is disabled in
# pyproject.toml and only loaded here when PySide6 (extra "panel") is installed.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if os.path.isdir("C:/Windows/Fonts"):  # offscreen Qt finds no fonts on its own on Windows
    os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")
try:
    import PySide6  # noqa: F401
except ImportError:  # pragma: no cover - plain `pc[dev]` install
    HAVE_QT = False
else:
    HAVE_QT = True
    pytest_plugins = ("pytestqt.plugin",)

Handler = Callable[[str], "list[str] | str | None"]


class FakeTransport:
    """Byte-level serial double.

    ``handler(command) -> lines`` produces the reply lines for every written command line
    (``None`` = no answer). ``send()``/``inject_bytes()`` push data at any time (async EVT).
    ``chunk_size`` splits the output into small pieces to exercise line reassembly.
    """

    def __init__(self, handler: Handler | None = None, chunk_size: int | None = None):
        self.handler = handler
        self.chunk_size = chunk_size
        if hasattr(handler, "attach"):
            handler.attach(self.send)
        self.written: list[str] = []
        self.raw_written: list[bytes] = []
        self._rx: queue.Queue[bytes | Exception] = queue.Queue()
        self._lock = threading.Lock()
        self.closed = False

    def read_some(self) -> bytes:
        try:
            item = self._rx.get(timeout=0.02)
        except queue.Empty:
            if self.closed:
                raise OSError("port closed") from None
            return b""
        if isinstance(item, Exception):
            raise item
        return item

    def write(self, data: bytes) -> None:
        if self.closed:
            raise OSError("port closed")
        self.raw_written.append(data)
        for raw in data.decode("utf-8").split("\n"):
            raw = raw.rstrip("\r")
            if not raw.strip():
                continue  # the firmware ignores empty lines
            with self._lock:
                self.written.append(raw)
            if self.handler is not None:
                out = self.handler(raw)
                if out is None:
                    continue
                if isinstance(out, str):
                    out = [out]
                self.send(*out)

    def close(self) -> None:
        self.closed = True

    # -- test helpers
    def send(self, *lines: str) -> None:
        self.inject_bytes("".join(x + "\r\n" for x in lines).encode("utf-8"))

    def inject_bytes(self, data: bytes) -> None:
        n = self.chunk_size or len(data) or 1
        for i in range(0, len(data), n):
            self._rx.put(data[i:i + n])

    def fail(self, exc: Exception | None = None) -> None:
        self._rx.put(exc or OSError("USB getrennt"))


CFG_DEFAULTS = {"INTERVAL": 10, "TEMP_OFFSET": 0, "T_HI": None, "T_LO": None,
                "RH_HI": None, "RH_LO": None, "BUZZER": 0}
CFG_RANGES = {"INTERVAL": (1, 3600), "TEMP_OFFSET": (-5000, 5000), "T_HI": (-4000, 8500),
              "T_LO": (-4000, 8500), "RH_HI": (0, 10000), "RH_LO": (0, 10000),
              "BUZZER": (0, 1)}
THRESHOLDS = ("T_HI", "T_LO", "RH_HI", "RH_LO")


class FakeUmwelt:
    """In-memory model of the firmware's protocol version 1 (docs/SPEC.md)."""

    def __init__(self, fw: str = "0.1.0") -> None:
        self.fw = fw
        self.sensor = "OK"
        self.values: tuple[int | str, ...] = (2134, 4512, 10132, 85000)
        self.age: int | str = 3
        self.cfg = dict(CFG_DEFAULTS)
        self.stream = False
        self.clock: str | None = None
        self.alarm = 0
        self.unacked = 0
        self.uptime = 100
        self.cfg_interleave: list[str] = []  # EVT lines sent between the C lines of CFG
        self.silent = False  # True: no answers (e.g. board resetting)
        self._emit: Callable[..., None] | None = None

    # -- wiring / helpers
    def attach(self, emit: Callable[..., None]) -> None:
        self._emit = emit

    def emit(self, *lines: str) -> None:
        if self._emit is not None:
            self._emit(*lines)

    def _vals(self) -> list[str]:
        if self.sensor == "MISSING":
            return ["-"] * 4
        return [str(v) for v in self.values]

    def measure(self, values: tuple[int | str, ...] | None = None) -> None:
        if values is not None:
            self.values = values
        self.age = 0
        if self.stream:
            self.emit("EVT DATA " + " ".join(self._vals()))

    def set_sensor(self, state: str) -> None:
        self.sensor = state
        self.emit(f"EVT SENSOR {state}")
        if state != "OK" and not self.alarm & 16:
            self.raise_alarm(16)
        elif state == "OK" and self.alarm & 16:
            self.alarm &= ~16
            self.unacked &= ~16
            self.emit("EVT ALARM 16 0")

    def raise_alarm(self, flag: int) -> None:
        self.alarm |= flag
        self.unacked |= flag
        self.emit(f"EVT ALARM {flag} 1")

    def reboot(self) -> None:
        self.stream = False
        self.clock = None
        self.uptime = 0
        self.emit(f"EVT BOOT {self.fw}")

    # -- command handler
    def __call__(self, cmd: str) -> list[str] | None:
        if self.silent:
            return None
        if len(cmd.encode("utf-8")) > 80:
            return ["ERR 2 line too long"]
        t = cmd.split()
        c = [x.upper() for x in t]
        if not t:
            return None
        if c == ["PING"]:
            return [f"OK PONG Umgebungssensoren {self.fw}"]
        if c == ["STATUS"]:
            interval = self.cfg["INTERVAL"]
            return [f"OK {self.sensor} {interval} {self.uptime} {self.alarm} {self.unacked}"]
        if c == ["READ"]:
            if self.sensor == "MISSING":
                return ["ERR 5 sensor missing"]
            return ["OK " + " ".join(self._vals()) + f" {self.age}"]
        if c[0] == "CFG":
            return self._cfg(t, c)
        if c[0] == "STREAM":
            if len(t) != 2 or t[1] not in ("0", "1"):
                return ["ERR 2 args"]
            self.stream = t[1] == "1"
            return ["OK"]
        if c == ["ACK"]:
            if not self.unacked:
                return ["ERR 7 nothing to ack"]
            self.unacked = 0
            return ["OK"]
        if c[0] == "TIME":
            if len(t) == 1:
                return [f"OK {self.clock or '--:--:--'}"]
            m = re.fullmatch(r"(\d\d):(\d\d):(\d\d)", t[1]) if len(t) == 2 else None
            if not m or int(m[1]) > 23 or int(m[2]) > 59 or int(m[3]) > 59:
                return ["ERR 2 args"]
            self.clock = t[1]
            return ["OK"]
        return ["ERR 1 unknown"]

    def _cfg(self, t: list[str], c: list[str]) -> list[str]:
        if len(t) == 1:
            lines = [f"C {k} {'OFF' if v is None else v}" for k, v in self.cfg.items()]
            return ["OK", lines[0], *self.cfg_interleave, *lines[1:], "END"]
        if c[1:] == ["RESET"]:
            self.cfg = dict(CFG_DEFAULTS)
            return ["OK"]
        if len(t) != 3:
            return ["ERR 2 args"]
        key = c[1]
        if key not in self.cfg:
            return ["ERR 3 key"]
        if c[2] == "OFF":
            if key not in THRESHOLDS:
                return ["ERR 3 range"]
            self.cfg[key] = None
            return ["OK"]
        if not re.fullmatch(r"-?\d+", t[2]):
            return ["ERR 2 not numeric"]
        v = int(t[2])
        lo, hi = CFG_RANGES[key]
        if not lo <= v <= hi:
            return ["ERR 3 range"]
        self.cfg[key] = v
        return ["OK"]


@pytest.fixture(autouse=True)
def _no_real_serial_port(request, monkeypatch):
    """Safety net: host tests must never open a real COM port (COM9 may be in use).

    Only tests marked ``@pytest.mark.hardware`` may open ports.
    """
    if request.node.get_closest_marker("hardware"):
        return
    import serial

    class _Refuse:
        def __init__(self, *_a, **_kw):
            raise AssertionError("Host-Test wollte einen echten seriellen Port öffnen")

    monkeypatch.setattr(serial, "Serial", _Refuse)


@pytest.fixture(autouse=True)
def _no_real_update_share(monkeypatch, tmp_path_factory):
    """Safety net (PROJ-9): no test ever probes the institute share or a network drive.

    The production search reads these module globals at call time, so diverting them here
    covers every MainWindow built with the default update service.
    """
    monkeypatch.delenv("UMWELT_UPDATE_DIR", raising=False)
    try:
        from umwelt_panel.core.services import update_service
    except ImportError:  # pragma: no cover
        return
    monkeypatch.setattr(update_service, "UNC_UPDATE_FOLDER",
                        str(tmp_path_factory.getbasetemp() / "kein-institutslaufwerk"))
    monkeypatch.setattr(update_service, "detect_network_drives", lambda: [])


@pytest.fixture
def make_device():
    """Factory: make_device(handler, **kw) -> (started UmweltDevice, FakeTransport)."""
    created: list[UmweltDevice] = []

    def factory(handler: Handler | None = None, *, chunk_size: int | None = None,
                timeout: float = 1.0) -> tuple[UmweltDevice, FakeTransport]:
        tr = FakeTransport(handler, chunk_size=chunk_size)
        dev = UmweltDevice(tr, timeout=timeout)
        dev.start()
        created.append(dev)
        return dev, tr

    yield factory
    for d in created:
        d.close()
