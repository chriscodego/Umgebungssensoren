"""Run a service call in ``QThreadPool`` and get the result back in the GUI thread.

Database queries over long periods and the CSV export can take longer than ~100 ms; they
never run on the GUI thread. ``on_ok``/``on_err`` are called in the GUI thread: the relay
object lives there, so its slots are reached through a queued connection.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

log = logging.getLogger(__name__)

_running: set[_Relay] = set()  # keeps relays alive until delivery


class _Relay(QObject):
    finished = Signal(object)
    failed = Signal(object)

    def __init__(self, on_ok: Callable[[Any], None],
                 on_err: Callable[[BaseException], None]) -> None:
        super().__init__()
        self._on_ok = on_ok
        self._on_err = on_err
        self.finished.connect(self._ok)
        self.failed.connect(self._err)

    @Slot(object)
    def _ok(self, result: Any) -> None:
        _running.discard(self)
        self._on_ok(result)

    @Slot(object)
    def _err(self, exc: Any) -> None:
        _running.discard(self)
        self._on_err(exc)


class _Task(QRunnable):
    def __init__(self, fn: Callable[[], Any], relay: _Relay) -> None:
        super().__init__()
        self._fn = fn
        self._relay = relay

    def run(self) -> None:
        try:
            result = self._fn()
        except Exception as exc:  # delivered to the caller, shown as German message
            self._relay.failed.emit(exc)
        else:
            self._relay.finished.emit(result)


def run_in_pool(fn: Callable[[], Any], on_ok: Callable[[Any], None],
                on_err: Callable[[BaseException], None]) -> None:
    """Call from the GUI thread."""
    relay = _Relay(on_ok, on_err)
    _running.add(relay)
    QThreadPool.globalInstance().start(_Task(fn, relay))


def pending() -> int:
    return len(_running)


def wait_for_pool(msecs: int = 5000) -> bool:
    """Block until all pool jobs are done (window closing)."""
    return QThreadPool.globalInstance().waitForDone(msecs)
