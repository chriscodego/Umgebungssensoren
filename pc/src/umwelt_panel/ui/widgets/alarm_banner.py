"""Alarm bar: hidden without alarm, red and blinking while unacknowledged, pale once
acknowledged (the flag stays while the cause persists, SPEC "Alarm"). Always with text."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QWidget

from umwelt_panel.ui.widgets import set_style_property


class AlarmBanner(QFrame):
    ack_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("alarmBanner")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        self.setProperty("state", "unacked")
        self.setProperty("blink", False)
        self.setVisible(False)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 8, 14, 8)
        self._text = QLabel(self)
        self._text.setObjectName("alarmBannerText")
        self._text.setWordWrap(True)
        layout.addWidget(self._text, 1)
        self._button = QPushButton(self.tr("&Quittieren"), self)
        self._button.setObjectName("alarmBannerButton")
        self._button.setToolTip(self.tr("Alarm am Gerät quittieren (Anzeige und Piezo aus)"))
        self._button.clicked.connect(self.ack_requested)
        layout.addWidget(self._button)

    def message(self) -> str:
        return self._text.text()

    def button(self) -> QPushButton:
        return self._button

    def show_alarm(self, texts: list[str], unacked: bool) -> None:
        state = self.tr("nicht quittiert") if unacked else self.tr("quittiert")
        self._text.setText(self.tr("⚠ ALARM ({0}): {1}").format(state, ", ".join(texts)))
        self._button.setEnabled(unacked)
        set_style_property(self, "state", "unacked" if unacked else "acked")
        if not unacked:
            set_style_property(self, "blink", False)
        self.setVisible(True)

    def clear(self) -> None:
        self.setVisible(False)
        self._text.clear()
        set_style_property(self, "blink", False)

    def toggle_blink(self) -> None:
        if self.isVisible() and self.property("state") == "unacked":
            set_style_property(self, "blink", not bool(self.property("blink")))
