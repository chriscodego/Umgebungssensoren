"""Umgebungssensoren Control Panel (PySide6): live values, alarm, settings, SQLite log.

Layering (as in the sibling project "RFB Controll Panel"):

* ``core/`` and ``data/`` import no Qt and are testable without a ``QApplication``;
* ``ui/`` only talks to services from ``core/services``;
* the serial link reuses :mod:`umwelt_ctl.protocol` and :mod:`umwelt_ctl.device` — there is
  no second protocol parser in this package.
"""

APP_NAME = "Umgebungssensoren"
__version__ = "0.1.0"
