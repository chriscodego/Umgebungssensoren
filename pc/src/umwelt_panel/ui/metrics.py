"""The four displayed quantities: titles, units and how to read them from a Measurement.

Physical values come from the ``Measurement`` properties and texts from the ``format_*``
functions of ``umwelt_ctl.protocol`` — no unit conversion happens in the UI.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from umwelt_ctl import protocol as p
from umwelt_ctl.protocol import Measurement


@dataclass(frozen=True)
class Metric:
    key: str
    title: str
    unit: str
    decimals: int
    min_span: float          # smallest vertical span of charts (noise is not a jump)
    value: Callable[[Measurement], float | None]
    text: Callable[[Measurement], str]


METRICS: dict[str, Metric] = {m.key: m for m in (
    Metric("t", "Temperatur", "°C", 1, 0.5, lambda m: m.temperature_c,
           lambda m: p.format_temperature(m.t)),
    Metric("rh", "Luftfeuchte", "% rF", 1, 2.0, lambda m: m.humidity_pct,
           lambda m: p.format_humidity(m.rh)),
    Metric("p", "Luftdruck", "hPa", 1, 1.0, lambda m: m.pressure_hpa,
           lambda m: p.format_pressure(m.p)),
    Metric("gas", "Gaswiderstand (Luftqualität)", "kΩ", 1, 5.0, lambda m: m.gas_kohm,
           lambda m: p.format_gas(m.gas)),
)}
