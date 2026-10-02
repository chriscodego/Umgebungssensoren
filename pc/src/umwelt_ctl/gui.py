"""Umgebungssensoren – grafische Oberfläche (Tkinter).

Aufbau: Verbindungsleiste, Alarmanzeige (rot blinkend + Text, „Quittieren“), Reiter „Live“
(vier Kacheln Temperatur/Feuchte/Druck/Gas, Temperaturverlauf auf einem Canvas,
CSV-Aufzeichnung an/aus) und „Einstellungen“ (Intervall, Schwellwerte, Offset, Piezo,
Standardwerte, Uhr). Unten eine Statuszeile.

Threading: alle seriellen Zugriffe laufen in *einem* Worker-Thread; Geräte-Ereignisse kommen
aus dem Dispatcher-Thread des Geräts. Beides gelangt über ``ui_q`` in den Tk-Hauptthread, der
die Queue per ``root.after`` abholt. Kein Widget wird außerhalb des Hauptthreads angefasst,
und der Hauptthread wartet nie auf das Gerät.
"""

from __future__ import annotations

import collections
import logging
import os
import queue
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
from collections.abc import Callable
from datetime import datetime
from tkinter import filedialog, messagebox, ttk
from typing import Any

from . import __version__
from . import protocol as p
from .device import DeviceDisconnected, DeviceTimeout, FirmwareTooOld, UmweltDevice, find_ports
from .messlog import MessLogger, default_log_path
from .protocol import DeviceError, DeviceStatus, Event, Measurement

log = logging.getLogger(__name__)

AUTO_PORT = "Automatisch"
DRAIN_MS = 50            # UI queue polling
STATUS_MS = 5000         # STATUS polling (alarm flags, uptime)
TICK_MS = 500            # blinking
RECONNECT_MS = 2000      # look for the device while disconnected
RETRY_AFTER_FAIL_S = 6.0
MAX_POLL_FAILURES = 3
CHART_POINTS = 360       # ring of the last N temperature values (1 h at 10 s)

COL_ALARM = ("#c62828", "#ffffff")
COL_ALARM_BLINK = ("#ff8a80", "#3b0000")
COL_ALARM_ACKED = ("#f3c2c2", "#5c0000")
COL_OK = "#1e7a34"
COL_ERR = "#b00020"
COL_MUTED = "#777777"

SETTING_KEYS = ("INTERVAL", "TEMP_OFFSET", "T_HI", "T_LO", "RH_HI", "RH_LO")


def friendly_error(exc: BaseException) -> str:
    """German, user-oriented message for an exception from the device layer."""
    if isinstance(exc, DeviceError):
        return exc.message_de  # one table in protocol.py
    if isinstance(exc, DeviceTimeout):
        return "Das Gerät antwortet nicht (Zeitüberschreitung)."
    if isinstance(exc, DeviceDisconnected):
        return f"Keine Verbindung zum Gerät. {exc}"
    return str(exc) or exc.__class__.__name__


def default_scan() -> list[str]:
    return [d for d, _ in find_ports()]


class Worker:
    """Single background thread executing jobs one after another."""

    def __init__(self, ui_queue: queue.Queue[Callable[[], None]]):
        self._jobs: queue.Queue = queue.Queue()
        self._ui = ui_queue
        self._thread = threading.Thread(target=self._run, name="umwelt-gui-worker", daemon=True)
        self._thread.start()

    def submit(self, fn: Callable[[], Any], on_ok: Callable[[Any], None] | None = None,
               on_err: Callable[[BaseException], None] | None = None) -> None:
        self._jobs.put((fn, on_ok, on_err))

    def stop(self) -> None:
        self._jobs.put(None)

    def _run(self) -> None:
        while True:
            job = self._jobs.get()
            if job is None:
                return
            fn, on_ok, on_err = job
            try:
                result = fn()
            except Exception as exc:
                if on_err is not None:
                    self._ui.put(lambda cb=on_err, e=exc: cb(e))
            else:
                if on_ok is not None:
                    self._ui.put(lambda cb=on_ok, r=result: cb(r))


