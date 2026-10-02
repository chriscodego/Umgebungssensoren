"""Gas resistance trend, computed on the PC from the incoming values (no protocol field).

Same rule as the device display (handbook, chapter 8): compare each value with a moving
average (weight 1/8); more than ±5 % away means rising/falling. A higher gas resistance
means fewer oxidisable gases (VOC) — "rising" is the better direction.
"""

from __future__ import annotations

WEIGHT = 1 / 8
THRESHOLD = 0.05

RISING = "steigend"
FALLING = "fallend"
STEADY = "gleichbleibend"

ARROWS = {RISING: "↑", FALLING: "↓", STEADY: "→"}


class GasTrend:
    def __init__(self) -> None:
        self._avg: float | None = None
        self.direction: str | None = None

    def reset(self) -> None:
        self._avg = None
        self.direction = None

    def update(self, gas: int | None) -> str | None:
        """Feed one value (``None`` = invalid, ignored). Returns the current direction."""
        if gas is None:
            return self.direction
        if self._avg is None:
            self._avg = float(gas)
            self.direction = STEADY
            return self.direction
        if gas > self._avg * (1 + THRESHOLD):
            self.direction = RISING
        elif gas < self._avg * (1 - THRESHOLD):
            self.direction = FALLING
        else:
            self.direction = STEADY
        self._avg += (gas - self._avg) * WEIGHT
        return self.direction

    def text(self) -> str:
        """``"↑ steigend"`` or ``""`` while there is no value yet."""
        if self.direction is None:
            return ""
        return f"{ARROWS[self.direction]} {self.direction}"
