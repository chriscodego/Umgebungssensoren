"""Pure parsing/formatting of the Umgebungssensoren serial protocol (no I/O, no Tk).

Contract: docs/SPEC.md, section "Serielles Protokoll" (protocol version 1).

This is the ONLY place where scaled wire integers are converted into physical units
(°C, %rF, hPa, Ω). Values are kept as exact integers; formatting with a decimal comma uses
integer arithmetic, so there is no float drift in displayed or logged values.
"""

from __future__ import annotations

import datetime as _dt
import logging
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

log = logging.getLogger(__name__)

BAUDRATE = 115200
MAX_LINE_LEN = 80  # bytes, without the line end
PRODUCT = "Umgebungssensoren"
ENCODING = "ascii"  # wire format is ASCII; incoming bytes are decoded leniently

# Oldest firmware this PC tool works with (protocol version 1).
MIN_FW_VERSION = "0.1.0"
TIME_RESYNC_SEC = 600  # re-send the PC time every 10 minutes while connected

# --------------------------------------------------------------------------- error codes

ERR_UNKNOWN_COMMAND = 1
ERR_BAD_ARGS = 2
ERR_OUT_OF_RANGE = 3
ERR_SENSOR = 5
ERR_WRONG_STATE = 7

# The one table mapping every SPEC error code to a German message.
ERROR_TEXTS_DE: dict[int, str] = {
    ERR_UNKNOWN_COMMAND: "Das Gerät kennt diesen Befehl nicht (Firmware zu alt?).",
    ERR_BAD_ARGS: "Das Gerät hat die Eingabe abgelehnt (falsches Format, falsche Anzahl "
                  "Argumente oder Zeile zu lang).",
    ERR_OUT_OF_RANGE: "Wert außerhalb des erlaubten Bereichs oder unbekannte Einstellung.",
    ERR_SENSOR: "Sensor nicht verfügbar – der BME680 wurde nicht gefunden "
                "(Verkabelung SDA/SCL und Stromversorgung prüfen).",
    ERR_WRONG_STATE: "Im aktuellen Zustand nicht möglich (z. B. kein unquittierter Alarm).",
}


def error_text_de(code: int) -> str:
    """German message for an ``ERR`` code (fallback for codes not in the SPEC)."""
    return ERROR_TEXTS_DE.get(code, f"Unbekannter Fehler vom Gerät (Code {code}).")


class ProtocolError(Exception):
    """Malformed line from the device, or an unexpected response shape."""


class DeviceError(Exception):
    """Device answered ``ERR <code> <text>``. ``str()`` is the German message."""

    def __init__(self, code: int, text: str = ""):
        self.code = code
        self.text = text
        self.message_de = error_text_de(code)
        super().__init__(f"{self.message_de} (ERR {code})")


# --------------------------------------------------------------------------- measurements

T_SCALE = 100    # 0.01 °C
RH_SCALE = 100   # 0.01 %rF
P_SCALE = 10     # 0.1 hPa

# Plausibility ranges (SPEC); outside -> invalid
T_RANGE = (-4000, 8500)
RH_RANGE = (0, 10000)
P_RANGE = (3000, 11000)
GAS_RANGE = (1, 0xFFFFFFFF)

INVALID = "-"


@dataclass(frozen=True)
class Measurement:
    """One measurement as scaled integers from the wire; ``None`` = invalid/missing."""

    t: int | None = None      # 0.01 °C
    rh: int | None = None     # 0.01 %rF
    p: int | None = None      # 0.1 hPa
    gas: int | None = None    # Ω
    age_sec: int | None = None  # only from READ

    # physical units (for charts / calculations; formatting uses the exact integers)
    @property
    def temperature_c(self) -> float | None:
        return None if self.t is None else self.t / T_SCALE

    @property
    def humidity_pct(self) -> float | None:
        return None if self.rh is None else self.rh / RH_SCALE

    @property
    def pressure_hpa(self) -> float | None:
        return None if self.p is None else self.p / P_SCALE

    @property
    def gas_ohm(self) -> int | None:
        return self.gas

    @property
    def gas_kohm(self) -> float | None:
        return None if self.gas is None else self.gas / 1000

    @property
    def any_valid(self) -> bool:
        return any(v is not None for v in (self.t, self.rh, self.p, self.gas))

    def csv_fields(self) -> tuple[str, str, str, str]:
        """Numbers for the CSV log: physical units, decimal comma, invalid -> ``""``."""
        return (
            "" if self.t is None else format_scaled(self.t, 2),
            "" if self.rh is None else format_scaled(self.rh, 2),
            "" if self.p is None else format_scaled(self.p, 1),
            "" if self.gas is None else str(self.gas),
        )


