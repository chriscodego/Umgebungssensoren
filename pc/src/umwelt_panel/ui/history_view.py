"""Tab „Verlauf": chart of one quantity over a period from the database, CSV export, clear.

Queries and the export run in the thread pool (``ui.tasks``); the view only shows results.
States: loading („Lade Verlauf …"), empty (no values in the period), error (message in the
chart area), populated.
"""

from __future__ import annotations

import datetime as _dt
import logging
from pathlib import Path

from PySide6.QtCore import QStandardPaths, QTimer, Signal, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from umwelt_panel.core.errors import PanelError
from umwelt_panel.core.models import LogStats, Sample, TimeRange, format_count, utc_now
from umwelt_panel.core.services.log_service import MeasurementLog
from umwelt_panel.core.services.settings_service import SettingsService
from umwelt_panel.ui import dialogs
from umwelt_panel.ui.metrics import METRICS
from umwelt_panel.ui.tasks import run_in_pool
from umwelt_panel.ui.widgets.history_chart import HistoryChart

log = logging.getLogger(__name__)

AUTO_REFRESH_MS = 30_000


def error_text(exc: BaseException) -> str:
    return str(exc) if isinstance(exc, PanelError | OSError) else (
        f"Unerwarteter Fehler: {exc.__class__.__name__}. Details stehen in der Logdatei.")


