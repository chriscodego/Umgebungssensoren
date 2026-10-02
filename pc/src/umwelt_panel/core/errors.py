"""Domain errors of the Control Panel. ``str(exc)`` is a user-ready German message."""

from __future__ import annotations

from pathlib import Path


class PanelError(Exception):
    """Base class; the message says what happened and what the user can do."""


class DatabaseError(PanelError):
    """The measurement database could not be opened, read or written."""


class DatabaseNewerError(DatabaseError):
    def __init__(self, path: Path, found: int, supported: int):
        self.found = found
        self.supported = supported
        super().__init__(
            f"Die Messwert-Datenbank {path} stammt von einer neueren Version des Control Panels "
            f"(Schema {found}, diese Version kennt {supported}). Bitte das Control Panel "
            "aktualisieren oder mit --db eine andere Datei wählen.")


class DatabaseCorruptError(DatabaseError):
    def __init__(self, path: Path):
        super().__init__(
            f"Die Datei {path} ist keine gültige Messwert-Datenbank (beschädigt oder falsche "
            "Datei). Bitte die Datei umbenennen oder mit --db eine andere wählen.")


class DatabaseUnavailableError(DatabaseError):
    def __init__(self, path: Path, detail: str = ""):
        extra = f" ({detail})" if detail else ""
        super().__init__(
            f"Die Messwert-Datenbank {path} kann nicht geöffnet werden{extra}. Ist der Ordner "
            "beschreibbar und die Datei nicht von einem anderen Programm gesperrt?")


class ExportError(PanelError):
    """The CSV export could not be written."""
