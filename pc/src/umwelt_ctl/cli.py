"""Kommandozeilen-Tool ``umwelt`` (auch ``python -m umwelt_ctl``)."""

from __future__ import annotations

import argparse
import datetime
import logging
import queue
import sys
import time
from collections.abc import Callable, Sequence

from . import __version__
from . import protocol as p
from .device import (
    PORT_ENV,
    DeviceDisconnected,
    DeviceTimeout,
    FirmwareTooOld,
    UmweltDevice,
    list_all_ports,
)
from .messlog import MessLogger, default_log_path, timestamp
from .protocol import DeviceError, DeviceStatus, Event, Measurement

EXIT_OK = 0
EXIT_DEVICE = 1       # ERR from the device, timeout during a command
EXIT_CONNECT = 2      # no device / port busy / wrong device / bad arguments


def _open_device(port: str | None) -> UmweltDevice:
    return UmweltDevice.open(port)


# Replaceable for tests: (port) -> connected device
open_device: Callable[[str | None], UmweltDevice] = _open_device


def _never_stop() -> bool:
    return False


# Replaceable for tests: monitor stops when this returns True (Ctrl+C otherwise)
monitor_should_stop: Callable[[], bool] = _never_stop


# --------------------------------------------------------------------------- argparse in German


class _DeFormatter(argparse.HelpFormatter):
    def add_usage(self, usage, actions, groups, prefix=None):  # noqa: D102
        super().add_usage(usage, actions, groups, "Aufruf: " if prefix is None else prefix)


