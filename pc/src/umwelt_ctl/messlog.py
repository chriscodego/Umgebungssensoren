"""CSV measurement log (``monitor --csv`` and the GUI).

Format (docs/SPEC.md, "PC-Tool"): ``;``-separated, UTF-8 with BOM, header row
``zeit;temperatur_c;feuchte_proz;druck_hpa;gas_ohm;alarm``. ``zeit`` is the PC time in
ISO 8601 with the local offset; values in physical units with a decimal comma; invalid
values stay empty (never 0). ``alarm`` is the alarm bitmask from the SPEC (0 = none,
empty = unknown).

BOM and header are written only when the file is new or empty; otherwise rows are appended.
The file is opened per row (append, then closed), so every row is on disk immediately and a
file opened in Excel (Windows lock) does not lose rows: they wait in memory and are written
with the next successful row. Retention/deletion is the user's decision — nothing is ever
deleted here.
"""

from __future__ import annotations

import csv
import datetime as _dt
import io
import logging
import os
from collections.abc import Callable

from .protocol import Measurement

log = logging.getLogger(__name__)

HEADER = ("zeit", "temperatur_c", "feuchte_proz", "druck_hpa", "gas_ohm", "alarm")
DELIMITER = ";"
BOM = "﻿"
DEFAULT_FILENAME = "umwelt_messwerte.csv"


def default_log_path() -> str:
    """``~/umwelt_messwerte.csv`` — in the user's home, outside the repository."""
    return os.path.join(os.path.expanduser("~"), DEFAULT_FILENAME)


def timestamp(now: _dt.datetime | None = None) -> str:
    """PC time as ISO 8601 with local offset, e.g. ``2026-10-02T14:03:12+02:00``."""
    t = now or _dt.datetime.now()
    if t.tzinfo is None:
        t = t.astimezone()  # naive local time -> attach the local offset
    return t.isoformat(timespec="seconds")


def make_row(m: Measurement, alarm_flags: int | None,
             now: _dt.datetime | None = None) -> tuple[str, ...]:
    return (timestamp(now), *m.csv_fields(), "" if alarm_flags is None else str(alarm_flags))


def _format(rows: list[tuple[str, ...]]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=DELIMITER, lineterminator="\r\n")
    w.writerows(rows)
    return buf.getvalue()


class MessLogger:
    """Appends measurement rows to a CSV file; see the module docstring."""

    def __init__(self, path: str | os.PathLike[str],
                 now: Callable[[], _dt.datetime] = _dt.datetime.now):
        self.path = os.path.abspath(os.fspath(path))
        self._now = now
        self._pending: list[tuple[str, ...]] = []
        self.rows_written = 0
        parent = os.path.dirname(self.path)
        if parent and not os.path.isdir(parent):
            raise OSError(f"Ordner existiert nicht: {parent}")

    @property
    def pending(self) -> int:
        """Rows waiting because the file was locked."""
        return len(self._pending)

    def write(self, m: Measurement, alarm_flags: int | None = None) -> None:
        """Append one row (and any waiting rows). Raises OSError if the file is locked;
        the row is kept and written with the next successful call."""
        self._pending.append(make_row(m, alarm_flags, self._now()))
        self.flush()

    def flush(self) -> None:
        if not self._pending:
            return
        new = not os.path.exists(self.path) or os.path.getsize(self.path) == 0
        text = _format(self._pending)
        if new:
            text = BOM + _format([HEADER]) + text
        with open(self.path, "a", encoding="utf-8", newline="") as f:
            f.write(text)
            f.flush()
        self.rows_written += len(self._pending)
        self._pending.clear()

    def close(self) -> None:
        """Write waiting rows if possible (never raises)."""
        try:
            self.flush()
        except OSError as exc:
            log.warning("%d Messzeile(n) konnten nicht geschrieben werden: %s",
                        len(self._pending), exc)
