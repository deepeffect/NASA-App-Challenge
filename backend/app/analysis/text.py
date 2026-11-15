"""Kural olaylarının başlık/açıklama metinleri için biçimlendirme yardımcıları (Türkçe)."""

import math

_UNITS = {"degC": "°C", "h": "sa", "min": "dk", "score_1_5": "/5"}


def unit_label(unit: str) -> str:
    return _UNITS.get(unit, unit)


def fmt(x: float | None, decimals: int = 1) -> str:
    """Türkçe ondalık virgül: 5.12 → '5,1'."""
    if x is None or (isinstance(x, float) and not math.isfinite(x)):
        return "—"
    s = f"{x:.{decimals}f}"
    return s.replace(".", ",")


def fmt_val(x: float | None, unit: str, decimals: int = 1) -> str:
    u = unit_label(unit)
    return f"{fmt(x, decimals)}{u}" if u.startswith("/") else f"{fmt(x, decimals)} {u}"
