"""Drives the update flow: search → decision → copy → hand-over.

Everything that touches the share runs in the ``QThreadPool``; the GUI thread only
opens dialogs and reacts to signals. A dead network drive can block a file system call
for many seconds — the window must keep showing live values and alarms meanwhile.

Two ways in, one search at a time:

* :meth:`UpdateController.check_in_background` — the automatic check shortly after the
  start. It stays silent: a newer version is announced through :attr:`update_found`
  (the main window shows a non-modal hint), everything else only goes into the log.
* :meth:`UpdateController.check_for_updates` — the button and the menu entry. It always
  answers: newer version, already up to date, share not reachable, version file invalid.
  Clicking while the automatic check still runs starts no second search; the running
  one simply answers out loud when it finishes.

The controller owns no update logic of its own — it asks
:class:`~umwelt_panel.core.services.update_service.UpdateService` and turns the
answer into a dialog.
"""

from __future__ import annotations

import logging
import threading
from contextlib import suppress
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot
from PySide6.QtWidgets import QWidget

from umwelt_panel.core.errors import (
    CopyCancelledError,
    PanelError,
    UpdateError,
    UpdateFolderUnreachableError,
)
from umwelt_panel.core.services.update_service import (
    AvailableUpdate,
    UpdateCheckResult,
    UpdateService,
    default_copy_directory,
)
from umwelt_panel.ui import dialogs
from umwelt_panel.ui.update_dialogs import CopyProgressDialog, UpdateAvailableDialog

log = logging.getLogger(__name__)

_UNEXPECTED = (
    "Bei der Update-Suche ist ein unerwarteter Fehler aufgetreten. Details stehen in der Logdatei."
)

def default_download_directory() -> Path:
    """Where the installer copy lands. Replaceable in tests."""
    return default_copy_directory()


class _CheckSignals(QObject):
    finished = Signal(object)
    failed = Signal(object)


class _CheckTask(QRunnable):
    """One folder search, off the GUI thread."""

    def __init__(self, service: UpdateService) -> None:
        super().__init__()
        self._service = service
        self.signals = _CheckSignals()

    @Slot()
    def run(self) -> None:
        try:
            result = self._service.check_for_update()
        except PanelError as exc:
            self.signals.failed.emit(exc)
        except Exception:
            log.exception("The update check failed unexpectedly")
            self.signals.failed.emit(UpdateError(_UNEXPECTED))
        else:
            self.signals.finished.emit(result)


class _CopySignals(QObject):
    progress = Signal(int, int)
    finished = Signal(str)
    failed = Signal(object)


class _CopyTask(QRunnable):
    """The copy itself, off the GUI thread, cancellable at any chunk boundary."""

    def __init__(
        self,
        service: UpdateService,
        update: AvailableUpdate,
        directory: Path,
        cancel: threading.Event,
    ) -> None:
        super().__init__()
        self._service = service
        self._update = update
        self._directory = directory
        self._cancel = cancel
        self.signals = _CopySignals()

    @Slot()
    def run(self) -> None:
        try:
            path = self._service.copy_installer(
                self._update,
                self._directory,
                progress=self.signals.progress.emit,
                is_cancelled=self._cancel.is_set,
            )
        except PanelError as exc:
            self.signals.failed.emit(exc)
        except Exception:
            log.exception("The installer copy failed unexpectedly")
            self.signals.failed.emit(UpdateError(_UNEXPECTED))
        else:
            self.signals.finished.emit(str(path))