class _DeParser(argparse.ArgumentParser):
    """ArgumentParser with German headings, help option and error messages."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("formatter_class", _DeFormatter)
        kwargs["add_help"] = False
        super().__init__(*args, **kwargs)
        self._optionals.title = "Optionen"
        self._positionals.title = "Argumente"
        self.add_argument("-h", "--help", action="help", help="diese Hilfe anzeigen und beenden")

    _MSG_DE = (
        ("the following arguments are required:", "folgende Argumente fehlen:"),
        ("unrecognized arguments:", "unbekannte Argumente:"),
        ("invalid choice:", "ungültige Auswahl:"),
        ("choose from", "möglich:"),
        ("expected one argument", "erwartet einen Wert"),
        ("invalid float value:", "ungültige Zahl:"),
        ("argument ", "Argument "),
    )

    def error(self, message: str):
        for en, de in self._MSG_DE:
            message = message.replace(en, de)
        self.print_usage(sys.stderr)
        self.exit(EXIT_CONNECT, f"{self.prog}: Fehler: {message}\n")


def _positive_seconds(text: str) -> float:
    try:
        v = float(text.replace(",", "."))
    except ValueError:
        raise argparse.ArgumentTypeError(f"{text!r} ist keine Zahl") from None
    if not 1 <= v <= 86400:
        raise argparse.ArgumentTypeError("Abfrageintervall 1 … 86400 s")
    return v


def build_parser() -> argparse.ArgumentParser:
    ap = _DeParser(
        prog="umwelt",
        description="PC-Tool für die Umgebungssensoren-Anzeige (Arduino Uno + BME680): "
                    "Werte lesen, Einstellungen ändern, Messprotokoll als CSV.",
        epilog="Beim Verbinden wird das Gerät nicht neu gestartet. Nur ein Programm kann den "
               "Port gleichzeitig benutzen (GUI, monitor, Arduino IDE, Upload).",
    )
    ap.add_argument("--port", help=f"serieller Port (z. B. COM9). Standard: Umgebungsvariable "
                                   f"{PORT_ENV}, sonst automatische Erkennung über "
                                   f"USB-VID 0x2341")
    ap.add_argument("-v", "--verbose", action="store_true",
                    help="serielle Kommunikation ausgeben (Fehlersuche)")
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}",
                    help="Programmversion anzeigen und beenden")
    sub = ap.add_subparsers(dest="cmd", metavar="BEFEHL", title="Befehle",
                            parser_class=_DeParser)
    sub.required = True

    sub.add_parser("ping", help="Verbindung prüfen, Firmware-Version anzeigen")
    sub.add_parser("status", help="Sensorzustand, Messintervall, Laufzeit und Alarme anzeigen")
    sub.add_parser("ports", help="verfügbare serielle Ports auflisten")
    sub.add_parser("read", help="aktuelle Messwerte anzeigen")

    keys = ", ".join(p.CONFIG_KEYS)
    a = sub.add_parser(
        "config", help="Einstellungen anzeigen/ändern; „config reset“ = Standardwerte",
        description="Ohne Argumente: alle Einstellungen anzeigen. Mit SCHLÜSSEL: nur diese. "
                    "Mit SCHLÜSSEL WERT: ändern (sofort wirksam, auf dem Gerät gespeichert). "
                    "„config reset“ setzt alle Einstellungen auf Standardwerte zurück "
                    "(Touch-Kalibrierung bleibt).",
        epilog="Werte in physikalischen Einheiten, Komma oder Punkt: "
               "INTERVAL in s (1 … 3600), TEMP_OFFSET in °C (−50 … 50), T_HI/T_LO in °C "
               "(−40 … 85), RH_HI/RH_LO in % (0 … 100), Schwellwerte auch OFF; "
               "BUZZER 0/1 bzw. an/aus. Beispiel: umwelt config T_HI 28,5")
    a.add_argument("key", nargs="?", metavar="SCHLÜSSEL", help=f"{keys} oder reset")
    a.add_argument("value", nargs="?", metavar="WERT", help="neuer Wert")
    a.add_argument("-y", "--yes", action="store_true",
                   help="„config reset“ ohne Rückfrage ausführen")

    sub.add_parser("ack", help="aktiven Alarm am Gerät quittieren (Anzeige/Ton aus)")

    a = sub.add_parser("time", help="Uhr am Gerät anzeigen (Gerät, PC, Abweichung) bzw. mit "
                                    "„time sync“ auf die PC-Zeit stellen")
    a.add_argument("action", nargs="?", choices=["sync"], metavar="sync",
                   help="Uhr des Geräts auf die PC-Zeit stellen")

    a = sub.add_parser("monitor", help="Messwerte und Ereignisse live anzeigen, optional als "
                                       "CSV protokollieren (Strg+C beendet)")
    a.add_argument("--csv", metavar="DATEI", nargs="?", const=default_log_path(),
                   help="Messwerte an diese CSV-Datei anhängen; ohne DATEI: %(const)s. "
                        "Lokale Messdaten – nicht ins Repository legen")
    a.add_argument("--interval", metavar="S", type=_positive_seconds,
                   help="Werte alle S Sekunden mit READ abfragen. Ohne diese Option sendet "
                        "das Gerät jede neue Messung selbst (STREAM, Messintervall des Geräts)")

    sub.add_parser("gui", help="grafische Oberfläche starten")
    return ap


# --------------------------------------------------------------------------- output helpers


def format_measurement(m: Measurement) -> str:
    rows = [
        ("Temperatur", p.format_temperature(m.t)),
        ("Feuchte", p.format_humidity(m.rh)),
        ("Druck", p.format_pressure(m.p)),
        ("Gaswiderstand", p.format_gas(m.gas, kilo=False)
         + (f" ({p.format_gas(m.gas)})" if m.gas is not None else "")),
        ("Alter", "noch keine Messung" if m.age_sec is None else f"{m.age_sec} s"),
    ]
    return "\n".join(f"{k + ':':<15}{v}" for k, v in rows)


def format_flags(flags: int, unacked: int = 0) -> str:
    if not flags:
        return "keiner"
    parts = []
    for f in p.ALARM_FLAGS:
        if flags & f:
            text = p.ALARM_TEXT_DE[f]
            parts.append(text + (" (nicht quittiert)" if unacked & f else ""))
    return ", ".join(parts)


def format_status(st: DeviceStatus) -> str:
    rows = [
        ("Sensor", st.sensor_text),
        ("Messintervall", f"{st.interval} s"),
        ("Laufzeit", p.format_uptime(st.uptime_sec)),
        ("Alarm", format_flags(st.alarm_flags, st.unacked_flags)),
    ]
    return "\n".join(f"{k + ':':<15}{v}" for k, v in rows)


def format_live(m: Measurement, flags: int | None, now: datetime.datetime | None = None) -> str:
    parts = [timestamp(now), f"{p.format_temperature(m.t):>10}", f"{p.format_humidity(m.rh):>11}",
             f"{p.format_pressure(m.p):>11}", f"{p.format_gas(m.gas):>10}"]
    if flags:
        parts.append(f"ALARM: {format_flags(flags)}")
    return "  ".join(parts)


def _confirm(question: str) -> bool:
    try:
        answer = input(f"{question} [j/N] ")
    except EOFError:
        return False
    return answer.strip().lower() in ("j", "ja", "y", "yes")


# --------------------------------------------------------------------------- commands


def _cmd_config(dev: UmweltDevice, args) -> int:
    key = args.key.upper() if args.key else None
    if key == "RESET":
        dev.reset_config()
        print("Einstellungen auf Standardwerte zurückgesetzt (Touch-Kalibrierung bleibt).")
        return EXIT_OK
    if key and args.value is not None:
        old = dev.get_config().get(key)
        wire = p.parse_config_input(key, args.value)
        dev.set_config(key, wire)
        new = None if wire == p.CFG_OFF else int(wire)
        print(f"{p.CONFIG_KEYS[key].label_de} ({key}): {p.format_config_value(key, old)} → "
              f"{p.format_config_value(key, new)}")
        return EXIT_OK
    cfg = dev.get_config()
    shown = [key] if key else [k for k in p.CONFIG_KEYS if k in cfg]
    for k in shown:
        if k not in cfg:
            print(f"Das Gerät hat die Einstellung {k} nicht gemeldet.", file=sys.stderr)
            return EXIT_DEVICE
        label = p.CONFIG_KEYS[k].label_de
        print(f"{k:<12} {p.format_config_value(k, cfg[k]):<12} {label}")
    return EXIT_OK


def _sync_clock(dev: UmweltDevice, quiet: bool = False) -> bool:
    try:
        sent = dev.sync_time()
    except (DeviceError, DeviceTimeout, DeviceDisconnected, p.ProtocolError) as exc:
        print(f"Warnung: Uhr konnte nicht gestellt werden: {exc}", file=sys.stderr)
        return False
    if not quiet:
        print(f"Uhr am Gerät gestellt: {sent:%H:%M:%S}")
    return True


def _cmd_time(dev: UmweltDevice, args) -> int:
    if args.action == "sync":
        return EXIT_OK if _sync_clock(dev) else EXIT_DEVICE
    device_time = dev.get_time()
    pc_now = datetime.datetime.now().replace(microsecond=0)
    if device_time is None:
        print(f"Gerät: nicht gestellt   PC: {pc_now:%H:%M:%S}")
        print("Stellen mit: umwelt time sync")
        return EXIT_OK
    diff = p.clock_difference_sec(device_time, pc_now.time())
    print(f"Gerät: {p.format_clock(device_time)}   PC: {pc_now:%H:%M:%S}   "
          f"Abweichung: {diff:+d} s")
    return EXIT_OK


EVENT_TEXT_DE = {
    p.EVT_BOOT: "Gerät neu gestartet – Uhr und Datenstrom werden neu gesetzt",
}


def _cmd_monitor(dev: UmweltDevice, args) -> int:
    events: queue.Queue[Event] = queue.Queue()
    unsubscribe = dev.subscribe(events.put)
    st = dev.status()
    flags = st.alarm_flags
    print(format_status(st))
    logger: MessLogger | None = None
    if args.csv:
        try:
            logger = MessLogger(args.csv)
        except OSError as exc:
            print(f"Fehler: CSV-Datei kann nicht angelegt werden: {exc}", file=sys.stderr)
            unsubscribe()
            return EXIT_DEVICE
        print(f"Messprotokoll: {logger.path}")
    _sync_clock(dev, quiet=True)
    last_sync = time.monotonic()
    poll = args.interval
    stream = poll is None
    next_poll = time.monotonic()
    if stream:
        dev.set_stream(True)
        print(f"Warte auf Messwerte (alle {st.interval} s) … (Strg+C beendet)")
    else:
        print(f"Frage alle {poll:g} s ab … (Strg+C beendet)")
    sys.stdout.flush()

    def measurement(m: Measurement, current_flags: int) -> None:
        print(format_live(m, current_flags))
        sys.stdout.flush()
        if logger is not None:
            try:
                logger.write(m, current_flags)
            except OSError as exc:
                print(f"Warnung: CSV-Datei gesperrt (in Excel geöffnet?) – {logger.pending} "
                      f"Zeile(n) warten: {exc}", file=sys.stderr)

    try:
        while not monitor_should_stop():
            now = time.monotonic()
            if now - last_sync >= p.TIME_RESYNC_SEC:
                _sync_clock(dev, quiet=True)
                last_sync = now
            if not stream and now >= next_poll:
                next_poll += poll
                try:
                    measurement(dev.read(), flags)
                except DeviceError as exc:
                    if exc.code != p.ERR_SENSOR:
                        raise
                    # sensor missing: an explicit row without values ("keine Daten" = alarm 16)
                    flags |= p.ALARM_SENSOR
                    measurement(Measurement(), flags)
            try:
                ev = events.get(timeout=0.2)  # short timeout keeps Ctrl+C responsive
            except queue.Empty:
                continue
            if ev.kind == "DISCONNECTED":
                print(f"Verbindung verloren: {ev.raw}", file=sys.stderr)
                return EXIT_DEVICE
            if ev.kind == p.EVT_DATA and stream and ev.measurement is not None:
                measurement(ev.measurement, flags)
            elif ev.kind == p.EVT_ALARM and ev.flag is not None:
                flags = flags | ev.flag if ev.active else flags & ~ev.flag
                state = "aktiv" if ev.active else "beendet"
                print(f"{timestamp()}  Alarm {state}: {p.ALARM_TEXT_DE[ev.flag]}")
            elif ev.kind == p.EVT_SENSOR:
                print(f"{timestamp()}  {p.SENSOR_TEXT_DE.get(ev.sensor or '', ev.sensor)}")
                if ev.sensor == p.SENSOR_OK and not stream:
                    flags &= ~p.ALARM_SENSOR
            elif ev.kind == p.EVT_BOOT:
                print(f"{timestamp()}  {EVENT_TEXT_DE[p.EVT_BOOT]} (Firmware {ev.fw_version})")
                if dev.last_status is not None:
                    flags = dev.last_status.alarm_flags
            sys.stdout.flush()
    except KeyboardInterrupt:
        print("\nBeendet.")
    finally:
        unsubscribe()
        if stream:
            try:
                dev.set_stream(False)
            except (DeviceError, DeviceTimeout, DeviceDisconnected):
                pass
        if logger is not None:
            logger.close()
            print(f"Messprotokoll: {logger.rows_written} Zeile(n) in {logger.path}")
    return EXIT_OK


def run_command(dev: UmweltDevice, args) -> int:
    cmd = args.cmd
    if cmd == "ping":
        print(f"PONG – {p.PRODUCT} Firmware {dev.ping()} an {dev.port or '?'}")
    elif cmd == "status":
        print(format_status(dev.status()))
    elif cmd == "read":
        print(format_measurement(dev.read()))
    elif cmd == "config":
        return _cmd_config(dev, args)
    elif cmd == "ack":
        dev.ack()
        print("Alarm quittiert (Anzeige/Ton aus; das Flag bleibt, solange die Ursache besteht).")
    elif cmd == "time":
        return _cmd_time(dev, args)
    elif cmd == "monitor":
        return _cmd_monitor(dev, args)
    else:  # pragma: no cover
        raise ValueError(cmd)
    return EXIT_OK


def _safe_console() -> None:
    """Never crash on characters the console code page cannot show."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(errors="replace")
            except (ValueError, OSError):
                pass


