"""Device settings: interval, temperature offset, thresholds, piezo, reset, clock.

The dialog only collects input. Values are shown and validated through
``umwelt_ctl.protocol`` (``config_input_text`` / ``parse_config_input``) — the one place that
knows the scaled integers; the dialog itself does no unit conversion. Sending happens in
the serial worker via the controller callbacks.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from umwelt_ctl import protocol as p

THRESHOLDS = ("T_HI", "T_LO", "RH_HI", "RH_LO")


def _phys(key: str, raw: int) -> float:
    """Scaled device integer -> number for a spin box (via protocol's formatting)."""
    return float(p.config_input_text(key, raw).replace(",", "."))


def _text(value: float, decimals: int) -> str:
    return f"{value:.{decimals}f}"


class _Threshold(QWidget):
    """Checkbox "aktiv" + value; unchecked = OFF."""

    def __init__(self, key: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        k = p.CONFIG_KEYS[key]
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.active = QCheckBox(self.tr("aktiv"), self)
        self.value = QDoubleSpinBox(self)
        self.value.setDecimals(2)
        self.value.setRange(_phys(key, k.lo), _phys(key, k.hi))
        self.value.setSingleStep(0.5)
        self.value.setSuffix(" °C" if k.kind == "temp" else " %")
        self.value.setAccessibleName(k.label_de)
        self.active.toggled.connect(self.value.setEnabled)
        layout.addWidget(self.active)
        layout.addWidget(self.value, 1)

    def set_raw(self, key: str, raw: int | None) -> None:
        self.active.setChecked(raw is not None)
        self.value.setEnabled(raw is not None)
        if raw is not None:
            self.value.setValue(_phys(key, raw))

    def text(self) -> str:
        return _text(self.value.value(), 2) if self.active.isChecked() else p.CFG_OFF


class SettingsDialog(QDialog):
    def __init__(self, config: dict[str, int | None], *,
                 sync_time: Callable[[], None], reset_config: Callable[[], None],
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Geräteeinstellungen"))
        self.setMinimumWidth(460)
        self._config = dict(config)
        self._sync_time = sync_time
        self._reset_config = reset_config
        self.reset_requested = False

        layout = QVBoxLayout(self)
        hint = QLabel(self.tr("Die Einstellungen werden auf dem Gerät (EEPROM) gespeichert und "
                              "gelten sofort – auch ohne PC."), self)
        hint.setObjectName("dialogHint")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        meas = QGroupBox(self.tr("Messung"), self)
        form = QFormLayout(meas)
        self.interval = QSpinBox(meas)
        k = p.CONFIG_KEYS["INTERVAL"]
        self.interval.setRange(k.lo, k.hi)
        self.interval.setSuffix(" s")
        form.addRow(self.tr("&Messintervall:"), self.interval)
        self.offset = QDoubleSpinBox(meas)
        k = p.CONFIG_KEYS["TEMP_OFFSET"]
        self.offset.setDecimals(2)
        self.offset.setRange(_phys("TEMP_OFFSET", k.lo), _phys("TEMP_OFFSET", k.hi))
        self.offset.setSingleStep(0.1)
        self.offset.setSuffix(" °C")
        form.addRow(self.tr("&Temperatur-Offset:"), self.offset)
        layout.addWidget(meas)

        alarm = QGroupBox(self.tr("Alarm-Schwellwerte"), self)
        aform = QFormLayout(alarm)
        self.thresholds = {key: _Threshold(key, alarm) for key in THRESHOLDS}
        for key, widget in self.thresholds.items():
            aform.addRow(p.CONFIG_KEYS[key].label_de + ":", widget)
        self.buzzer = QCheckBox(self.tr("&Piezo-Ton bei Alarm"), alarm)
        aform.addRow("", self.buzzer)
        layout.addWidget(alarm)

        tools = QHBoxLayout()
        self.sync_button = QPushButton(self.tr("&Uhr synchronisieren"), self)
        self.sync_button.setToolTip(self.tr("Geräteuhr auf die PC-Zeit stellen"))
        self.sync_button.clicked.connect(self._on_sync)
        self.reset_button = QPushButton(self.tr("&Standardwerte …"), self)
        self.reset_button.setToolTip(self.tr("Alle Einstellungen auf dem Gerät auf die "
                                             "Standardwerte zurücksetzen"))
        self.reset_button.clicked.connect(self._on_reset)
        tools.addWidget(self.sync_button)
        tools.addStretch(1)
        tools.addWidget(self.reset_button)
        layout.addLayout(tools)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel, self)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(self.tr("Ü&bernehmen"))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(self.tr("Abbrechen"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._load(config)

    def _load(self, cfg: dict[str, int | None]) -> None:
        self.interval.setValue(cfg.get("INTERVAL") or p.CONFIG_KEYS["INTERVAL"].default or 10)
        self.offset.setValue(_phys("TEMP_OFFSET", cfg.get("TEMP_OFFSET") or 0))
        for key, widget in self.thresholds.items():
            widget.set_raw(key, cfg.get(key))
        self.buzzer.setChecked(bool(cfg.get("BUZZER")))

    def entered(self) -> dict[str, str]:
        """All fields as user text in physical units (for ``parse_config_input``)."""
        out = {"INTERVAL": str(self.interval.value()),
               "TEMP_OFFSET": _text(self.offset.value(), 2),
               "BUZZER": "1" if self.buzzer.isChecked() else "0"}
        out.update({key: w.text() for key, w in self.thresholds.items()})
        return out

    def changes(self) -> dict[str, str]:
        """Only the fields that differ from the device values (nothing else is sent)."""
        out: dict[str, str] = {}
        for key, text in self.entered().items():
            try:
                wire = p.parse_config_input(key, text)
            except ValueError:
                out[key] = text  # let the device layer report it
                continue
            current = self._config.get(key)
            old = p.CFG_OFF if current is None else str(current)
            if wire != old:
                out[key] = text
        return out

    @Slot()
    def _on_sync(self) -> None:
        self._sync_time()

    @Slot()
    def _on_reset(self) -> None:
        answer = QMessageBox.question(
            self, self.tr("Standardwerte wiederherstellen?"),
            self.tr("Alle Einstellungen auf dem Gerät (Messintervall 10 s, Offset 0, "
                    "Schwellwerte aus, Piezo aus) werden auf die Standardwerte "
                    "zurückgesetzt. Die Touch-Kalibrierung bleibt erhalten.\n\nFortfahren?"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.reset_requested = True
        self._reset_config()
        self.done(QDialog.DialogCode.Rejected)  # nothing else to send
