"""One live value tile: title, big number, a sub line (time/trend/state) and a sparkline.

The texts come pre-formatted from :mod:`umwelt_ctl.protocol` (decimal comma, units); this
widget does no unit conversion. ``--`` is shown for an invalid value, never ``0``.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QFrame, QLabel, QSizePolicy, QVBoxLayout, QWidget

from umwelt_panel.ui.widgets import set_style_property
from umwelt_panel.ui.widgets.sparkline import Sparkline

VALUE_FONT_FACTOR = 2.6
TITLE_FONT_FACTOR = 1.15
PLACEHOLDER = "--"


class ValueBox(QFrame):
    def __init__(self, title: str, min_span: float, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("valueBox")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setProperty("alarm", False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(4)

        self._title = QLabel(title, self)
        self._title.setObjectName("valueBoxTitle")
        self._title.setFont(self._scaled_font(TITLE_FONT_FACTOR, bold=True))
        layout.addWidget(self._title)

        self._value = QLabel(PLACEHOLDER, self)
        self._value.setObjectName("valueBoxValue")
        self._value.setFont(self._scaled_font(VALUE_FONT_FACTOR, bold=True))
        self._value.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._value.setAccessibleName(self.tr("{0}: aktueller Wert").format(title))
        layout.addWidget(self._value, 1)

        self._sub = QLabel("", self)
        self._sub.setObjectName("valueBoxSub")
        layout.addWidget(self._sub)

        self._sparkline = Sparkline(min_span, self)
        layout.addWidget(self._sparkline)

    def _scaled_font(self, factor: float, *, bold: bool) -> QFont:
        font = QFont(self.font())
        size = font.pointSizeF()
        font.setPointSizeF((size if size > 0 else 9.0) * factor)
        font.setBold(bold)
        return font

    # -- read-only view (tests, accessibility) -------------------------------------

    def title(self) -> str:
        return self._title.text()

    def value_text(self) -> str:
        return self._value.text()

    def sub_text(self) -> str:
        return self._sub.text()

    def sparkline(self) -> Sparkline:
        return self._sparkline

    # -- input ---------------------------------------------------------------------

    def show_value(self, text: str, sub: str = "", *, valid: bool = True) -> None:
        self._value.setText(text if valid else PLACEHOLDER)
        set_style_property(self._value, "state", "normal" if valid else "muted")
        self._sub.setText(sub)
        set_style_property(self._sub, "state", "normal" if valid else "error")

    def show_placeholder(self, sub: str, *, error: bool = False, text: str = PLACEHOLDER
                         ) -> None:
        self._value.setText(text)
        set_style_property(self._value, "state", "muted")
        self._sub.setText(sub)
        set_style_property(self._sub, "state", "error" if error else "normal")

    def set_alarm(self, active: bool) -> None:
        set_style_property(self, "alarm", bool(active))

    def append_history(self, value: float | None) -> None:
        self._sparkline.append(value)