class HistoryView(QWidget):
    log_changed = Signal()      # after clear/export: statistics should be refreshed
    message = Signal(str)       # status bar text

    def __init__(self, log_service: MeasurementLog, settings: SettingsService,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._log = log_service
        self._settings = settings
        self._samples: list[Sample] = []
        self._range_shown: tuple[_dt.datetime | None, _dt.datetime] | None = None
        self._loading = False
        self._busy = False

        layout = QVBoxLayout(self)
        bar = QHBoxLayout()
        bar.addWidget(QLabel(self.tr("&Zeitraum:"), self))
        self.range_combo = QComboBox(self)
        for rng in TimeRange:
            self.range_combo.addItem(rng.label_de, rng.value)
        bar.itemAt(0).widget().setBuddy(self.range_combo)
        bar.addWidget(self.range_combo)
        metric_label = QLabel(self.tr("&Messgröße:"), self)
        self.metric_combo = QComboBox(self)
        for m in METRICS.values():
            self.metric_combo.addItem(m.title, m.key)
        metric_label.setBuddy(self.metric_combo)
        bar.addSpacing(12)
        bar.addWidget(metric_label)
        bar.addWidget(self.metric_combo)
        bar.addStretch(1)
        self.refresh_button = QPushButton(self.tr("&Aktualisieren"), self)
        self.export_button = QPushButton(self.tr("CSV e&xportieren …"), self)
        self.export_button.setToolTip(self.tr("Gewählten Zeitraum als CSV speichern "
                                              "(Semikolon, UTF-8, Dezimalkomma)"))
        self.clear_button = QPushButton(self.tr("Log &löschen …"), self)
        self.clear_button.setToolTip(self.tr("Alle gespeicherten Messwerte löschen "
                                             "(mit Rückfrage)"))
        for b in (self.refresh_button, self.export_button, self.clear_button):
            bar.addWidget(b)
        layout.addLayout(bar)

        self.chart = HistoryChart(self)
        layout.addWidget(self.chart, 1)
        self.stats_label = QLabel(self)
        self.stats_label.setObjectName("historyStatsLabel")
        self.stats_label.setWordWrap(True)
        layout.addWidget(self.stats_label)

        self._restore()
        self.range_combo.currentIndexChanged.connect(self._on_range_changed)
        self.metric_combo.currentIndexChanged.connect(self._on_metric_changed)
        self.refresh_button.clicked.connect(self.refresh)
        self.export_button.clicked.connect(self.export_csv)
        self.clear_button.clicked.connect(self.clear_log)

        self._timer = QTimer(self)
        self._timer.setInterval(AUTO_REFRESH_MS)
        self._timer.timeout.connect(self._auto_refresh)
        self._timer.start()

    # -- state -----------------------------------------------------------------------

    def _restore(self) -> None:
        rng = self._settings.history_range()
        self.range_combo.setCurrentIndex(max(0, self.range_combo.findData(rng.value)))
        metric = self._settings.history_metric()
        self.metric_combo.setCurrentIndex(max(0, self.metric_combo.findData(metric)))

    def time_range(self) -> TimeRange:
        return TimeRange(self.range_combo.currentData())

    def metric(self) -> str:
        return str(self.metric_combo.currentData())

    def is_loading(self) -> bool:
        return self._loading

    def set_stats(self, stats: LogStats) -> None:
        if stats.count == 0:
            text = self.tr("Das Log ist leer.")
        else:
            first = stats.first_utc.astimezone() if stats.first_utc else None
            since = f" · seit {first:%d.%m.%Y %H:%M}" if first else ""
            text = self.tr("{0} Messwerte im Log{1}").format(format_count(stats.count), since)
        self.stats_label.setText(text)
        self.clear_button.setEnabled(stats.count > 0 and not self._busy)

    # -- loading ---------------------------------------------------------------------

    @Slot()
    def refresh(self) -> None:
        if self._loading:
            return
        self._loading = True
        rng = self.time_range()
        now = utc_now()
        if not self._samples:
            self.chart.set_placeholder(self.tr("Lade Verlauf …"))
        self.refresh_button.setEnabled(False)

        def ok(samples: list[Sample]) -> None:
            self._loading = False
            self.refresh_button.setEnabled(True)
            start = rng.start(now)
            self._samples = samples
            self._range_shown = (None if start is None else start.astimezone(), now.astimezone())
            self._draw()

        def err(exc: BaseException) -> None:
            self._loading = False
            self.refresh_button.setEnabled(True)
            self._samples = []
            log.warning("Verlauf nicht lesbar: %s", exc)
            self.chart.set_placeholder(self.tr("Verlauf nicht lesbar: {0}").format(
                error_text(exc)))

        run_in_pool(lambda: self._log.series(rng, now=now), ok, err)

    def _draw(self) -> None:
        metric = METRICS[self.metric()]
        points = [(s.ts_utc.astimezone(), metric.value(s.measurement)) for s in self._samples]
        start, end = self._range_shown or (None, None)
        self.chart.set_series(points, unit=metric.unit, decimals=metric.decimals,
                              min_span=metric.min_span, start=start, end=end)

    @Slot()
    def _on_range_changed(self) -> None:
        self._settings.set_history_range(self.time_range())
        self._samples = []
        self.refresh()

    @Slot()
    def _on_metric_changed(self) -> None:
        self._settings.set_history_metric(self.metric())
        self._draw()

    @Slot()
    def _auto_refresh(self) -> None:
        if self.isVisible():
            self.refresh()

    def showEvent(self, event) -> None:  # noqa: ANN001, N802 - Qt override
        super().showEvent(event)
        self.refresh()

    # -- export / clear -------------------------------------------------------------

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.export_button.setEnabled(not busy)
        self.clear_button.setEnabled(not busy)

    @Slot()
    def export_csv(self) -> None:
        rng = self.time_range()
        docs = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)
        name = f"umwelt_messwerte_{rng.value}_{_dt.datetime.now():%Y-%m-%d_%H%M}.csv"
        path = dialogs.save_file_name(self, self.tr("Messwerte als CSV exportieren"),
                                      str(Path(docs or Path.home()) / name))
        if not path:
            return
        self._set_busy(True)
        self.message.emit(self.tr("Exportiere {0} …").format(rng.label_de))

        def ok(rows: int) -> None:
            self._set_busy(False)
            text = self.tr("{0} Messwerte ({1}) exportiert nach:\n{2}").format(
                format_count(rows), rng.label_de, path)
            if rows == 0:
                text = self.tr("Im Zeitraum „{0}“ gibt es keine Messwerte; die Datei enthält "
                               "nur die Kopfzeile:\n{1}").format(rng.label_de, path)
            self.message.emit(self.tr("CSV-Export: {0} Zeilen nach {1}").format(rows, path))
            dialogs.show_info(self, self.tr("CSV-Export"), text)
            self.log_changed.emit()

        def err(exc: BaseException) -> None:
            self._set_busy(False)
            dialogs.show_error(self, self.tr("CSV-Export fehlgeschlagen"), error_text(exc))

        run_in_pool(lambda: self._log.export_csv(rng, path), ok, err)

    @Slot()
    def clear_log(self) -> None:
        if not dialogs.ask_yes_no(
                self, self.tr("Messwert-Log löschen?"),
                self.tr("Alle gespeicherten Messwerte in\n{0}\nwerden endgültig gelöscht. Das "
                        "kann nicht rückgängig gemacht werden. Vorher als CSV exportieren?\n\n"
                        "Jetzt löschen?").format(self._log.path)):
            return
        self._set_busy(True)

        def ok(n: int) -> None:
            self._set_busy(False)
            self._samples = []
            self.message.emit(self.tr("{0} Messwerte gelöscht.").format(format_count(n)))
            self.log_changed.emit()
            self.refresh()

        def err(exc: BaseException) -> None:
            self._set_busy(False)
            dialogs.show_error(self, self.tr("Löschen fehlgeschlagen"), error_text(exc))

        run_in_pool(self._log.clear, ok, err)