def format_scaled(raw: int, decimals: int) -> str:
    """Exact integer -> decimal string with comma: ``format_scaled(-5, 2) == "-0,05"``."""
    if decimals <= 0:
        return str(raw)
    sign = "-" if raw < 0 else ""
    a = abs(int(raw))
    div = 10 ** decimals
    return f"{sign}{a // div},{a % div:0{decimals}d}"


def format_temperature(raw: int | None) -> str:
    return "--" if raw is None else f"{format_scaled(raw, 2)} °C"


def format_humidity(raw: int | None) -> str:
    return "--" if raw is None else f"{format_scaled(raw, 2)} % rF"


def format_pressure(raw: int | None) -> str:
    return "--" if raw is None else f"{format_scaled(raw, 1)} hPa"


def format_gas(raw: int | None, *, kilo: bool = True) -> str:
    """Gas resistance; ``kilo`` -> ``"85,0 kΩ"`` (rounded to 0.1 kΩ), else ``"85000 Ω"``."""
    if raw is None:
        return "--"
    if not kilo:
        return f"{raw} Ω"
    return f"{format_scaled((raw + 50) // 100, 1)} kΩ"


def format_uptime(sec: int | None) -> str:
    if sec is None:
        return "--"
    sec = max(0, int(sec))
    d, rest = divmod(sec, 86400)
    h, rest = divmod(rest, 3600)
    m, s = divmod(rest, 60)
    hms = f"{h:02d}:{m:02d}:{s:02d}"
    return f"{d} d {hms}" if d else hms


def _int(tok: str, line: str) -> int:
    if not re.fullmatch(r"-?\d+", tok):
        raise ProtocolError(f"Zahl erwartet, erhalten {tok!r} in {line!r}")
    return int(tok)


def _value(tok: str, rng: tuple[int, int], name: str, line: str) -> int | None:
    """``-`` -> None; integer in the plausibility range -> int; outside -> None (logged).

    A token that is neither ``-`` nor an integer is garbage -> ProtocolError.
    """
    if tok == INVALID:
        return None
    v = _int(tok, line)
    if not rng[0] <= v <= rng[1]:
        log.warning("Unplausibler Wert %s=%s verworfen (%r)", name, v, line)
        return None
    return v


def parse_values(tokens: list[str] | tuple[str, ...], line: str = "") -> Measurement:
    """``<t> <rh> <p> <gas>`` (four tokens) -> Measurement."""
    if len(tokens) != 4:
        raise ProtocolError(f"Vier Messwerte erwartet: {line!r}")
    t, rh, p, gas = tokens
    return Measurement(
        t=_value(t, T_RANGE, "t", line),
        rh=_value(rh, RH_RANGE, "rh", line),
        p=_value(p, P_RANGE, "p", line),
        gas=_value(gas, GAS_RANGE, "gas", line),
    )


def parse_read(args: tuple[str, ...]) -> Measurement:
    """``OK <t> <rh> <p> <gas> <ageSec>`` -> Measurement (with ``age_sec``)."""
    line = "OK " + " ".join(args)
    if len(args) != 5:
        raise ProtocolError(f"Unerwartete READ-Antwort: {line!r}")
    m = parse_values(args[:4], line)
    age = None if args[4] == INVALID else _int(args[4], line)
    if age is not None and age < 0:
        raise ProtocolError(f"Negatives Alter in {line!r}")
    return Measurement(m.t, m.rh, m.p, m.gas, age)


# --------------------------------------------------------------------------- status & alarms

