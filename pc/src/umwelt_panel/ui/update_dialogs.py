"""The two dialogs of the update feature: the result, and the copy progress.

None of them knows how an update works. They collect a decision and hand it back —
:class:`~umwelt_panel.ui.update_controller.UpdateController` does the talking to
:class:`~umwelt_panel.core.services.update_service.UpdateService`.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Slot
from PySide6.QtWidgets import (
    QAbstractButton,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from umwelt_panel.core.services.update_service import AvailableUpdate

log = logging.getLogger(__name__)

MEGABYTE = 1024 * 1024


class UpdateAvailableDialog(QDialog):
    """Shows what is installed, what is available, and lets the user decide."""

    def __init__(
        self, installed_version: str, update: AvailableUpdate, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setObjectName("updateAvailableDialog")
        self.setWindowTitle(self.tr("Aktualisierung verfügbar"))
        self.setModal(True)
        self.setMinimumSize(560, 420)

        layout = QVBoxLayout(self)

        headline = QLabel(self.tr("Version {0} steht zur Verfügung.").format(update.version), self)
        headline.setObjectName("updateHeadline")
        headline.setWordWrap(True)
        layout.addWidget(headline)

        self._versions = QLabel(self)
        self._versions.setObjectName("updateVersionsLabel")
        self._versions.setWordWrap(True)
        self._versions.setText(
            self.tr("Installiert: {0}     Verfügbar: {1}").format(installed_version, update.version)
        )
        layout.addWidget(self._versions)

        self._published = QLabel(self)
        self._published.setObjectName("updatePublishedLabel")
        if update.published_on:
            self._published.setText(self.tr("Veröffentlicht am {0}").format(update.published_on))
        else:
            self._published.setText(self.tr("Veröffentlichungsdatum unbekannt"))
        layout.addWidget(self._published)

        notes_caption = QLabel(self.tr("Änderungen:"), self)
        layout.addWidget(notes_caption)

        self._notes = QPlainTextEdit(self)
        self._notes.setObjectName("updateReleaseNotes")
        # Read-only plain text: the notes come from a file on a share and are never
        # interpreted as markup.
        self._notes.setReadOnly(True)
        self._notes.setPlainText(
            update.notes or self.tr("Für diese Version wurden keine Notizen hinterlegt.")
        )
        self._notes.setAccessibleName(self.tr("Änderungsnotizen"))
        layout.addWidget(self._notes, 1)

        self._size = QLabel(self)
        self._size.setObjectName("updateSizeLabel")
        self._size.setText(
            self.tr("Installer: {0} ({1:.0f} MB) vom Institutslaufwerk").format(
                update.installer_name, update.installer_size / MEGABYTE
            )
        )
        self._size.setWordWrap(True)
        layout.addWidget(self._size)

        self._hint = QLabel(
            self.tr(
                "Für die Aktualisierung wird das Control Panel beendet; die Verbindung zum "
                "Gerät wird getrennt und die Aufzeichnung pausiert bis zum nächsten Start. "
                "Das Gerät selbst misst und warnt weiter."
            ),
            self,
        )
        self._hint.setObjectName("updateQuitHint")
        self._hint.setWordWrap(True)
        layout.addWidget(self._hint)

        self._buttons = QDialogButtonBox(self)
        self._update_button = self._buttons.addButton(
            self.tr("&Jetzt aktualisieren"), QDialogButtonBox.ButtonRole.AcceptRole
        )
        self._later_button = self._buttons.addButton(
            self.tr("&Später"), QDialogButtonBox.ButtonRole.RejectRole
        )
        self._later_button.setDefault(True)
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        layout.addWidget(self._buttons)

        self.setTabOrder(self._notes, self._update_button)
        self.setTabOrder(self._update_button, self._later_button)

    def versions_text(self) -> str:
        return self._versions.text()

    def published_text(self) -> str:
        return self._published.text()

    def notes_text(self) -> str:
        return self._notes.toPlainText()

    def size_text(self) -> str:
        return self._size.text()

    def update_button(self) -> QAbstractButton:
        return self._update_button

    def later_button(self) -> QAbstractButton:
        return self._later_button


class CopyProgressDialog(QDialog):
    """Progress of the copy, with a cancel button that really stops it.

    The dialog is modal but the copy runs in the thread pool, so the window keeps
    painting and „Abbrechen“ stays clickable for the whole transfer.
    """

    def __init__(self, installer_name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("updateCopyDialog")
        self.setWindowTitle(self.tr("Aktualisierung wird vorbereitet"))
        self.setModal(True)
        self.setMinimumWidth(480)
        self._cancelled = False

        layout = QVBoxLayout(self)

        self._caption = QLabel(
            self.tr("„{0}“ wird vom Institutslaufwerk kopiert und geprüft …").format(
                installer_name
            ),
            self,
        )
        self._caption.setWordWrap(True)
        layout.addWidget(self._caption)

        self._bar = QProgressBar(self)
        self._bar.setObjectName("updateProgressBar")
        self._bar.setRange(0, 0)  # Endless until the first chunk arrives.
        self._bar.setAccessibleName(self.tr("Kopierfortschritt"))
        layout.addWidget(self._bar)

        self._status = QLabel(self.tr("Kopieren beginnt …"), self)
        self._status.setObjectName("updateCopyStatus")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)

        self._buttons = QDialogButtonBox(self)
        self._cancel_button = self._buttons.addButton(
            self.tr("&Abbrechen"), QDialogButtonBox.ButtonRole.RejectRole
        )
        self._cancel_button.setDefault(True)
        self._buttons.rejected.connect(self.reject)
        layout.addWidget(self._buttons)

    def is_cancelled(self) -> bool:
        return self._cancelled

    def progress_bar(self) -> QProgressBar:
        return self._bar

    def cancel_button(self) -> QPushButton:
        button = self._cancel_button
        assert isinstance(button, QPushButton)
        return button

    def status_text(self) -> str:
        return self._status.text()

    @Slot(int, int)
    def show_progress(self, copied: int, total: int) -> None:
        if total > 0:
            # QProgressBar holds an int; kilobytes keep a 500 MB installer in range.
            self._bar.setRange(0, max(1, total // 1024))
            self._bar.setValue(min(copied, total) // 1024)
            self._status.setText(
                self.tr("{0:.1f} von {1:.1f} MB kopiert").format(
                    copied / MEGABYTE, total / MEGABYTE
                )
            )
        else:
            self._status.setText(self.tr("{0:.1f} MB kopiert").format(copied / MEGABYTE))

    def reject(self) -> None:
        """Esc and „Abbrechen“ take the same route: mark cancelled, then close."""
        self._cancelled = True
        self._status.setText(self.tr("Kopieren wird abgebrochen …"))
        self._cancel_button.setEnabled(False)
        super().reject()
