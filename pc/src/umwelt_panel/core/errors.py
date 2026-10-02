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


# --------------------------------------------------------------------------- updates (PROJ-9)

_LOG_HINT = ("Details stehen in der Logdatei (%LOCALAPPDATA%\\Umgebungssensoren\\Logs\\"
             "panel.log).")


class UpdateError(PanelError):
    """Base class for everything that can go wrong while looking for an update."""


class UpdateFolderUnreachableError(UpdateError):
    """No candidate for the update folder answered in time — no share, no VPN, no drive."""

    def __init__(self) -> None:
        super().__init__(
            "Das Update-Laufwerk ist nicht erreichbar.\n\n"
            "Gesucht wurde der Ordner „01_Interna\\05_Software\\Umgebungssensoren“ auf dem "
            "Institutslaufwerk und auf allen verbundenen Netzlaufwerken. Bitte prüfen Sie die "
            "Verbindung zum Institutsnetz (im Homeoffice: VPN) und versuchen Sie es erneut.")


class UpdateManifestMissingError(UpdateError):
    """The update folder is reachable but holds no ``latest.json`` yet."""

    def __init__(self) -> None:
        super().__init__(
            "Der Update-Ordner ist erreichbar, enthält aber keine Versionsdatei "
            "(latest.json). Es wurde dort noch keine Version bereitgestellt.\n\n"
            "Es wurde nichts kopiert.")


class UpdateManifestInvalidError(UpdateError):
    """``latest.json`` exists but is unreadable, too large, or not what it must be."""

    def __init__(self) -> None:
        super().__init__(
            "Die Versionsdatei (latest.json) im Update-Ordner ist ungültig und wurde "
            "nicht verwendet. Es wurde nichts kopiert.\n\n"
            f"Bitte melden Sie das der Person, die die Software betreut. {_LOG_HINT}")


class InstallerMissingError(UpdateError):
    """``latest.json`` names an installer that is not in the update folder."""

    def __init__(self, name: str) -> None:
        super().__init__(
            f"Die Versionsdatei nennt den Installer „{name}“, er liegt aber nicht im "
            "Update-Ordner. Es wurde nichts kopiert.\n\n"
            "Möglicherweise wird die Version gerade veröffentlicht — bitte versuchen "
            "Sie es in einigen Minuten erneut.")
        self.name = name


class CopyCancelledError(UpdateError):
    """The user pressed cancel while the installer was being copied."""

    def __init__(self) -> None:
        super().__init__("Das Kopieren des Installers wurde abgebrochen.")


class CopyFailedError(UpdateError):
    """The installer did not arrive completely; the partial copy was removed."""

    def __init__(self) -> None:
        super().__init__(
            "Der Installer konnte nicht vollständig vom Update-Laufwerk kopiert "
            "werden. Die unvollständige Kopie wurde entfernt und nicht gestartet.\n\n"
            f"Bitte versuchen Sie es erneut. {_LOG_HINT}")


class ChecksumMismatchError(UpdateError):
    """The copied installer does not match the SHA-256 in ``latest.json``."""

    def __init__(self) -> None:
        super().__init__(
            "Die Prüfsumme des kopierten Installers stimmt nicht mit der Versionsdatei "
            "überein. Die Kopie wurde gelöscht und NICHT gestartet.\n\n"
            "Möglicherweise wird gerade eine neue Version veröffentlicht — bitte "
            f"versuchen Sie es in einigen Minuten erneut. {_LOG_HINT}")


class TempDirectoryError(UpdateError):
    """The temporary directory cannot hold the installer."""

    def __init__(self, path: Path) -> None:
        super().__init__(
            f"In das temporäre Verzeichnis „{path}“ kann nicht geschrieben werden.\n\n"
            "Bitte geben Sie Speicherplatz frei oder prüfen Sie die Zugriffsrechte "
            "auf dieses Verzeichnis.")
        self.path = path