SENSOR_OK = "OK"
SENSOR_MISSING = "MISSING"
SENSOR_ERROR = "ERROR"
SENSOR_STATES = (SENSOR_OK, SENSOR_MISSING, SENSOR_ERROR)
SENSOR_TEXT_DE = {
    SENSOR_OK: "Sensor OK",
    SENSOR_MISSING: "Sensor nicht erreichbar",
    SENSOR_ERROR: "Messfehler am Sensor",
}

ALARM_T_HI = 1
ALARM_T_LO = 2
ALARM_RH_HI = 4
ALARM_RH_LO = 8
ALARM_SENSOR = 16
ALARM_FLAGS = (ALARM_T_HI, ALARM_T_LO, ALARM_RH_HI, ALARM_RH_LO, ALARM_SENSOR)
ALARM_ALL = sum(ALARM_FLAGS)
ALARM_TEXT_DE = {
    ALARM_T_HI: "Temperatur zu hoch",
    ALARM_T_LO: "Temperatur zu niedrig",
    ALARM_RH_HI: "Luftfeuchte zu hoch",
    ALARM_RH_LO: "Luftfeuchte zu niedrig",
    ALARM_SENSOR: "keine Messdaten (Sensor fehlt oder Messfehler)",
}


def alarm_texts(flags: int) -> list[str]:
    """German texts of all set alarm bits (in flag order)."""
    return [ALARM_TEXT_DE[f] for f in ALARM_FLAGS if flags & f]


@dataclass(frozen=True)
class DeviceStatus:
    """``OK <sensor> <interval> <uptimeSec> <alarmFlags> <unackedFlags>``."""

    sensor: str
    interval: int
    uptime_sec: int
    alarm_flags: int = 0
    unacked_flags: int = 0

    @property
    def sensor_text(self) -> str:
        return SENSOR_TEXT_DE.get(self.sensor, self.sensor)

    @property
    def alarm_active(self) -> bool:
        return self.alarm_flags != 0

    @property
    def needs_ack(self) -> bool:
        return self.unacked_flags != 0


def parse_status(args: tuple[str, ...]) -> DeviceStatus:
    line = "OK " + " ".join(args)
    if len(args) != 5:
        raise ProtocolError(f"Unerwartete STATUS-Antwort: {line!r}")
    sensor = args[0].upper()
    if sensor not in SENSOR_STATES:
        raise ProtocolError(f"Unbekannter Sensorzustand {args[0]!r} in {line!r}")
    nums = [_int(a, line) for a in args[1:]]
    if nums[0] < 1 or nums[1] < 0 or not all(0 <= f <= ALARM_ALL for f in nums[2:]):
        raise ProtocolError(f"Unplausible STATUS-Antwort: {line!r}")
    return DeviceStatus(sensor, nums[0], nums[1], nums[2], nums[3])


# --------------------------------------------------------------------------- configuration


@dataclass(frozen=True)
class ConfigKey:
    name: str
    label_de: str
    kind: str          # "sec", "temp", "rh", "bool"
    lo: int
    hi: int
    off_allowed: bool = False
    default: int | None = None


CONFIG_KEYS: dict[str, ConfigKey] = {k.name: k for k in (
    ConfigKey("INTERVAL", "Messintervall", "sec", 1, 3600, default=10),
    ConfigKey("TEMP_OFFSET", "Temperatur-Offset", "temp", -5000, 5000, default=0),
    ConfigKey("T_HI", "Temperatur oberer Schwellwert", "temp", -4000, 8500, True),
    ConfigKey("T_LO", "Temperatur unterer Schwellwert", "temp", -4000, 8500, True),
    ConfigKey("RH_HI", "Feuchte oberer Schwellwert", "rh", 0, 10000, True),
    ConfigKey("RH_LO", "Feuchte unterer Schwellwert", "rh", 0, 10000, True),
    ConfigKey("BUZZER", "Piezo bei Alarm", "bool", 0, 1, default=0),
)}
CFG_OFF = "OFF"
_SCALE_OF_KIND = {"temp": 2, "rh": 2}
_UNIT_OF_KIND = {"sec": "s", "temp": "°C", "rh": "%"}


def config_key(name: str) -> ConfigKey:
    key = CONFIG_KEYS.get(str(name).strip().upper())
    if key is None:
        raise ValueError(f"Unbekannte Einstellung {name!r}. Möglich: "
                         + ", ".join(CONFIG_KEYS))
    return key


