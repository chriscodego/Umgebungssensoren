"""History chart of one value over a period: axes, time labels, gaps — QPainter only.

Points are ``(local datetime, value | None)`` in physical units (already converted by
``umwelt_ctl.protocol``). ``None`` and long pauses (no data for more than five typical
steps, e.g. while the device was unplugged) break the line instead of bridging it.
"""

from __future__ import annotations

import datetime as _dt
import statistics

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPaintEvent, QPalette, QPen, QPolygonF
from PySide6.QtWidgets import QSizePolicy, QWidget

Point = tuple[_dt.datetime, float | None]


def _num(value: float, decimals: int) -> str:
    return f"{value:.{decimals}f}".replace(".", ",")


class HistoryChart(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("historyChart")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumHeight(220)
        self.setAccessibleName(self.tr("Verlaufsdiagramm"))
        self._points: list[Point] = []
        self._unit = ""
        self._decimals = 1
        self._min_span = 1.0
        self._start: _dt.datetime | None = None
        self._end: _dt.datetime | None = None
        self._placeholder = self.tr("Keine Messwerte im gewählten Zeitraum.")

    # -- API -----------------------------------------------------------------------

    def set_series(self, points: list[Point], *, unit: str, decimals: int, min_span: float,
                   start: _dt.datetime | None = None, end: _dt.datetime | None = None) -> None:
        self._points = sorted(points, key=lambda pt: pt[0])
        self._unit, self._decimals, self._min_span = unit, decimals, min_span
        self._start, self._end = start, end
        self._placeholder = self.tr("Keine Messwerte im gewählten Zeitraum.")
        self.update()

    def set_placeholder(self, text: str) -> None:
        self._points = []
        self._placeholder = text
        self.update()

    def points(self) -> list[Point]:
        return list(self._points)

    def placeholder(self) -> str:
        return "" if self._valid_count() >= 1 else self._placeholder

    def _valid_count(self) -> int:
        return sum(1 for _, v in self._points if v is not None)

    # -- painting ------------------------------------------------------------------

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pal = self.palette()
        text_color = pal.color(QPalette.ColorRole.WindowText)
        fm = QFontMetrics(self.font())
        valid = [(t, v) for t, v in self._points if v is not None]
        if not valid:
            painter.setPen(text_color)
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._placeholder)
            return

        values = [v for _, v in valid]
        lo, hi = min(values), max(values)
        if hi - lo < self._min_span:
            mid = (hi + lo) / 2
            lo, hi = mid - self._min_span / 2, mid + self._min_span / 2
        pad = (hi - lo) * 0.08
        lo, hi = lo - pad, hi + pad

        t0 = self._start or self._points[0][0]
        t1 = self._end or self._points[-1][0]
        if t1 <= t0:
            t1 = t0 + _dt.timedelta(seconds=1)
        span_s = (t1 - t0).total_seconds()

        label_w = max(fm.horizontalAdvance(f"{_num(v, self._decimals)} {self._unit}")
                      for v in (lo, hi)) + 12
        plot = QRectF(label_w, 10, self.width() - label_w - 14,
                      self.height() - 10 - fm.height() * 2 - 6)
        if plot.width() < 20 or plot.height() < 20:
            return

        def x_of(t: _dt.datetime) -> float:
            return plot.left() + (t - t0).total_seconds() / span_s * plot.width()

        def y_of(v: float) -> float:
            return plot.bottom() - (v - lo) / (hi - lo) * plot.height()

        # grid + y labels
        grid = QPen(pal.color(QPalette.ColorRole.Mid), 1.0, Qt.PenStyle.DotLine)
        for i in range(5):
            v = lo + (hi - lo) * i / 4
            y = y_of(v)
            painter.setPen(grid)
            painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            painter.setPen(text_color)
            painter.drawText(QRectF(0, y - fm.height() / 2, label_w - 6, fm.height()),
                             Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                             f"{_num(v, self._decimals)} {self._unit}")
        # x labels
        fmt = "%H:%M" if span_s <= 86400 * 1.01 else "%d.%m. %H:%M"
        for i in range(5):
            t = t0 + _dt.timedelta(seconds=span_s * i / 4)
            x = plot.left() + plot.width() * i / 4
            painter.setPen(grid)
            painter.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()))
            text = t.strftime(fmt)
            w = fm.horizontalAdvance(text)
            painter.setPen(text_color)
            painter.drawText(QPointF(min(max(x - w / 2, 0), self.width() - w - 2),
                                     plot.bottom() + fm.ascent() + 4), text)
        painter.setPen(QPen(text_color, 1.0))
        painter.drawRect(plot)

        # the curve, broken at invalid values and long pauses
        times = [t for t, _ in self._points]
        steps = [(b - a).total_seconds() for a, b in zip(times, times[1:], strict=False)
                 if b > a]
        max_gap = 5 * statistics.median(steps) if steps else float("inf")
        painter.setPen(QPen(QColor("#1565c0"), 2.0))
        segment: list[QPointF] = []
        last_t: _dt.datetime | None = None
        for t, v in self._points:
            if v is None or (last_t is not None and (t - last_t).total_seconds() > max_gap):
                _flush(painter, segment)
                segment = []
            if v is not None:
                segment.append(QPointF(x_of(t), y_of(v)))
            last_t = t
        _flush(painter, segment)


def _flush(painter: QPainter, segment: list[QPointF]) -> None:
    if len(segment) >= 2:
        painter.drawPolyline(QPolygonF(segment))
    elif len(segment) == 1:
        painter.drawEllipse(segment[0], 2.0, 2.0)
