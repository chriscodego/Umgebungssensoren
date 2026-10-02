"""The permanent measurement log: record, query periods, statistics, clear, CSV export.

Timestamps are PC time, stored as UTC; the CSV export writes them as ISO 8601 with the
local offset. Values stay the exact scaled integers of the wire (docs/SPEC.md) until they
are formatted by :mod:`umwelt_ctl.protocol` — the only place for unit conversion. The CSV
format is the one of the measurement log (``umwelt_ctl.messlog``): ``;``, UTF-8 with BOM,
header row, decimal comma, invalid values empty (never 0).

Nothing is deleted automatically: :meth:`MeasurementLog.clear` is only called after the user
confirmed it.
"""

from __future__ import annotations

import datetime as _dt
import logging
import os
from collections.abc import Callable, Iterator
from pathlib import Path

from umwelt_ctl import messlog
from umwelt_ctl.protocol import Measurement
from umwelt_panel.core.errors import ExportError
from umwelt_panel.core.models import (
    LogStats,
    Sample,
    TimeRange,
    from_epoch_ms,
    to_epoch_ms,
    utc_now,
)
from umwelt_panel.data.db import Database
from umwelt_panel.data.repositories import MeasurementRepository

log = logging.getLogger(__name__)

#: Upper bound of points the chart gets for one period (bucket averages beyond that).
DEFAULT_MAX_POINTS = 720
EXPORT_BATCH = 2000


def _measurement(t: float | None, rh: float | None, p: float | None,
                 gas: float | None) -> Measurement:
    def r(v: float | None) -> int | None:
        return None if v is None else int(round(v))

    return Measurement(r(t), r(rh), r(p), r(gas))


class MeasurementLog:
    def __init__(self, db: Database, now: Callable[[], _dt.datetime] = utc_now):
        self.db = db
        self._now = now

    @property
    def path(self) -> Path:
        return self.db.path

    # ------------------------------------------------------------------ write

    def record(self, m: Measurement, alarm: int | None,
               ts: _dt.datetime | None = None) -> Sample:
        """Store one measurement (invalid values as NULL). Raises DatabaseError."""
        ts = ts or self._now()
        with self.db.connect() as conn:
            MeasurementRepository(conn).insert(to_epoch_ms(ts), m.t, m.rh, m.p, m.gas, alarm)
        return Sample(ts.astimezone(_dt.UTC), m, alarm)

    def clear(self) -> int:
        """Delete every logged measurement (only after the user confirmed). Returns count."""
        with self.db.connect() as conn:
            n = MeasurementRepository(conn).delete_all()
        log.info("Messwert-Log geleert (%d Zeilen)", n)
        return n

    # ------------------------------------------------------------------ read

    def _bounds(self, rng: TimeRange, now: _dt.datetime | None) -> tuple[int | None, int]:
        now = now or self._now()
        start = rng.start(now)
        return (None if start is None else to_epoch_ms(start)), to_epoch_ms(now)

    def count(self, rng: TimeRange = TimeRange.ALL, now: _dt.datetime | None = None) -> int:
        start, end = self._bounds(rng, now)
        with self.db.connect() as conn:
            return MeasurementRepository(conn).count(start, end)

    def samples(self, rng: TimeRange, now: _dt.datetime | None = None) -> list[Sample]:
        """Every row of the period, oldest first (small periods and tests)."""
        start, end = self._bounds(rng, now)
        with self.db.connect() as conn:
            return [_sample(row) for row in MeasurementRepository(conn).rows(start, end)]

    def series(self, rng: TimeRange, max_points: int = DEFAULT_MAX_POINTS,
               now: _dt.datetime | None = None) -> list[Sample]:
        """Chart data for the period: raw rows, or bucket averages above ``max_points``."""
        start, end = self._bounds(rng, now)
        with self.db.connect() as conn:
            repo = MeasurementRepository(conn)
            if start is None:
                first, last = repo.first_last()
                if first is None or last is None:
                    return []
                start, end = first, max(end, last)
            n = repo.count(start, end)
            if n <= max_points:
                return [_sample(row) for row in repo.rows(start, end)]
            # buckets over the span that actually holds data (best resolution)
            first, last = repo.first_last(start, end)
            lo, hi = first or start, last or end
            bucket = max(1, -(-(hi - lo + 1) // max(1, max_points)))
            return [Sample(from_epoch_ms(ts), _measurement(t, rh, p, gas), None)
                    for ts, t, rh, p, gas in repo.buckets(lo, hi, bucket)]

    def stats(self) -> LogStats:
        with self.db.connect() as conn:
            repo = MeasurementRepository(conn)
            count = repo.count()
            first, last = repo.first_last()
        return LogStats(
            path=self.db.path, count=count, size_bytes=self.db.size_bytes(),
            first_utc=None if first is None else from_epoch_ms(first),
            last_utc=None if last is None else from_epoch_ms(last))

    # ------------------------------------------------------------------ export

    def export_csv(self, rng: TimeRange, target: str | os.PathLike[str],
                   now: _dt.datetime | None = None) -> int:
        """Write the period as CSV (measurement-log format). Returns the number of rows.

        Written to ``<target>.tmp`` first and renamed at the end, so a failed export never
        leaves a half file under the chosen name. Raises ExportError / DatabaseError.
        """
        target = Path(target)
        tmp = target.with_name(target.name + ".tmp")
        start, end = self._bounds(rng, now)
        written = 0
        try:
            with open(tmp, "w", encoding="utf-8", newline="") as f:
                f.write(messlog.csv_text([], header=True))
                with self.db.connect() as conn:
                    for batch in _batches(MeasurementRepository(conn).rows(start, end)):
                        f.write(messlog.csv_text([_csv_row(s) for s in batch]))
                        written += len(batch)
            os.replace(tmp, target)
        except OSError as exc:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:  # pragma: no cover - best effort
                pass
            raise ExportError(
                f"Die Datei {target} konnte nicht geschrieben werden ({exc.strerror or exc}). "
                "Ist sie z. B. in Excel geöffnet oder der Ordner schreibgeschützt?") from exc
        except BaseException:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:  # pragma: no cover
                pass
            raise
        log.info("CSV-Export: %d Zeilen nach %s", written, target)
        return written


def _sample(row: tuple[int, int | None, int | None, int | None, int | None, int | None]
            ) -> Sample:
    ts, t, rh, p, gas, alarm = row
    return Sample(from_epoch_ms(ts), Measurement(t, rh, p, gas), alarm)


def _batches(rows: Iterator[tuple]) -> Iterator[list[Sample]]:
    batch: list[Sample] = []
    for row in rows:
        batch.append(_sample(row))
        if len(batch) >= EXPORT_BATCH:
            yield batch
            batch = []
    if batch:
        yield batch


def _csv_row(s: Sample) -> tuple[str, ...]:
    # UTC -> local time with offset, e.g. 2026-10-02T14:03:12+02:00
    return messlog.make_row(s.measurement, s.alarm, s.ts_utc.astimezone())
