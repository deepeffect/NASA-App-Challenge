"""Birim normalizasyonu ve dönüşümleri (katalog birimine çevirmek için)."""

from collections.abc import Callable

import numpy as np
import pandas as pd

UNIT_ALIASES: dict[str, str] = {
    "°c": "degC", "c": "degC", "celsius": "degC", "degc": "degC", "deg_c": "degC", "℃": "degC",
    "°f": "degF", "f": "degF", "fahrenheit": "degF", "degf": "degF",
    "bpm": "bpm", "beats/min": "bpm", "1/min": "bpm", "/min": "bpm",
    "%": "%", "percent": "%", "pct": "%",
    "kg": "kg", "lb": "lb", "lbs": "lb",
    "h": "h", "hr": "h", "hrs": "h", "hour": "h", "hours": "h", "sa": "h", "saat": "h",
    "min": "min", "mins": "min", "minute": "min", "minutes": "min", "dk": "min",
    "ms": "ms", "s": "s", "sec": "s", "seconds": "s",
    "msv": "mSv", "usv": "uSv", "µsv": "uSv", "μsv": "uSv", "sv": "Sv",
    "mmhg": "mmHg",
    "score": "score_1_5", "score_1_5": "score_1_5", "1-5": "score_1_5", "likert": "score_1_5",
}

CONVERSIONS: dict[tuple[str, str], Callable[[np.ndarray], np.ndarray]] = {
    ("degF", "degC"): lambda v: (v - 32.0) * 5.0 / 9.0,
    ("lb", "kg"): lambda v: v * 0.45359237,
    ("s", "ms"): lambda v: v * 1000.0,
    ("min", "h"): lambda v: v / 60.0,
    ("h", "min"): lambda v: v * 60.0,
    ("uSv", "mSv"): lambda v: v / 1000.0,
    ("Sv", "mSv"): lambda v: v * 1000.0,
}


def normalize_unit(u: object) -> str | None:
    if u is None or (isinstance(u, float) and np.isnan(u)):
        return None
    s = str(u).strip()
    if not s:
        return None
    return UNIT_ALIASES.get(s.lower(), s)


def convert(values: pd.Series, from_unit: str, to_unit: str) -> pd.Series | None:
    """Dönüşüm yoksa None."""
    if from_unit == to_unit:
        return values
    fn = CONVERSIONS.get((from_unit, to_unit))
    if fn is None:
        return None
    return pd.Series(fn(values.to_numpy(dtype=float)), index=values.index)
