"""Start of the Control Panel: ``python -m umwelt_panel`` / ``umwelt-panel``.

The only place where the database meets Qt at startup: a database problem is shown as a
German message box instead of a traceback.
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence
from types import TracebackType

from umwelt_panel import APP_NAME, __version__

log = logging.getLogger(__name__)

_UNEXPECTED = ("Es ist ein unerwarteter Fehler aufgetreten.\n\nDetails stehen in der Logdatei "
               "(Ordner „Logs“ im Datenordner von Umgebungssensoren).")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="umwelt-panel",
        description="Control Panel für die Umgebungssensoren-Anzeige: Live-Werte, Alarm, "
                    "Einstellungen und dauerhaftes Messwert-Log (SQLite).")
    ap.add_argument("--port", metavar="PORT",
                    help="serieller Port, z. B. COM9 (sonst Umgebungsvariable UMWELT_PORT "
                         "oder automatische Erkennung über USB-VID 0x2341)")
    ap.add_argument("--db", metavar="DATEI",
                    help="Messwert-Datenbank (Standard: messwerte.db im Datenordner des "
                         "Benutzers)")
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return ap


def _ensure_std_streams() -> None:
    """A windowed PyInstaller bundle has no console: ``sys.stdout``/``stderr`` are ``None``.

    argparse (``--help``/``--version``) and logging write there; send it to the null
    device instead of crashing. Nothing is written next to the executable.
    """
    import os

    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    _ensure_std_streams()
    args = build_parser().parse_args(argv)

    from PySide6.QtCore import QLocale
    from PySide6.QtWidgets import QApplication, QMessageBox

    from umwelt_panel.config import database_path
    from umwelt_panel.core.errors import DatabaseError
    from umwelt_panel.core.services.log_service import MeasurementLog
    from umwelt_panel.core.services.settings_service import SettingsService
    from umwelt_panel.data.db import Database
    from umwelt_panel.logging_setup import setup_logging
    from umwelt_panel.ui.device_controller import DeviceController
    from umwelt_panel.ui.main_window import MainWindow, load_stylesheet

    setup_logging()
    log.info("Starte %s Control Panel %s", APP_NAME, __version__)
    QLocale.setDefault(QLocale(QLocale.Language.German, QLocale.Country.Germany))
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setStyleSheet(load_stylesheet())

    def show_error(title: str, text: str) -> None:
        box = QMessageBox()
        box.setIcon(QMessageBox.Icon.Critical)
        box.setWindowTitle(title)
        box.setText(text)
        box.exec()

    def hook(exc_type: type[BaseException], exc: BaseException,
             tb: TracebackType | None) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc, tb)
            return
        log.critical("Unbehandelte Ausnahme", exc_info=(exc_type, exc, tb))
        show_error(APP_NAME, _UNEXPECTED)

    sys.excepthook = hook

    try:
        db = Database(database_path(args.db))
        db.open()
    except (DatabaseError, OSError) as exc:
        log.error("Start abgebrochen: %s", exc)
        show_error("Datenbank kann nicht geöffnet werden", str(exc))
        return 1
    log.info("Messwert-Datenbank: %s", db.path)

    log_service = MeasurementLog(db)
    settings = SettingsService(db)
    controller = DeviceController(log_service)
    window = MainWindow(controller, log_service, settings, port=args.port)
    window.show()
    window.start()
    window.schedule_update_check()
    return app.exec()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
