"""The few standard dialogs the panel uses, in one place (tests replace them)."""

from __future__ import annotations

from PySide6.QtWidgets import QFileDialog, QMessageBox, QWidget


def ask_yes_no(parent: QWidget | None, title: str, text: str) -> bool:
    """Confirmation for destructive actions; "Nein" is the default button."""
    answer = QMessageBox.question(parent, title, text,
                                  QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                  QMessageBox.StandardButton.No)
    return answer == QMessageBox.StandardButton.Yes


def show_error(parent: QWidget | None, title: str, text: str) -> None:
    QMessageBox.warning(parent, title, text)


def show_info(parent: QWidget | None, title: str, text: str) -> None:
    QMessageBox.information(parent, title, text)


def save_file_name(parent: QWidget | None, title: str, suggestion: str) -> str:
    """Path chosen by the user, or ``""`` if cancelled."""
    path, _ = QFileDialog.getSaveFileName(parent, title, suggestion,
                                          "CSV-Dateien (*.csv);;Alle Dateien (*)")
    return path
