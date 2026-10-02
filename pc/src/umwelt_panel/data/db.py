"""SQLite file, schema version and migrations (stdlib ``sqlite3``, no Qt).

Schema version lives in ``PRAGMA user_version``. :data:`MIGRATIONS` is an ordered list of
``(version, statements)``; :meth:`Database.open` applies every step newer than the file in
one ``BEGIN IMMEDIATE`` transaction each, so two panels starting together cannot apply a
step twice. A file newer than this program is refused (never downgraded or touched).

Every call opens its own short connection (:meth:`Database.connect`): the serial worker
thread, the thread pool and the GUI thread never share a connection, and WAL mode lets a
reader run while a measurement is being written. Low-level ``sqlite3`` errors leave this
module only as :class:`~umwelt_panel.core.errors.DatabaseError` with a German message.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path

from umwelt_panel.core.errors import (
    DatabaseCorruptError,
    DatabaseError,
    DatabaseNewerError,
    DatabaseUnavailableError,
)

log = logging.getLogger(__name__)

BUSY_TIMEOUT_S = 5.0

Migration = tuple[int, Sequence[str]]

#: Schema history. Never edit a released step — append a new one.
MIGRATIONS: tuple[Migration, ...] = (
    (1, (
        # ts_utc: PC time, Unix milliseconds (UTC). Values are the scaled wire integers
        # from docs/SPEC.md (t 0.01 °C, rh 0.01 %rF, p 0.1 hPa, gas Ω); NULL = invalid.
        "CREATE TABLE measurements ("
        " id INTEGER PRIMARY KEY,"
        " ts_utc INTEGER NOT NULL,"
        " t INTEGER, rh INTEGER, p INTEGER, gas INTEGER,"
        " alarm INTEGER)",
        "CREATE INDEX idx_measurements_ts ON measurements (ts_utc)",
        "CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)",
    )),
)

_CORRUPT_MARKERS = ("file is not a database", "malformed", "file is encrypted")


class Database:
    """The measurement database file. Cheap to create; :meth:`open` migrates it."""

    def __init__(self, path: str | os.PathLike[str],
                 migrations: Sequence[Migration] = MIGRATIONS):
        self.path = Path(path)
        self._migrations = tuple(sorted(migrations, key=lambda m: m[0]))

    @property
    def schema_version(self) -> int:
        return self._migrations[-1][0] if self._migrations else 0

    # ------------------------------------------------------------------ connections

    def _raw_connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=BUSY_TIMEOUT_S, isolation_level=None)
        conn.execute(f"PRAGMA busy_timeout={int(BUSY_TIMEOUT_S * 1000)}")
        return conn

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        """One short transaction: commit on success, roll back on error, always close."""
        try:
            conn = self._raw_connect()
        except sqlite3.Error as exc:
            raise self._translate(exc) from exc
        try:
            conn.execute("BEGIN")
            yield conn
            conn.execute("COMMIT")
        except sqlite3.Error as exc:
            _rollback(conn)
            log.warning("Datenbankfehler: %s", exc)
            raise self._translate(exc) from exc
        except BaseException:
            _rollback(conn)
            raise
        finally:
            conn.close()

    def _translate(self, exc: BaseException) -> DatabaseError:
        text = str(exc).lower()
        if any(m in text for m in _CORRUPT_MARKERS):
            return DatabaseCorruptError(self.path)
        if "locked" in text:
            return DatabaseUnavailableError(self.path, "Datei gesperrt")
        if "readonly" in text or "unable to open" in text:
            return DatabaseUnavailableError(self.path, "kein Schreibzugriff")
        return DatabaseError(
            "Die Messwert-Datenbank konnte gerade nicht gelesen oder beschrieben werden "
            f"({exc}). Bitte den Vorgang wiederholen; bleibt der Fehler, das Control Panel "
            "neu starten.")

    # ------------------------------------------------------------------ startup

    def open(self) -> int:
        """Create the folder/file if needed and migrate to :attr:`schema_version`.

        Returns the version the file had before (0 = new). Raises DatabaseError.
        """
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise DatabaseUnavailableError(self.path, "Ordner nicht anlegbar") from exc
        try:
            conn = self._raw_connect()
        except sqlite3.Error as exc:
            raise self._translate(exc) from exc
        try:
            before = self._version(conn)
            if before > self.schema_version:
                raise DatabaseNewerError(self.path, before, self.schema_version)
            self._enable_wal(conn)
            for version, statements in self._migrations:
                if version > before:
                    self._apply(conn, version, statements)
            log.info("Messwert-Datenbank %s (Schema %d, vorher %d)", self.path,
                     self.schema_version, before)
            return before
        except sqlite3.Error as exc:
            raise self._translate(exc) from exc
        finally:
            conn.close()

    @staticmethod
    def _version(conn: sqlite3.Connection) -> int:
        return int(conn.execute("PRAGMA user_version").fetchone()[0])

    @staticmethod
    def _enable_wal(conn: sqlite3.Connection) -> None:
        # WAL lets the history view read while the worker writes. Not a correctness need:
        # if the switch fails (e.g. a network drive), the default journal is fine.
        try:
            mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            if str(mode).lower() != "wal":
                conn.execute("PRAGMA journal_mode=WAL")
        except sqlite3.Error:
            log.debug("WAL-Modus nicht aktivierbar", exc_info=True)

    def _apply(self, conn: sqlite3.Connection, version: int, statements: Sequence[str]) -> None:
        conn.execute("BEGIN IMMEDIATE")
        try:
            if self._version(conn) >= version:  # another instance was faster
                conn.execute("ROLLBACK")
                return
            for sql in statements:
                conn.execute(sql)
            conn.execute(f"PRAGMA user_version={int(version)}")
            conn.execute("COMMIT")
            log.info("Datenbank-Migration auf Schema %d angewandt", version)
        except BaseException:
            _rollback(conn)
            raise

    # ------------------------------------------------------------------ file info

    def size_bytes(self) -> int:
        """File size on disk including the WAL file."""
        total = 0
        for suffix in ("", "-wal"):
            try:
                total += os.path.getsize(f"{self.path}{suffix}")
            except OSError:
                pass
        return total


def _rollback(conn: sqlite3.Connection) -> None:
    try:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
    except sqlite3.Error:  # pragma: no cover - best effort
        pass