def config_range_text(key: ConfigKey) -> str:
    if key.kind == "bool":
        return "0 (aus) oder 1 (an)"
    d = _SCALE_OF_KIND.get(key.kind, 0)
    unit = _UNIT_OF_KIND[key.kind]
    text = f"{format_scaled(key.lo, d)} … {format_scaled(key.hi, d)} {unit}"
    return text + (" oder OFF" if key.off_allowed else "")


def format_config_value(name: str, raw: int | None) -> str:
    """Human-readable German value: ``"28,50 °C"``, ``"aus"``, ``"10 s"``, ``"an"``."""
    key = CONFIG_KEYS.get(name.upper())
    if raw is None:
        return "aus"
    if key is None:
        return str(raw)
    if key.kind == "bool":
        return "an" if raw else "aus"
    d = _SCALE_OF_KIND.get(key.kind, 0)
    return f"{format_scaled(raw, d)} {_UNIT_OF_KIND[key.kind]}"


def config_input_text(name: str, raw: int | None) -> str:
    """Value as the user would type it (for editable fields): ``"28,5"``, ``"OFF"``."""
    key = config_key(name)
    if raw is None:
        return CFG_OFF
    if key.kind in ("sec", "bool"):
        return str(raw)
    text = format_scaled(raw, _SCALE_OF_KIND[key.kind])
    if "," in text:
        text = text.rstrip("0").rstrip(",")
    return text


_OFF_WORDS = ("OFF", "AUS", "-", "")
_ON_WORDS = {"1": 1, "AN": 1, "EIN": 1, "ON": 1, "0": 0, "AUS": 0, "OFF": 0}


def parse_config_input(name: str, text: str | int) -> str:
    """User input in physical units -> wire value for ``CFG <key> <value>``.

    Temperatures/humidity in °C/% with comma or point (``"28,5"`` -> ``"2850"``),
    ``OFF``/``aus`` for thresholds, seconds for INTERVAL, ``0/1/an/aus`` for BUZZER.
    Raises ValueError with a German message (nothing is sent then).
    """
    key = config_key(name)
    s = str(text).strip()
    if key.kind == "bool":
        v = _ON_WORDS.get(s.upper())
        if v is None:
            raise ValueError(f"{key.label_de}: bitte 0/1 bzw. an/aus angeben.")
        return str(v)
    if key.off_allowed and s.upper() in _OFF_WORDS:
        return CFG_OFF
    try:
        d = Decimal(s.replace(",", "."))
    except InvalidOperation:
        raise ValueError(f"{key.label_de}: {s!r} ist keine Zahl. Erlaubt: "
                         f"{config_range_text(key)}.") from None
    if not d.is_finite():
        raise ValueError(f"{key.label_de}: {s!r} ist keine Zahl.")
    scaled = d * (10 ** _SCALE_OF_KIND.get(key.kind, 0))
    if scaled != scaled.to_integral_value():
        places = _SCALE_OF_KIND.get(key.kind, 0)
        raise ValueError(f"{key.label_de}: höchstens {places} Nachkommastellen"
                         if places else f"{key.label_de}: nur ganze Sekunden")
    raw = int(scaled)
    if not key.lo <= raw <= key.hi:
        raise ValueError(f"{key.label_de}: {s} liegt außerhalb des erlaubten Bereichs "
                         f"({config_range_text(key)}).")
    return str(raw)


def parse_config_line(line: str) -> tuple[str, int | None]:
    """``C <key> <value>`` -> (KEY, int or None for OFF)."""
    t = line.split()
    if len(t) != 3 or t[0].upper() != "C":
        raise ProtocolError(f"Unerwartete Zeile (erwartet C <key> <value>): {line!r}")
    value = None if t[2].upper() == CFG_OFF else _int(t[2], line)
    return t[1].upper(), value


def parse_config(lines: tuple[str, ...] | list[str]) -> dict[str, int | None]:
    out: dict[str, int | None] = {}
    for line in lines:
        k, v = parse_config_line(line)
        if k not in CONFIG_KEYS:
            log.info("Unbekannte Einstellung ignoriert: %s", line)
            continue
        out[k] = v
    return out


