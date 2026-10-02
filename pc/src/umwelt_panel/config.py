"""Per-user paths of the Control Panel (no Qt).

Everything writable lives in the user data directory (``platformdirs``), never in the
repository and never next to the program. On Windows that is
``%LOCALAPPDATA%\\Umgebungssensoren\\messwerte.db`` — local, not roaming/OneDrive.
"""

from __future__ import annotations

import os
from pathlib import Path

from umwelt_panel import APP_NAME

DB_FILENAME = "messwerte.db"
LOG_FILENAME = "panel.log"


def data_dir() -> Path:
    from platformdirs import user_data_path  # lazy: core tests do not need platformdirs

    return Path(user_data_path(APP_NAME, appauthor=False, roaming=False))


def log_dir() -> Path:
    from platformdirs import user_log_path

    return Path(user_log_path(APP_NAME, appauthor=False))


def database_path(explicit: str | os.PathLike[str] | None = None) -> Path:
    """``--db`` if given, else ``<user data dir>/messwerte.db``."""
    if explicit:
        return Path(explicit).expanduser().resolve()
    return data_dir() / DB_FILENAME