class Tile:
    """One live value: title, big number, small sub line."""

    def __init__(self, parent: tk.Widget, title: str, fonts: dict[str, tkfont.Font]):
        self.frame = tk.Frame(parent, bd=2, relief="groove", padx=10, pady=6, bg="#ffffff")
        self.title = tk.Label(self.frame, text=title, font=fonts["tile_title"], anchor="w",
                              bg="#ffffff", fg="#44505c")
        self.value = tk.Label(self.frame, text="--", font=fonts["tile_value"], anchor="w",
                              bg="#ffffff")
        self.sub = tk.Label(self.frame, text="", font=fonts["hint"], anchor="w", bg="#ffffff",
                            fg=COL_MUTED)
        self.title.pack(fill="x")
        self.value.pack(fill="x")
        self.sub.pack(fill="x")

    def show(self, text: str, sub: str = "", muted: bool = False, sub_error: bool = False
             ) -> None:
        self.value.configure(text=text, fg=COL_MUTED if muted else "#12355b")
        self.sub.configure(text=sub, fg=COL_ERR if sub_error else COL_MUTED)


class App:
    def __init__(self, root: tk.Tk | tk.Toplevel, port: str | None = None, *,
                 open_device: Callable[[str | None], UmweltDevice] | None = None,
                 scan_ports: Callable[[], list[str]] | None = None,
                 autoconnect: bool = True, csv_path: str | None = None):
        self.root = root
        self.ui_q: queue.Queue[Callable[[], None]] = queue.Queue()
        self.worker = Worker(self.ui_q)
        self._open_device = open_device or (lambda prt: UmweltDevice.open(prt))
        self._scan_ports = scan_ports or default_scan

        self.dev: UmweltDevice | None = None
        self.conn_state = "getrennt"     # getrennt | verbinde | verbunden
        self.loading = False
        self.status: DeviceStatus | None = None
        self.measurement: Measurement | None = None
        self.measured_at: datetime | None = None
        self.config: dict[str, int | None] = {}
        self.alarm_flags = 0
        self.unacked_flags = 0
        self.chart: collections.deque[int | None] = collections.deque(maxlen=CHART_POINTS)
        self.logger: MessLogger | None = None
        self.blink_on = False
        self._status_inflight = False
        self._poll_failures = 0
        self._next_try = 0.0
        self._scan_inflight = False
        self._closing = False

        self._setup_fonts()
        root.title("Umgebungssensoren")
        root.geometry("820x660")
        root.minsize(640, 520)
        root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.auto_var = tk.BooleanVar(value=autoconnect)
        self.port_var = tk.StringVar(value=port or AUTO_PORT)
        self.csv_on = tk.BooleanVar(value=False)
        self.csv_path = tk.StringVar(value=csv_path or default_log_path())
        self.buzzer_var = tk.BooleanVar(value=False)
        self.setting_vars = {k: tk.StringVar() for k in SETTING_KEYS}

        self._build()
        self._render()
        root.after(DRAIN_MS, self._drain)
        root.after(STATUS_MS, self._poll)
        root.after(TICK_MS, self._tick)
        root.after(200, self._reconnect_tick)

    # ------------------------------------------------------------------ build

    def _setup_fonts(self) -> None:
        base = tkfont.nametofont("TkDefaultFont")
        fam = base.actual("family")
        self.fonts = {
            "tile_title": tkfont.Font(family=fam, size=11, weight="bold"),
            "tile_value": tkfont.Font(family=fam, size=24, weight="bold"),
            "banner": tkfont.Font(family=fam, size=13, weight="bold"),
            "hint": tkfont.Font(family=fam, size=9),
            "state": tkfont.Font(family=fam, size=12, weight="bold"),
        }

    def _build(self) -> None:
        top = ttk.Frame(self.root, padding=(8, 6))
        top.pack(fill="x")
        self.conn_dot = tk.Label(top, text="●", font=self.fonts["state"], fg=COL_ERR)
        self.conn_dot.pack(side="left")
        self.conn_lbl = ttk.Label(top, text="nicht verbunden", width=40)
        self.conn_lbl.pack(side="left", padx=(2, 8))
        ttk.Label(top, text="Port:").pack(side="left")
        self.port_cb = ttk.Combobox(top, textvariable=self.port_var, width=14)
        self.port_cb.pack(side="left", padx=4)
        self.port_cb.bind("<Button-1>", lambda _e: self.refresh_ports())
        self.conn_btn = ttk.Button(top, text="Verbinden", command=self.toggle_connect)
        self.conn_btn.pack(side="left", padx=4)
        ttk.Checkbutton(top, text="automatisch", variable=self.auto_var,
                        command=lambda: setattr(self, "_next_try", 0.0)).pack(side="left")

        # alarm banner (packed only while an alarm is active)
        self.alarm_frame = tk.Frame(self.root, bd=1, relief="solid")
        self.alarm_lbl = tk.Label(self.alarm_frame, text="", font=self.fonts["banner"],
                                  anchor="w", justify="left", padx=10, pady=6, wraplength=640)
        self.alarm_lbl.pack(side="left", fill="x", expand=True)
        self.ack_btn = ttk.Button(self.alarm_frame, text="Quittieren", command=self.acknowledge)
        self.ack_btn.pack(side="right", padx=8, pady=4)

        self.nb = ttk.Notebook(self.root)
        self.nb.pack(fill="both", expand=True, padx=8, pady=(4, 2))
        self._build_live()
        self._build_settings()

        self.statusbar = ttk.Label(self.root, text="", anchor="w", padding=(8, 2))
        self.statusbar.pack(fill="x", side="bottom")
        self.message = ttk.Label(self.root, text="", anchor="w", padding=(8, 0),
                                 foreground=COL_MUTED)
        self.message.pack(fill="x", side="bottom")

    def _build_live(self) -> None:
        tab = ttk.Frame(self.nb, padding=6)
        self.nb.add(tab, text="Live")
        grid = ttk.Frame(tab)
        grid.pack(fill="x")
        for c in range(2):
            grid.columnconfigure(c, weight=1, uniform="tile")
        self.tiles = {
            "t": Tile(grid, "Temperatur", self.fonts),
            "rh": Tile(grid, "Luftfeuchte", self.fonts),
            "p": Tile(grid, "Luftdruck", self.fonts),
            "gas": Tile(grid, "Gaswiderstand (Luftqualität)", self.fonts),
        }
        for n, tile in enumerate(self.tiles.values()):
            tile.frame.grid(row=n // 2, column=n % 2, sticky="nsew", padx=4, pady=4)

        chart_box = ttk.LabelFrame(tab, text="Temperaturverlauf", padding=4)
        chart_box.pack(fill="both", expand=True, pady=(6, 0))
        self.canvas = tk.Canvas(chart_box, height=160, bg="#ffffff", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda _e: self.draw_chart())

        csvf = ttk.LabelFrame(tab, text="Messprotokoll (CSV)", padding=6)
        csvf.pack(fill="x", pady=(6, 0))
        row = ttk.Frame(csvf)
        row.pack(fill="x")
        ttk.Checkbutton(row, text="Aufzeichnen", variable=self.csv_on,
                        command=self.toggle_csv).pack(side="left")
        ttk.Entry(row, textvariable=self.csv_path, state="readonly").pack(
            side="left", padx=6, fill="x", expand=True)
        ttk.Button(row, text="Datei wählen …", command=self.choose_csv).pack(side="left")
        self.csv_state = ttk.Label(csvf, text="aus", foreground=COL_MUTED)
        self.csv_state.pack(anchor="w", pady=(4, 0))

    def _build_settings(self) -> None:
        tab = ttk.Frame(self.nb, padding=10)
        self.nb.add(tab, text="Einstellungen")
        box = ttk.LabelFrame(tab, text="Messung und Alarm (auf dem Gerät gespeichert)",
                             padding=8)
        box.pack(fill="x")
        units = {"INTERVAL": "s", "TEMP_OFFSET": "°C", "T_HI": "°C", "T_LO": "°C",
                 "RH_HI": "%", "RH_LO": "%"}
        self.setting_entries: dict[str, ttk.Entry] = {}
        for r, key in enumerate(SETTING_KEYS):
            info = p.CONFIG_KEYS[key]
            ttk.Label(box, text=info.label_de + ":").grid(row=r, column=0, sticky="w", pady=2)
            e = ttk.Entry(box, textvariable=self.setting_vars[key], width=10)
            e.grid(row=r, column=1, sticky="w", padx=6)
            self.setting_entries[key] = e
            ttk.Label(box, text=units[key]).grid(row=r, column=2, sticky="w")
            ttk.Label(box, text=p.config_range_text(info), foreground=COL_MUTED).grid(
                row=r, column=3, sticky="w", padx=(12, 0))
        r = len(SETTING_KEYS)
        ttk.Checkbutton(box, text="Piezo-Signal bei Alarm", variable=self.buzzer_var).grid(
            row=r, column=0, columnspan=4, sticky="w", pady=(6, 0))
        ttk.Label(box, foreground=COL_MUTED, wraplength=640, justify="left",
                  text="Schwellwerte leer lassen oder OFF eingeben = aus. Dezimalkomma oder "
                       "-punkt. Der Temperatur-Offset gleicht die Eigenerwärmung aus.").grid(
            row=r + 1, column=0, columnspan=4, sticky="w", pady=(6, 0))
        btns = ttk.Frame(box)
        btns.grid(row=r + 2, column=0, columnspan=4, sticky="w", pady=(8, 0))
        ttk.Button(btns, text="Übernehmen", command=self.apply_settings).pack(side="left")
        ttk.Button(btns, text="Vom Gerät laden", command=self.load_config).pack(side="left",
                                                                               padx=6)
        ttk.Button(btns, text="Standardwerte …", command=self.reset_config).pack(side="left")

        box = ttk.LabelFrame(tab, text="Uhr am Gerät", padding=8)
        box.pack(fill="x", pady=(10, 0))
        self.clock_lbl = ttk.Label(box, text="Keine Verbindung.")
        self.clock_lbl.pack(side="left")
        ttk.Button(box, text="Jetzt stellen",
                   command=lambda: self.sync_clock(manual=True)).pack(side="right")

        ttk.Label(tab, text=f"Umgebungssensoren PC-Tool {__version__} · benötigt Firmware ≥ "
                            f"{p.MIN_FW_VERSION}", foreground=COL_MUTED).pack(side="bottom",
                                                                           anchor="w")

    # ------------------------------------------------------------------ plumbing

    @property
    def connected(self) -> bool:
        return self.conn_state == "verbunden" and self.dev is not None

    def _drain(self) -> None:
        try:
            while True:
                fn = self.ui_q.get_nowait()
                try:
                    fn()
                except Exception as exc:  # keep the loop alive
                    log.debug("UI-Callback fehlgeschlagen", exc_info=True)
                    self.say(f"Interner Fehler: {exc}", error=True)
        except queue.Empty:
            pass
        if not self._closing:
            self.root.after(DRAIN_MS, self._drain)

    def say(self, text: str, error: bool = False) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        self.message.configure(text=f"{stamp}  {text}", foreground=COL_ERR if error else COL_MUTED)

    def _error(self, exc: BaseException, title: str = "Fehler") -> None:
        msg = friendly_error(exc)
        self.say(f"{title}: {msg}", error=True)
        messagebox.showerror(title, msg, parent=self.root)

    def run_device(self, fn: Callable[[UmweltDevice], Any], ok_msg: str | None = None,
                   done: Callable[[Any], None] | None = None) -> None:
        """Run ``fn(device)`` in the worker; show errors as German dialogs."""
        dev = self.dev
        if dev is None or not self.connected:
            messagebox.showwarning("Nicht verbunden", "Keine Verbindung zum Gerät. "
                                   "Bitte USB-Kabel prüfen.", parent=self.root)
            return

        def ok(result: Any) -> None:
            if ok_msg:
                self.say(ok_msg)
            if done:
                done(result)
            self.request_status()

        self.worker.submit(lambda: fn(dev), ok, self._error)

    # ------------------------------------------------------------------ connection

    def refresh_ports(self) -> None:
        self.worker.submit(self._scan_ports,
                           lambda ports: self.port_cb.configure(values=[AUTO_PORT, *ports]),
                           lambda _e: None)

    def _selected_port(self) -> str | None:
        text = self.port_var.get().strip()
        return None if not text or text == AUTO_PORT else text.split(" ", 1)[0]

    def toggle_connect(self) -> None:
        if self.conn_state == "verbunden":
            self.auto_var.set(False)
            self.disconnect("getrennt (automatisches Verbinden aus)")
        elif self.conn_state == "getrennt":
            self._connect(self._selected_port(), manual=True)

    def _reconnect_tick(self) -> None:
        if self._closing:
            return
        self.root.after(RECONNECT_MS, self._reconnect_tick)
        if (self.conn_state != "getrennt" or not self.auto_var.get() or self._scan_inflight
                or time.monotonic() < self._next_try):
            return
        wanted = self._selected_port()
        if wanted is not None:
            self._connect(wanted, manual=False)
            return
        self._scan_inflight = True

        def done(ports: list[str]) -> None:
            self._scan_inflight = False
            if not ports:
                self._set_conn("getrennt", "Warte auf das Gerät … (USB-Kabel einstecken)")
            elif self.conn_state == "getrennt" and self.auto_var.get():
                self._connect(ports[0], manual=False)

        def err(_exc: BaseException) -> None:
            self._scan_inflight = False

        self.worker.submit(self._scan_ports, done, err)

    def _connect(self, port: str | None, manual: bool) -> None:
        self._set_conn("verbinde", f"verbinde mit {port or 'Gerät'} …")

        def ok(dev: UmweltDevice) -> None:
            if self._closing:
                dev.close()
                return
            self.dev = dev
            self._poll_failures = 0
            dev.subscribe(lambda ev: self.ui_q.put(lambda: self.on_event(ev)))
            self._set_conn("verbunden", f"verbunden: {dev.port or port or '?'} · "
                                        f"Firmware {dev.fw_version}")
            self.say(f"Verbunden mit {dev.port or port} (Firmware {dev.fw_version})")
            self._initial_load()

        def err(exc: BaseException) -> None:
            if isinstance(exc, FirmwareTooOld):
                self.auto_var.set(False)  # retrying is pointless until the firmware is updated
                self._set_conn("getrennt", "Firmware zu alt – bitte aktualisieren")
                messagebox.showerror("Firmware zu alt", str(exc), parent=self.root)
                return
            self._next_try = time.monotonic() + RETRY_AFTER_FAIL_S
            msg = friendly_error(exc)
            self._set_conn("getrennt", "Verbindung fehlgeschlagen – neuer Versuch folgt")
            self.say(f"Verbindung fehlgeschlagen: {msg}", error=True)
            if manual:
                messagebox.showerror("Verbindung fehlgeschlagen", msg, parent=self.root)

        self.worker.submit(lambda: self._open_device(port), ok, err)

    def _initial_load(self) -> None:
        dev = self.dev
        if dev is None:
            return
        self.loading = True
        self._render()

        def job() -> tuple[DeviceStatus, Measurement | BaseException, dict[str, int | None]]:
            dev.set_stream(True)
            dev.sync_time()
            st = dev.status()
            try:
                m: Measurement | BaseException = dev.read()
            except DeviceError as exc:  # ERR 5: sensor missing -> own state, not a failure
                m = exc
            return st, m, dev.get_config()

        def ok(res: tuple[DeviceStatus, Measurement | BaseException, dict[str, int | None]]
               ) -> None:
            self.loading = False
            st, m, cfg = res
            self._on_status(st)
            if isinstance(m, Measurement):
                self.measurement, self.measured_at = m, datetime.now()
            else:
                self.measurement = None
            self._on_config(cfg)
            self.clock_lbl.configure(text=f"Gestellt auf PC-Zeit ({datetime.now():%H:%M:%S})")
            self._render()

        def err(exc: BaseException) -> None:
            self.loading = False
            self.say(f"Laden fehlgeschlagen: {friendly_error(exc)}", error=True)
            self._render()

        self.worker.submit(job, ok, err)

    def disconnect(self, reason: str) -> None:
        dev, self.dev = self.dev, None
        if dev is not None:
            self.worker.submit(dev.close)
        self._status_inflight = False
        self.loading = False
        self._set_conn("getrennt", reason)
        self.say(reason, error=True)

    def _set_conn(self, state: str, text: str) -> None:
        self.conn_state = state
        color = {"verbunden": "#1e9e3c", "verbinde": "#e0a800"}.get(state, COL_ERR)
        self.conn_dot.configure(fg=color)
        self.conn_lbl.configure(text=text)
        self.conn_btn.configure(text="Trennen" if state == "verbunden" else "Verbinden",
                                state="disabled" if state == "verbinde" else "normal")
        if state != "verbunden":
            self.clock_lbl.configure(text="Keine Verbindung.")
        self._render()

    # ------------------------------------------------------------------ polling

    def _poll(self) -> None:
        if self._closing:
            return
        self.request_status()
        self.root.after(STATUS_MS, self._poll)

    def request_status(self) -> None:
        dev = self.dev
        if dev is None or self._status_inflight or not self.connected:
            return
        self._status_inflight = True

        def ok(st: DeviceStatus) -> None:
            self._status_inflight = False
            self._poll_failures = 0
            if dev is self.dev:
                self._on_status(st)

        def err(exc: BaseException) -> None:
            self._status_inflight = False
            if dev is not self.dev:
                return
            self._poll_failures += 1
            if isinstance(exc, DeviceDisconnected) or self._poll_failures >= MAX_POLL_FAILURES:
                self.disconnect("Verbindung verloren – warte auf das Gerät …")

        self.worker.submit(dev.status, ok, err)

    def _on_status(self, st: DeviceStatus) -> None:
        self.status = st
        self.alarm_flags = st.alarm_flags
        self.unacked_flags = st.unacked_flags
        if st.sensor == p.SENSOR_MISSING:
            self.measurement = None
        self._render()

    # ------------------------------------------------------------------ events

    def on_event(self, ev: Event) -> None:
        if ev.kind == "DISCONNECTED":
            if self.dev is not None:
                self.disconnect(f"Verbindung verloren ({ev.raw}) – warte auf das Gerät …")
            return
        if ev.kind == p.EVT_DATA and ev.measurement is not None:
            self.on_measurement(ev.measurement)
        elif ev.kind == p.EVT_ALARM and ev.flag is not None:
            text = p.ALARM_TEXT_DE[ev.flag]
            self.say(f"Alarm {'aktiv' if ev.active else 'beendet'}: {text}", error=ev.active)
            if ev.active:
                self.alarm_flags |= ev.flag
                self.unacked_flags |= ev.flag
                self._attention()
            else:
                self.alarm_flags &= ~ev.flag
                self.unacked_flags &= ~ev.flag
            self._render()
            self.request_status()
        elif ev.kind == p.EVT_SENSOR:
            self.say(p.SENSOR_TEXT_DE.get(ev.sensor or "", str(ev.sensor)),
                     error=ev.sensor != p.SENSOR_OK)
            self.request_status()
        elif ev.kind == p.EVT_BOOT:
            # the device layer has already re-read STATUS, re-sent TIME and STREAM
            self.say("Gerät wurde neu gestartet – Uhr und Datenstrom neu gesetzt.", error=True)
            self.request_status()
            self.load_config()

    def on_measurement(self, m: Measurement) -> None:
        self.measurement, self.measured_at = m, datetime.now()
        self.chart.append(m.t)
        if self.logger is not None:
            self._write_csv(m)
        self._render()
        self.draw_chart()

    def _attention(self) -> None:
        try:
            self.root.bell()
        except tk.TclError:
            pass

    # ------------------------------------------------------------------ rendering

    def _tick(self) -> None:
        if self._closing:
            return
        self.blink_on = not self.blink_on
        self._render_alarm()
        self.root.after(TICK_MS, self._tick)

    def view_state(self) -> str:
        """``getrennt`` / ``laden`` / ``sensorfehler`` / ``werte``."""
        if not self.connected:
            return "getrennt"
        if self.loading or self.status is None:
            return "laden"
        if self.status.sensor != p.SENSOR_OK and (self.measurement is None
                                                   or not self.measurement.any_valid):
            return "sensorfehler"
        return "werte"

    def _render(self) -> None:
        state = self.view_state()
        m = self.measurement
        if state == "getrennt":
            text = "Verbinde …" if self.conn_state == "verbinde" else "keine Verbindung"
            for tile in self.tiles.values():
                tile.show("--", text, muted=True)
        elif state == "laden":
            for tile in self.tiles.values():
                tile.show("…", "lade Werte vom Gerät", muted=True)
        elif state == "sensorfehler":
            assert self.status is not None
            for tile in self.tiles.values():
                tile.show("--", self.status.sensor_text, muted=True, sub_error=True)
        elif m is None or not m.any_valid:
            for tile in self.tiles.values():
                tile.show("--", "noch keine gültige Messung", muted=True)
        else:
            age = f"gemessen {self.measured_at:%H:%M:%S}" if self.measured_at else ""
            for key, text in (("t", p.format_temperature(m.t)),
                              ("rh", p.format_humidity(m.rh)),
                              ("p", p.format_pressure(m.p)),
                              ("gas", p.format_gas(m.gas))):
                invalid = getattr(m, key) is None
                self.tiles[key].show(text, "ungültig" if invalid else age, muted=invalid,
                                     sub_error=invalid)
        self._render_statusbar()
        self._render_alarm()

    def _render_statusbar(self) -> None:
        if not self.connected:
            self.statusbar.configure(text="Keine Verbindung zum Gerät.")
            return
        st = self.status
        if st is None:
            self.statusbar.configure(text="Lade Status …")
            return
        parts = [st.sensor_text, f"Intervall {st.interval} s",
                 f"Laufzeit {p.format_uptime(st.uptime_sec)}"]
        if self.dev is not None and self.dev.fw_version:
            parts.append(f"Firmware {self.dev.fw_version}")
        self.statusbar.configure(text=" · ".join(parts))

    def _render_alarm(self) -> None:
        flags = self.alarm_flags if self.connected else 0
        if not flags:
            if self.alarm_frame.winfo_manager():
                self.alarm_frame.pack_forget()
            return
        unacked = self.unacked_flags & flags
        texts = p.alarm_texts(flags)
        state = "nicht quittiert" if unacked else "quittiert"
        self.alarm_lbl.configure(text=f"⚠ ALARM ({state}): " + ", ".join(texts))
        if unacked:
            bg, fg = COL_ALARM_BLINK if self.blink_on else COL_ALARM
            self.ack_btn.state(["!disabled"])
        else:
            bg, fg = COL_ALARM_ACKED
            self.ack_btn.state(["disabled"])
        self.alarm_frame.configure(bg=bg)
        self.alarm_lbl.configure(bg=bg, fg=fg)
        if not self.alarm_frame.winfo_manager():
            self.alarm_frame.pack(fill="x", padx=8, pady=(0, 4), after=self.conn_dot.master)

    def draw_chart(self) -> None:
        c = self.canvas
        c.delete("all")
        w, h = max(c.winfo_width(), 50), max(c.winfo_height(), 50)
        values = [v for v in self.chart if v is not None]
        if len(values) < 2:
            c.create_text(w // 2, h // 2, text="Noch zu wenige Messwerte für einen Verlauf.",
                          fill=COL_MUTED)
            return
        lo, hi = min(values), max(values)
        if hi - lo < 50:  # at least 0.5 °C span
            mid = (hi + lo) // 2
            lo, hi = mid - 25, mid + 25
        left, right, top, bottom = 70, w - 10, 10, h - 20
        n = self.chart.maxlen or len(self.chart)
        step = (right - left) / max(1, n - 1)
        offset = n - len(self.chart)

        def y(v: int) -> float:
            return bottom - (v - lo) * (bottom - top) / (hi - lo)

        for v in (lo, hi):
            c.create_line(left, y(v), right, y(v), fill="#e0e0e0")
            c.create_text(left - 6, y(v), text=p.format_temperature(v), anchor="e",
                          fill="#44505c")
        segment: list[float] = []
        for i, v in enumerate(self.chart):
            if v is None:  # invalid value -> gap in the line
                if len(segment) >= 4:
                    c.create_line(*segment, fill="#2f7fd8", width=2)
                segment = []
                continue
            segment += [left + (offset + i) * step, y(v)]
        if len(segment) >= 4:
            c.create_line(*segment, fill="#2f7fd8", width=2)
        c.create_text(right, h - 4, text=f"letzte {len(self.chart)} Messungen", anchor="se",
                      fill=COL_MUTED)

    # ------------------------------------------------------------------ actions

    def acknowledge(self) -> None:
        def done(_r: Any) -> None:
            self.unacked_flags = 0
            self._render()

        self.run_device(lambda d: d.ack(), "Alarm quittiert.", done)

    def _on_config(self, cfg: dict[str, int | None]) -> None:
        self.config = dict(cfg)
        for key in SETTING_KEYS:
            if key in cfg:
                v = cfg[key]
                self.setting_vars[key].set("" if v is None else p.config_input_text(key, v))
        if "BUZZER" in cfg:
            self.buzzer_var.set(bool(cfg["BUZZER"]))

    def load_config(self) -> None:
        dev = self.dev
        if dev is None or not self.connected:
            return
        self.worker.submit(dev.get_config, self._on_config,
                           lambda e: self.say(f"Einstellungen nicht lesbar: {friendly_error(e)}",
                                              error=True))

    def pending_settings(self) -> list[tuple[str, str]]:
        """Changed settings as ``(key, wire value)``; ValueError (German) for bad input."""
        changes: list[tuple[str, str]] = []
        for key in SETTING_KEYS:
            wire = p.parse_config_input(key, self.setting_vars[key].get())
            current = self.config.get(key)
            current_wire = p.CFG_OFF if current is None else str(current)
            if key not in self.config or wire != current_wire:
                changes.append((key, wire))
        buzzer = "1" if self.buzzer_var.get() else "0"
        if "BUZZER" not in self.config or str(self.config["BUZZER"]) != buzzer:
            changes.append(("BUZZER", buzzer))
        return changes

    def apply_settings(self) -> None:
        try:
            changes = self.pending_settings()
        except ValueError as exc:
            messagebox.showerror("Ungültige Eingabe", str(exc), parent=self.root)
            return
        if not changes:
            self.say("Keine Änderungen.")
            return

        def job(d: UmweltDevice) -> dict[str, int | None]:
            for key, wire in changes:
                d.set_config(key, wire)
            return d.get_config()

        names = ", ".join(p.CONFIG_KEYS[k].label_de for k, _ in changes)
        self.run_device(job, f"Gespeichert: {names}", self._on_config)

    def reset_config(self) -> None:
        if not messagebox.askyesno(
                "Standardwerte", "Alle Einstellungen (Intervall, Schwellwerte, Offset, Piezo) "
                "auf Standardwerte zurücksetzen?\nDie Touch-Kalibrierung bleibt erhalten.",
                icon="warning", parent=self.root):
            return

        def job(d: UmweltDevice) -> dict[str, int | None]:
            d.reset_config()
            return d.get_config()

        self.run_device(job, "Einstellungen auf Standardwerte zurückgesetzt.", self._on_config)

    def sync_clock(self, manual: bool = False) -> None:
        def done(sent: datetime) -> None:
            self.clock_lbl.configure(text=f"Gestellt auf PC-Zeit ({sent:%H:%M:%S})")

        if manual or self.connected:
            self.run_device(lambda d: d.sync_time(), "Uhr am Gerät gestellt.", done)

    # ------------------------------------------------------------------ CSV

    def _write_csv(self, m: Measurement) -> None:
        assert self.logger is not None
        try:
            self.logger.write(m, self.alarm_flags if self.connected else None)
            self.csv_state.configure(text=f"aktiv – {self.logger.rows_written} Zeile(n) in "
                                          f"{self.logger.path}", foreground=COL_OK)
        except OSError:
            self.csv_state.configure(text=f"Datei gesperrt (in Excel geöffnet?) – "
                                          f"{self.logger.pending} Zeile(n) warten",
                                     foreground=COL_ERR)

    def toggle_csv(self) -> None:
        if self.logger is not None:
            self.logger.close()
            self.logger = None
        if not self.csv_on.get():
            self.csv_state.configure(text="aus", foreground=COL_MUTED)
            return
        try:
            self.logger = MessLogger(self.csv_path.get())
        except OSError as exc:
            self.csv_on.set(False)
            self.csv_state.configure(text=f"aus – Datei nicht nutzbar: {exc}",
                                     foreground=COL_ERR)
            return
        self.csv_state.configure(text=f"aktiv – schreibt nach {self.logger.path}",
                                 foreground=COL_OK)

    def choose_csv(self) -> None:
        current = self.csv_path.get()
        path = filedialog.asksaveasfilename(
            parent=self.root, title="CSV-Messprotokoll wählen", defaultextension=".csv",
            initialdir=os.path.dirname(current) or os.path.expanduser("~"),
            initialfile=os.path.basename(current), confirmoverwrite=False,
            filetypes=[("CSV-Dateien", "*.csv"), ("Alle Dateien", "*.*")])
        if path:
            self.csv_path.set(os.path.normpath(path))
            if self.csv_on.get():
                self.toggle_csv()

    # ------------------------------------------------------------------ shutdown

    def on_close(self) -> None:
        self._closing = True
        if self.logger is not None:
            self.logger.close()
        self.worker.stop()
        dev, self.dev = self.dev, None
        if dev is not None:
            dev.close()  # always release the port (a leaked handle blocks uploads)
        self.root.destroy()


def _enable_dpi_awareness() -> None:
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover - not Windows / not supported
        pass


def main(port: str | None = None) -> int:
    """Entry point of ``umwelt gui``."""
    _enable_dpi_awareness()
    root = tk.Tk()
    App(root, port)
    root.mainloop()
    return 0
