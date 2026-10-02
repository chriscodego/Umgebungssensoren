"""All SQL of the Control Panel. Repositories take a connection; they never open one."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator

Row = tuple[int, int | None, int | None, int | None, int | None, int | None]
BucketRow = tuple[int, float | None, float | None, float | None, float | None]


class MeasurementRepository:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def insert(self, ts_ms: int, t: int | None, rh: int | None, p: int | None,
               gas: int | None, alarm: int | None) -> None:
        self._conn.execute(
            "INSERT INTO measurements (ts_utc, t, rh, p, gas, alarm) VALUES (?, ?, ?, ?, ?, ?)",
            (ts_ms, t, rh, p, gas, alarm))

    @staticmethod
    def _where(start_ms: int | None, end_ms: int | None) -> tuple[str, list[int]]:
        parts, args = [], []
        if start_ms is not None:
            parts.append("ts_utc >= ?")
            args.append(start_ms)
        if end_ms is not None:
            parts.append("ts_utc <= ?")
            args.append(end_ms)
        return (" WHERE " + " AND ".join(parts)) if parts else "", args

    def count(self, start_ms: int | None = None, end_ms: int | None = None) -> int:
        where, args = self._where(start_ms, end_ms)
        return int(self._conn.execute(f"SELECT COUNT(*) FROM measurements{where}",
                                      args).fetchone()[0])

    def first_last(self, start_ms: int | None = None, end_ms: int | None = None
                   ) -> tuple[int | None, int | None]:
        where, args = self._where(start_ms, end_ms)
        row = self._conn.execute(f"SELECT MIN(ts_utc), MAX(ts_utc) FROM measurements{where}",
                                 args).fetchone()
        return row[0], row[1]

    def rows(self, start_ms: int | None = None, end_ms: int | None = None,
             batch: int = 1000) -> Iterator[Row]:
        """All rows of the period in time order, fetched in batches (export)."""
        where, args = self._where(start_ms, end_ms)
        cur = self._conn.execute(
            f"SELECT ts_utc, t, rh, p, gas, alarm FROM measurements{where} ORDER BY ts_utc, id",
            args)
        while True:
            chunk = cur.fetchmany(batch)
            if not chunk:
                return
            yield from chunk

    def buckets(self, start_ms: int, end_ms: int, bucket_ms: int) -> list[BucketRow]:
        """Averages per time bucket (chart). ``AVG`` skips NULL, an all-invalid bucket is NULL."""
        bucket_ms = max(1, int(bucket_ms))
        return [tuple(r) for r in self._conn.execute(
            "SELECT CAST(AVG(ts_utc) AS INTEGER), AVG(t), AVG(rh), AVG(p), AVG(gas)"
            " FROM measurements WHERE ts_utc >= ? AND ts_utc <= ?"
            " GROUP BY (ts_utc - ?) / ? ORDER BY 1",
            (start_ms, end_ms, start_ms, bucket_ms))]

    def delete_all(self) -> int:
        return self._conn.execute("DELETE FROM measurements").rowcount


class SettingsRepository:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def get(self, key: str) -> str | None:
        row = self._conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return None if row is None else str(row[0])

    def set(self, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?)"
            " ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))

    def delete(self, key: str) -> None:
        self._conn.execute("DELETE FROM settings WHERE key = ?", (key,))
