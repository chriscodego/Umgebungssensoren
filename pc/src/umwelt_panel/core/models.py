"""Plain data of the Control Panel (no Qt, no SQL)."""

from __future__ import annotations

import datetime as _dt
import enum
from dataclasses import dataclass
from pathlib import Path

from umwelt_ctl.protocol import Measurement

UTC = _dt.UTC


def utc_now() -> _dt.datetime:
    return _dt.datetime.now(UTC)


def to_epoch_ms(ts: _dt.datetime) -> int:
    """Aware (or naive local) datetime -> Unix time in milliseconds (UTC)."""
    if ts.tzinfo is None:
        ts = ts.astimezone()
    return int(round(ts.timestamp() * 1000))


def from_epoch_ms(ms: int) -> _dt.datetime:
    return _dt.datetime.fromtimestamp(ms / 1000, UTC)


@dataclass(frozen=True)
class Sample:
    """One logged measurement: PC time (UTC), the wire integers, the alarm bitmask."""

    ts_utc: _dt.datetime
    measurement: Measurement
    alarm: int | None = None  # SPEC bitmask; None = unknown


class TimeRange(enum.Enum):
    """Periods of the history view and the CSV export."""

    HOUR = "1h"
    DAY = "24h"
    WEEK = "7d"
    ALL = "all"

    @property
    def label_de(self) -> str:
        return {"1h": "letzte Stunde", "24h": "letzte 24 Stunden", "7d": "letzte 7 Tage",
                "all": "alles"}[self.value]

    @property
    def duration(self) -> _dt.timedelta | None:
        return {"1h": _dt.timedelta(hours=1), "24h": _dt.timedelta(days=1),
                "7d": _dt.timedelta(days=7)}.get(self.value)

    def start(self, now: _dt.datetime) -> _dt.datetime | None:
        """Inclusive start of the period (``None`` = from the first row)."""
        d = self.duration
        return None if d is None else now - d


@dataclass(frozen=True)
class LogStats:
    """What the user sees about the log: how much, since when, where, how big."""

    path: Path
    count: int
    size_bytes: int
    first_utc: _dt.datetime | None = None
    last_utc: _dt.datetime | None = None


def format_size(size: int) -> str:
    """``1536`` -> ``"1,5 KB"`` (decimal comma, binary units)."""
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            if unit == "B":
                return f"{int(value)} B"
            return f"{value:.1f} {unit}".replace(".", ",")
        value /= 1024
    return f"{size} B"  # pragma: no cover


def format_count(n: int) -> str:
    """``12345`` -> ``"12.345"`` (German thousands separator)."""
    return f"{n:,}".replace(",", ".")
