"""Logging: stderr plus a rotating file in the user log directory (no Qt)."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from umwelt_panel.config import LOG_FILENAME, log_dir

_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"


def setup_logging(level: int = logging.INFO) -> None:
    root = logging.getLogger()
    if root.handlers:
        return
    root.setLevel(level)
    stream = logging.StreamHandler()
    stream.setFormatter(logging.Formatter(_FORMAT))
    root.addHandler(stream)
    # A missing log file is a nuisance, not a reason to keep the panel from starting.
    try:
        directory = log_dir()
        directory.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(directory / LOG_FILENAME, maxBytes=1_000_000,
                                      backupCount=3, encoding="utf-8")
    except OSError:
        logging.getLogger(__name__).warning("Log-Ordner nicht beschreibbar – nur stderr",
                                            exc_info=True)
        return
    handler.setFormatter(logging.Formatter(_FORMAT))
    root.addHandler(handler)
