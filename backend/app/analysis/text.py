"""Kural olaylarının başlık/açıklama metinleri için biçimlendirme yardımcıları (İngilizce)."""

import math

_UNITS = {"degC": "°C", "score_1_5": "/5"}


def unit_label(unit: str) -> str:
    return _UNITS.get(unit, unit)


def fmt(x: float | None, decimals: int = 1) -> str:
    """Ondalık nokta: 5.12 → '5.1'."""
    if x is None or (isinstance(x, float) and not math.isfinite(x)):
        return "—"
    return f"{x:.{decimals}f}"


def fmt_val(x: float | None, unit: str, decimals: int = 1) -> str:
    u = unit_label(unit)
    return f"{fmt(x, decimals)}{u}" if u.startswith("/") else f"{fmt(x, decimals)} {u}"
