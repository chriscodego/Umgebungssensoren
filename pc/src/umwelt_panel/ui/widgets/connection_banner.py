"""Full-width bar with the state of the USB link: coloured, with text, port choice and button.

States (property ``severity`` for app.qss): ``ok`` connected, ``busy`` connecting,
``warning`` connected but the sensor is missing, ``error`` waiting for the device / failed,
``idle`` disconnected by the user. The text always says the state — colour is never alone.
"""

from __future__ import annotations

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from umwelt_panel.ui.widgets import set_style_property

AUTO_PORT_TEXT = "Automatisch"


class PortComboBox(QComboBox):
    """Combo box that asks for a fresh port list each time it opens."""

    about_to_show = Signal()

    def showPopup(self) -> None:  # noqa: N802 - Qt override
        self.about_to_show.emit()
        super().showPopup()


class ConnectionBanner(QFrame):
    connect_requested = Signal(str)     # port; "" = automatic detection
    disconnect_requested = Signal()
    settings_requested = Signal()
    ports_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("connectionBanner")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        self.setProperty("severity", "idle")
        self._connected = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(12)

        texts = QVBoxLayout()
        texts.setSpacing(0)
        self._text = QLabel(self)
        self._text.setObjectName("connectionBannerText")
        self._text.setWordWrap(True)
        self._detail = QLabel(self)
        self._detail.setObjectName("connectionBannerDetail")
        self._detail.setWordWrap(True)
        texts.addWidget(self._text)
        texts.addWidget(self._detail)
        layout.addLayout(texts, 1)

        port_label = QLabel(self.tr("&Port:"), self)
        port_label.setObjectName("connectionBannerPortLabel")
        self._ports = PortComboBox(self)
        self._ports.setObjectName("portCombo")
        self._ports.setMinimumContentsLength(12)
        self._ports.setAccessibleName(self.tr("Serieller Port"))
        self._ports.addItem(AUTO_PORT_TEXT, "")
        self._ports.about_to_show.connect(self.ports_requested)
        port_label.setBuddy(self._ports)
        layout.addWidget(port_label)
        layout.addWidget(self._ports)

        self._button = QPushButton(self.tr("&Verbinden"), self)
        self._button.setObjectName("connectionBannerButton")
        self._button.clicked.connect(self._on_button)
        layout.addWidget(self._button)

        self._settings = QPushButton(self.tr("&Einstellungen …"), self)
        self._settings.setObjectName("connectionBannerButton")
        self._settings.clicked.connect(self.settings_requested)
        layout.addWidget(self._settings)

    # -- API -----------------------------------------------------------------------

    def message(self) -> str:
        return self._text.text()

    def detail(self) -> str:
        return self._detail.text()

    def severity(self) -> str:
        return str(self.property("severity"))

    def button(self) -> QPushButton:
        return self._button

    def settings_button(self) -> QPushButton:
        return self._settings

    def port_combo(self) -> QComboBox:
        return self._ports

    def selected_port(self) -> str:
        return str(self._ports.currentData() or "")

    def set_ports(self, ports: list[str], selected: str | None = None) -> None:
        current = selected if selected is not None else self.selected_port()
        self._ports.blockSignals(True)
        self._ports.clear()
        self._ports.addItem(AUTO_PORT_TEXT, "")
        for port in ports:
            self._ports.addItem(port, port)
        if current and self._ports.findData(current) < 0:
            self._ports.addItem(current, current)  # remembered port, currently not plugged in
        self._ports.setCurrentIndex(max(0, self._ports.findData(current or "")))
        self._ports.blockSignals(False)

    def show_state(self, severity: str, text: str, detail: str = "", *,
                   connected: bool, busy: bool = False) -> None:
        self._connected = connected
        self._text.setText(text)
        self._detail.setText(detail)
        self._detail.setVisible(bool(detail))
        self._button.setText(self.tr("&Trennen") if connected else self.tr("&Verbinden"))
        self._button.setEnabled(not busy)
        self._ports.setEnabled(not connected and not busy)
        self._settings.setEnabled(connected)
        set_style_property(self, "severity", severity)

    @Slot()
    def _on_button(self) -> None:
        if self._connected:
            self.disconnect_requested.emit()
        else:
            self.connect_requested.emit(self.selected_port())
