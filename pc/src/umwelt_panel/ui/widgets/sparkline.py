"""A tiny history curve of one live value (hand-made with QPainter, no chart library).

No axes, no labels: the curve only answers "steady, rising or falling?". Invalid values
(``None``) leave a gap instead of being drawn as zero.
"""

from __future__ import annotations

from collections import deque

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QPainter, QPaintEvent, QPalette, QPen, QPolygonF
from PySide6.QtWidgets import QSizePolicy, QWidget

#: 1 h at the device's default interval of 10 s.
SPARKLINE_CAPACITY = 360


class Sparkline(QWidget):
    def __init__(self, min_span: float, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._values: deque[float | None] = deque(maxlen=SPARKLINE_CAPACITY)
        #: smallest vertical span, so sensor noise does not look like a jump
        self._min_span = min_span
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        point = self.font().pointSizeF()
        self.setMinimumHeight(int(40 * max(point / 9.0 if point > 0 else 1.0, 1.0)))
        self.setAccessibleName(self.tr("Verlauf der letzten Messwerte"))

    def append(self, value: float | None) -> None:
        self._values.append(None if value is None else float(value))
        self.update()

    def clear(self) -> None:
        if self._values:
            self._values.clear()
            self.update()

    def values(self) -> tuple[float | None, ...]:
        return tuple(self._values)

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        palette = self.palette()
        area = self.rect().adjusted(2, 3, -2, -3)
        painter.setPen(QPen(palette.color(QPalette.ColorRole.Mid), 1.0, Qt.PenStyle.DotLine))
        painter.drawLine(area.left(), area.center().y(), area.right(), area.center().y())

        valid = [v for v in self._values if v is not None]
        if len(valid) < 2:
            return
        lo, hi = min(valid), max(valid)
        if hi - lo < self._min_span:
            mid = (hi + lo) / 2
            lo, hi = mid - self._min_span / 2, mid + self._min_span / 2
        span = hi - lo
        step = area.width() / max(1, SPARKLINE_CAPACITY - 1)
        offset = SPARKLINE_CAPACITY - len(self._values)  # newest value at the right edge
        painter.setPen(QPen(palette.color(QPalette.ColorRole.Highlight), 2.0))
        segment: list[QPointF] = []
        for i, v in enumerate(self._values):
            if v is None:
                _draw(painter, segment)
                segment = []
                continue
            segment.append(QPointF(area.left() + (offset + i) * step,
                                   area.bottom() - (v - lo) / span * area.height()))
        _draw(painter, segment)


def _draw(painter: QPainter, points: list[QPointF]) -> None:
    if len(points) >= 2:
        painter.drawPolyline(QPolygonF(points))
    elif len(points) == 1:
        painter.drawEllipse(points[0], 1.5, 1.5)