def main(argv: Sequence[str] | None = None) -> int:
    _safe_console()
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.WARNING,
                        format="%(levelname)s %(message)s")

    if args.cmd == "gui":
        from .gui import main as gui_main
        return gui_main(args.port)
    if args.cmd == "ports":
        ports = list_all_ports()
        if not ports:
            print("Keine seriellen Ports gefunden.")
        for name, desc, arduino in ports:
            print(f"{name:<8} {desc}" + ("   ← Arduino" if arduino else ""))
        return EXIT_OK
    if args.cmd == "config":
        key = args.key.upper() if args.key else None
        if key == "RESET":
            if args.value is not None:
                parser.error("„config reset“ erwartet keinen Wert")
            if not args.yes and not _confirm(
                    "Alle Einstellungen (Intervall, Schwellwerte, Offset, Piezo) auf "
                    "Standardwerte zurücksetzen?"):
                print("Abgebrochen.")
                return EXIT_DEVICE
        elif key is not None:
            try:
                p.config_key(key)
                if args.value is not None:
                    p.parse_config_input(key, args.value)  # validate before connecting
            except ValueError as exc:
                parser.error(str(exc))

    try:
        dev = open_device(args.port)
    except FirmwareTooOld as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return EXIT_CONNECT
    except (DeviceDisconnected, DeviceTimeout, DeviceError, p.ProtocolError, OSError) as exc:
        print(f"Fehler: Verbindung fehlgeschlagen: {exc}", file=sys.stderr)
        print("Hinweis: Ist das Gerät angesteckt? Ist der Port frei (Arduino IDE, seriellen "
              "Monitor, GUI schließen)? Ggf. --port angeben.", file=sys.stderr)
        return EXIT_CONNECT
    try:
        return run_command(dev, args)
    except DeviceError as exc:
        print(f"Fehler vom Gerät: {exc}", file=sys.stderr)
        return EXIT_DEVICE
    except (DeviceTimeout, DeviceDisconnected, p.ProtocolError, ValueError) as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return EXIT_DEVICE
    finally:
        dev.close()


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