# --------------------------------------------------------------------------- events

EVT_BOOT = "BOOT"
EVT_DATA = "DATA"
EVT_ALARM = "ALARM"
EVT_SENSOR = "SENSOR"
KNOWN_EVENTS = (EVT_BOOT, EVT_DATA, EVT_ALARM, EVT_SENSOR)


@dataclass(frozen=True)
class Event:
    """Asynchronous ``EVT`` line; unused fields stay ``None``."""

    kind: str
    measurement: Measurement | None = None
    flag: int | None = None
    active: bool | None = None
    sensor: str | None = None
    fw_version: str | None = None
    raw: str = field(default="", compare=False)


def parse_event(line: str) -> Event:
    """Parse an ``EVT`` line. Malformed known events raise ProtocolError (caller skips)."""
    tokens = line.split()
    if not tokens or tokens[0].upper() != "EVT":
        raise ProtocolError(f"Keine EVT-Zeile: {line!r}")
    if len(tokens) < 2:
        raise ProtocolError(f"EVT ohne Typ: {line!r}")
    kind = tokens[1].upper()
    args = tokens[2:]
    if kind == EVT_DATA:
        return Event(kind, measurement=parse_values(args, line), raw=line)
    if kind == EVT_ALARM:
        if len(args) != 2 or args[1] not in ("0", "1"):
            raise ProtocolError(f"EVT ALARM erwartet <flag> <0|1>: {line!r}")
        flag = _int(args[0], line)
        if flag not in ALARM_FLAGS:
            raise ProtocolError(f"Unbekanntes Alarm-Flag in {line!r}")
        return Event(kind, flag=flag, active=args[1] == "1", raw=line)
    if kind == EVT_SENSOR:
        if len(args) != 1 or args[0].upper() not in SENSOR_STATES:
            raise ProtocolError(f"EVT SENSOR erwartet OK|MISSING|ERROR: {line!r}")
        return Event(kind, sensor=args[0].upper(), raw=line)
    if kind == EVT_BOOT:
        return Event(kind, fw_version=" ".join(args), raw=line)
    return Event(kind, raw=line)  # unknown kinds: passed through, ignored by the device layer


# --------------------------------------------------------------------------- PING / TIME / version


def parse_pong(args: tuple[str, ...]) -> str:
    """``OK PONG Umgebungssensoren <fw>`` -> fw. Another product -> ProtocolError."""
    if len(args) < 2 or args[0].upper() != "PONG":
        raise ProtocolError(f"Unerwartete PING-Antwort: OK {' '.join(args)}")
    if args[1] != PRODUCT:
        raise ProtocolError(f"Das Gerät meldet sich als „{args[1]}“, nicht als {PRODUCT} – "
                            "falscher Port?")
    return args[2] if len(args) >= 3 else ""


def version_older(version: str | None, minimum: str) -> bool:
    """True if dotted ``version`` is older than ``minimum``; unparsable -> False."""

    def parts(v: str) -> tuple[int, ...]:
        return tuple(int(x) for x in re.findall(r"\d+", v))

    if not version:
        return False
    a, b = parts(version), parts(minimum)
    return bool(a) and a < b


def format_clock(t: _dt.time) -> str:
    return f"{t.hour:02d}:{t.minute:02d}:{t.second:02d}"


_CLOCK_RE = re.compile(r"^(\d{2}):(\d{2}):(\d{2})$")
CLOCK_UNSET = "--:--:--"


def parse_clock(text: str) -> _dt.time | None:
    """``hh:mm:ss`` -> time; ``--:--:--`` (not set) -> None."""
    text = text.strip()
    if text == CLOCK_UNSET:
        return None
    m = _CLOCK_RE.match(text)
    if not m:
        raise ProtocolError(f"Ungültige Uhrzeit {text!r}")
    h, mi, se = (int(x) for x in m.groups())
    if h > 23 or mi > 59 or se > 59:
        raise ProtocolError(f"Ungültige Uhrzeit {text!r}")
    return _dt.time(h, mi, se)


