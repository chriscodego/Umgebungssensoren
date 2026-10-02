"""The non-modal hint that a newer version is waiting on the institute share.

It appears after the automatic check at startup and blocks nothing: live values, alarm
banner and recording keep running. „Später“ hides it until the next start; „Jetzt
aktualisieren“ hands the decision to the update controller.
"""

from __future__ import annotations

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QWidget,
)

from umwelt_panel.core.services.update_service import AvailableUpdate


class UpdateNotice(QFrame):
    """A slim bar: „Version X ist verfügbar“ plus „Jetzt aktualisieren“ and „Später“."""

    install_requested = Signal(object)
    dismissed = Signal()

    def __init__(self, installed_version: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("updateNotice")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        self.setVisible(False)
        self._installed_version = installed_version
        self._offered: AvailableUpdate | None = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(12)

        self._text = QLabel(self)
        self._text.setObjectName("updateNoticeText")
        self._text.setWordWrap(True)
        self._text.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(self._text, 1)

        self._install = QPushButton(self.tr("Jetzt &aktualisieren"), self)
        self._install.setObjectName("updateNoticeInstallButton")
        self._install.setAccessibleName(self.tr("Neue Version jetzt installieren"))
        self._install.clicked.connect(self._on_install)
        layout.addWidget(self._install, 0)

        self._later = QPushButton(self.tr("S&päter"), self)
        self._later.setObjectName("updateNoticeLaterButton")
        self._later.setAccessibleName(self.tr("Hinweis bis zum nächsten Start ausblenden"))
        self._later.clicked.connect(self._on_later)
        layout.addWidget(self._later, 0)

        self.setTabOrder(self._install, self._later)

    # -- API ---------------------------------------------------------------------------

    def show_update(self, offered: AvailableUpdate) -> None:
        self._offered = offered
        self._text.setText(
            self.tr(
                "Version {0} ist verfügbar (installiert: {1}). Aktualisiert wird erst "
                "nach Ihrem Klick."
            ).format(offered.version, self._installed_version)
        )
        self.setVisible(True)

    def offered_update(self) -> AvailableUpdate | None:
        return self._offered

    def message(self) -> str:
        return self._text.text()

    def install_button(self) -> QPushButton:
        return self._install

    def later_button(self) -> QPushButton:
        return self._later

    # -- internals ---------------------------------------------------------------------

    @Slot()
    def _on_install(self) -> None:
        if self._offered is not None:
            self.install_requested.emit(self._offered)

    @Slot()
    def _on_later(self) -> None:
        self.setVisible(False)
        self.dismissed.emit()
