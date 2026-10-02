"""Project-specific widgets built from Qt primitives."""

from __future__ import annotations

from PySide6.QtWidgets import QWidget


def set_style_property(widget: QWidget, name: str, value: object) -> None:
    """Set a dynamic property read by app.qss and re-polish (Qt does not do it itself)."""
    if widget.property(name) == value:
        return
    widget.setProperty(name, value)
    style = widget.style()
    if style is not None:
        style.unpolish(widget)
        style.polish(widget)
        for child in widget.findChildren(QWidget):
            style.unpolish(child)
            style.polish(child)
    widget.update()