def parse_time_reply(args: tuple[str, ...]) -> _dt.time | None:
    if len(args) != 1:
        raise ProtocolError(f"Unerwartete TIME-Antwort: OK {' '.join(args)}")
    return parse_clock(args[0])


def clock_difference_sec(device: _dt.time, pc: _dt.time) -> int:
    """device - pc in seconds, wrapped to -12 h .. +12 h (midnight-safe)."""

    def secs(t: _dt.time) -> int:
        return t.hour * 3600 + t.minute * 60 + t.second

    d = (secs(device) - secs(pc)) % 86400
    return d - 86400 if d > 43200 else d


# --------------------------------------------------------------------------- command builders


@dataclass(frozen=True)
class Reply:
    """Successful response: tokens after ``OK`` and (for lists) body lines before ``END``."""

    args: tuple[str, ...] = ()
    lines: tuple[str, ...] = ()


def encode_line(line: str) -> bytes:
    return (line + "\n").encode(ENCODING)


def _cmd(*parts: object) -> str:
    line = " ".join(str(x) for x in parts)
    try:
        size = len(encode_line(line)) - 1
    except UnicodeEncodeError:
        raise ValueError("Befehl enthält Nicht-ASCII-Zeichen") from None
    if size > MAX_LINE_LEN:
        raise ValueError(f"Befehl zu lang ({size} > {MAX_LINE_LEN} Bytes)")
    return line


def cmd_ping() -> str:
    return _cmd("PING")


def cmd_status() -> str:
    return _cmd("STATUS")


def cmd_read() -> str:
    return _cmd("READ")


def cmd_cfg_list() -> str:
    return _cmd("CFG")


def cmd_cfg_set(name: str, wire_value: str) -> str:
    """``CFG <key> <value>``; ``wire_value`` from :func:`parse_config_input`."""
    key = config_key(name)
    v = str(wire_value).strip().upper()
    if v == CFG_OFF:
        if not key.off_allowed:
            raise ValueError(f"{key.label_de}: OFF ist hier nicht erlaubt")
    else:
        if not re.fullmatch(r"-?\d+", v) or not key.lo <= int(v) <= key.hi:
            raise ValueError(f"{key.label_de}: ungültiger Wert {wire_value!r} "
                             f"(Rohwert {key.lo}…{key.hi})")
        v = str(int(v))
    return _cmd("CFG", key.name, v)


def cmd_cfg_reset() -> str:
    return _cmd("CFG", "RESET")


def cmd_stream(on: bool) -> str:
    return _cmd("STREAM", 1 if on else 0)


def cmd_ack() -> str:
    return _cmd("ACK")


def cmd_time_get() -> str:
    return _cmd("TIME")


def cmd_time_set(t: _dt.time | _dt.datetime) -> str:
    return _cmd("TIME", format_clock(t if isinstance(t, _dt.time) else t.time()))


# --------------------------------------------------------------------------- line classification


def clean_line(raw: str | bytes) -> str:
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    return raw.replace("\r", "").strip()


def _head(line: str) -> str:
    return line.split(None, 1)[0].upper() if line.strip() else ""


def is_event_line(line: str) -> bool:
    return _head(line) == "EVT"


def is_ok_line(line: str) -> bool:
    return _head(line) == "OK"


def is_err_line(line: str) -> bool:
    return _head(line) == "ERR"


def is_end_line(line: str) -> bool:
    return line.strip().upper() == "END"


def parse_ok_args(line: str) -> tuple[str, ...]:
    tokens = line.split()
    if not tokens or tokens[0].upper() != "OK":
        raise ProtocolError(f"Keine OK-Zeile: {line!r}")
    return tuple(tokens[1:])


def parse_err(line: str) -> DeviceError:
    """``ERR <code> <text>`` -> DeviceError (not raised). Missing code -> -1."""
    tokens = line.split(None, 2)
    if not tokens or tokens[0].upper() != "ERR":
        raise ProtocolError(f"Keine ERR-Zeile: {line!r}")
    code, text = -1, ""
    if len(tokens) >= 2:
        try:
            code = int(tokens[1])
        except ValueError:
            text = " ".join(tokens[1:])
        else:
            text = tokens[2] if len(tokens) > 2 else ""
    return DeviceError(code, text)
