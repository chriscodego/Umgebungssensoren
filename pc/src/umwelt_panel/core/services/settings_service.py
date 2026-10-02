"""Typed access to the panel's own settings (table ``settings``, plain text values).

Only this service knows the key names and encodings. Device settings (interval,
thresholds …) are NOT stored here — they live in the device EEPROM (``CFG``).
"""

from __future__ import annotations

import logging

from umwelt_panel.core.errors import DatabaseError
from umwelt_panel.core.models import TimeRange
from umwelt_panel.data.db import Database
from umwelt_panel.data.repositories import SettingsRepository

log = logging.getLogger(__name__)

KEY_AUTO_LOG = "log.auto"
KEY_PORT = "serial.port"
KEY_HISTORY_RANGE = "ui.history_range"
KEY_HISTORY_METRIC = "ui.history_metric"
KEY_GEOMETRY = "ui.main_window_geometry"

METRICS = ("t", "rh", "p", "gas")
_MAX_VALUE_LENGTH = 8192


class SettingsService:
    def __init__(self, db: Database):
        self._db = db

    def _get(self, key: str) -> str | None:
        try:
            with self._db.connect() as conn:
                return SettingsRepository(conn).get(key)
        except DatabaseError as exc:  # a setting is never worth a crash
            log.warning("Einstellung %s nicht lesbar: %s", key, exc)
            return None

    def _set(self, key: str, value: str | None) -> None:
        if value is not None and len(value) > _MAX_VALUE_LENGTH:
            raise ValueError("Wert zu lang")
        with self._db.connect() as conn:
            repo = SettingsRepository(conn)
            if value is None:
                repo.delete(key)
            else:
                repo.set(key, value)

    # -- logging -------------------------------------------------------------------

    def auto_log(self) -> bool:
        """Record measurements automatically while connected. On at first start."""
        return self._get(KEY_AUTO_LOG) != "0"

    def set_auto_log(self, enabled: bool) -> None:
        self._set(KEY_AUTO_LOG, "1" if enabled else "0")

    # -- serial port ---------------------------------------------------------------

    def port(self) -> str | None:
        """Last chosen port, ``None`` = automatic detection."""
        value = (self._get(KEY_PORT) or "").strip()
        return value or None

    def set_port(self, port: str | None) -> None:
        self._set(KEY_PORT, (port or "").strip() or None)

    # -- history view --------------------------------------------------------------

    def history_range(self) -> TimeRange:
        try:
            return TimeRange(self._get(KEY_HISTORY_RANGE) or TimeRange.DAY.value)
        except ValueError:
            return TimeRange.DAY

    def set_history_range(self, rng: TimeRange) -> None:
        self._set(KEY_HISTORY_RANGE, TimeRange(rng).value)

    def history_metric(self) -> str:
        value = self._get(KEY_HISTORY_METRIC)
        return value if value in METRICS else "t"

    def set_history_metric(self, metric: str) -> None:
        if metric not in METRICS:
            raise ValueError(f"Unbekannte Messgröße {metric!r}")
        self._set(KEY_HISTORY_METRIC, metric)

    # -- window --------------------------------------------------------------------

    def window_geometry(self) -> str | None:
        """Opaque Base64 Qt geometry, ``None`` at first start."""
        return self._get(KEY_GEOMETRY)

    def set_window_geometry(self, geometry: str | None) -> None:
        self._set(KEY_GEOMETRY, geometry)