class UpdateController(QObject):
    """The state machine behind the update button, the menu entry and the startup check."""

    #: Emitted once the installer runs: the window has to close so Windows can replace
    #: the executable. The device keeps measuring and alarming on its own meanwhile.
    application_should_quit = Signal()

    #: A silent check found a newer version. Carries the :class:`AvailableUpdate`.
    update_found = Signal(object)

    #: Emitted when a copy really starts — the non-modal hint can go away then.
    copy_started = Signal()

    #: Test hook: raised whenever the controller comes back to rest.
    finished = Signal()

    def __init__(
        self,
        service: UpdateService,
        parent_widget: QWidget | None = None,
        pool: QThreadPool | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent if parent is not None else parent_widget)
        self._service = service
        self._widget = parent_widget
        self._pool = pool if pool is not None else QThreadPool.globalInstance()
        self._checking = False
        self._interactive = False
        self._copying = False
        self._cancel = threading.Event()
        self._progress: CopyProgressDialog | None = None

    @property
    def installed_version(self) -> str:
        return self._service.installed_version

    def is_busy(self) -> bool:
        return self._checking or self._copying

    def is_checking(self) -> bool:
        return self._checking

    # -- entry points ------------------------------------------------------------------

    @Slot()
    def check_for_updates(self) -> None:
        """The button and the menu entry. Always ends with an answer to the user."""
        if self._copying:
            log.info("An installer copy is running — the update search is ignored")
            return
        if self._checking:
            # No second search: the running one answers out loud when it finishes.
            log.info("An update check is already running — it will report its result")
            self._interactive = True
            return
        self._start_check(interactive=True)

    @Slot()
    def check_in_background(self) -> None:
        """The automatic check after the start. Silent unless something newer is there."""
        if self.is_busy():
            log.info("An update check is already running — the startup check is skipped")
            return
        self._start_check(interactive=False)

    def install(self, update: AvailableUpdate) -> bool:
        """„Jetzt aktualisieren“: copy, verify, hand over. ``True`` = the copy started."""
        if self.is_busy():
            log.info("The update controller is busy — the install request is ignored")
            return False
        self._start_copy(update)
        return True

    # -- the search --------------------------------------------------------------------

    def _start_check(self, *, interactive: bool) -> None:
        self._checking = True
        self._interactive = interactive
        log.info("Update check started (%s)", "by the user" if interactive else "at startup")
        task = _CheckTask(self._service)
        task.signals.finished.connect(self._on_check_finished)
        task.signals.failed.connect(self._on_check_failed)
        self._pool.start(task)

    @Slot(object)
    def _on_check_finished(self, result: object) -> None:
        interactive = self._interactive
        self._checking = False
        self._interactive = False
        if not isinstance(result, UpdateCheckResult):  # pragma: no cover - defensive
            self.finished.emit()
            return
        update = result.update
        if update is None:
            log.info(
                "No newer version in the update folder (installed %s, latest %s)",
                result.installed_version,
                result.latest_version,
            )
            if interactive:
                self._show_up_to_date(result.installed_version)
            self.finished.emit()
            return

        log.info("Version %s is available in %s", update.version, update.folder)
        if not interactive:
            self.update_found.emit(update)
            self.finished.emit()
            return
        if self._ask_to_install(result.installed_version, update):
            self.install(update)
        if not self._copying:
            self.finished.emit()

    @Slot(object)
    def _on_check_failed(self, error: object) -> None:
        interactive = self._interactive
        self._checking = False
        self._interactive = False
        panel_error = error if isinstance(error, PanelError) else UpdateError(_UNEXPECTED)
        if not interactive:
            # The startup check stays invisible — no share, no VPN, nothing published.
            log.info("Startup update check without result: %s", type(panel_error).__name__)
            self.finished.emit()
            return
        if isinstance(panel_error, UpdateFolderUnreachableError):
            self._warn(self.tr("Update-Laufwerk nicht erreichbar"), str(panel_error))
        else:
            self._warn(self.tr("Update nicht möglich"), str(panel_error))
        self.finished.emit()

    def _show_up_to_date(self, installed: str) -> None:
        dialogs.show_info(
            self._widget,
            self.tr("Keine Aktualisierung nötig"),
            self.tr(
                "Sie verwenden bereits die neueste Version ({0}). Es wurde nichts kopiert."
            ).format(installed),
        )

    def _ask_to_install(self, installed: str, update: AvailableUpdate) -> bool:
        dialog = UpdateAvailableDialog(installed, update, self._widget)
        return dialog.exec() == UpdateAvailableDialog.DialogCode.Accepted

    # -- the copy ----------------------------------------------------------------------

    def _start_copy(self, update: AvailableUpdate) -> None:
        self._copying = True
        self._cancel.clear()
        dialog = CopyProgressDialog(update.installer_name, self._widget)
        dialog.rejected.connect(self._on_copy_cancelled)
        self._progress = dialog
        # open() shows the dialog modally without a nested event loop, so signals from
        # the worker keep arriving and the progress bar actually moves.
        dialog.open()
        self.copy_started.emit()

        task = _CopyTask(self._service, update, default_download_directory(), self._cancel)
        task.signals.progress.connect(dialog.show_progress)
        task.signals.finished.connect(self._on_copy_finished)
        task.signals.failed.connect(self._on_copy_failed)
        self._pool.start(task)

    @Slot()
    def _on_copy_cancelled(self) -> None:
        # The worker sees the flag at the next chunk and removes the partial copy.
        self._cancel.set()
        log.info("The installer copy was cancelled by the user")

    @Slot(str)
    def _on_copy_finished(self, path: str) -> None:
        self._copying = False
        self._close_progress()
        try:
            self._service.launch_installer(Path(path))
        except PanelError as exc:
            self._warn(self.tr("Update nicht möglich"), str(exc))
            self.finished.emit()
            return
        self.application_should_quit.emit()
        self.finished.emit()

    @Slot(object)
    def _on_copy_failed(self, error: object) -> None:
        self._copying = False
        self._close_progress()
        if isinstance(error, CopyCancelledError):
            # The user asked for it — a cancelled copy is not an error to report.
            self.finished.emit()
            return
        panel_error = error if isinstance(error, PanelError) else UpdateError(_UNEXPECTED)
        self._warn(self.tr("Update nicht möglich"), str(panel_error))
        self.finished.emit()

    # -- helpers -----------------------------------------------------------------------

    def _warn(self, title: str, text: str) -> None:
        dialogs.show_error(self._widget, title, text)

    def _close_progress(self) -> None:
        dialog, self._progress = self._progress, None
        if dialog is None:
            return
        # Disconnect first: done() emits rejected(), which would otherwise look like a
        # cancellation the user never asked for.
        with suppress(RuntimeError, TypeError):
            dialog.rejected.disconnect(self._on_copy_cancelled)
        dialog.done(0)
        dialog.deleteLater()
