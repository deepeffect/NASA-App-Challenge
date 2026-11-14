"""Seri özellikleri: kişisel baseline, z-score, 7 günlük rolling ortalama/z, 7 günlük eğim.

Tüm hesaplar nedenseldir (t günündeki değer sadece ≤ t verisine bakar), bu yüzden `as_of` ile
kesilmiş veri, tam verinin aynı güne kadarki kısmıyla birebir aynı sonucu verir.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from app.analysis.catalog import MetricDef, RulesConfig
from app.models.schemas import Baseline


@dataclass
class SeriesFeatures:
    astronaut_id: str
    metric: str
    frame: pd.DataFrame  # index: gün (DatetimeIndex, günlük, boşluklar NaN); kolonlar aşağıda
    baseline: Baseline | None
    eval_from: pd.Timestamp | None  # sapma/trend kuralları bu günden itibaren değerlendirilir

    FEATURE_COLUMNS = ("value", "min", "max", "n", "z", "roll7", "z7", "slope7")

    @property
    def eval_mask(self) -> np.ndarray:
        if self.eval_from is None:
            return np.zeros(len(self.frame), dtype=bool)
        return np.asarray(self.frame.index >= self.eval_from, dtype=bool)

    def last_valid(self) -> pd.Series | None:
        valid = self.frame["value"].dropna()
        if valid.empty:
            return None
        return self.frame.loc[valid.index[-1]]


def rolling_slope(y: pd.Series, window: int, min_periods: int) -> pd.Series:
    """Rolling lineer regresyon eğimi (birim/gün), NaN'ları atlayarak. Vektörel (döngüsüz)."""
    t = np.arange(len(y), dtype=float)
    m = y.notna().to_numpy(dtype=float)
    yv = np.nan_to_num(y.to_numpy(dtype=float), nan=0.0)

    def rsum(a: np.ndarray) -> np.ndarray:
        return pd.Series(a).rolling(window, min_periods=1).sum().to_numpy()

    n = rsum(m)
    sx, sy = rsum(t * m), rsum(yv)
    sxy, sxx = rsum(t * yv), rsum(t * t * m)
    denom = n * sxx - sx * sx
    with np.errstate(divide="ignore", invalid="ignore"):
        slope = (n * sxy - sx * sy) / denom
    slope[(n < min_periods) | (np.abs(denom) < 1e-9)] = np.nan
    return pd.Series(slope, index=y.index)


def compute_baseline(
    values: pd.Series, first_day: pd.Timestamp, as_of: pd.Timestamp, rules: RulesConfig, min_std: float
) -> tuple[Baseline | None, pd.Timestamp | None]:
    """İlk N takvim gününün ortalama ve std'si. Yeterli veri yoksa (None, None)."""
    end = min(first_day + pd.Timedelta(days=rules.baseline.days - 1), as_of)
    window = values.loc[first_day:end].dropna()
    if len(window) < max(rules.baseline.min_days, 2):
        return None, None
    std = float(window.std(ddof=1))
    baseline = Baseline(
        mean=float(window.mean()),
        std=max(std if np.isfinite(std) else 0.0, min_std, 1e-9),
        n_days=int(len(window)),
        start=first_day.date(),
        end=end.date(),
    )
    return baseline, end + pd.Timedelta(days=1)


def compute_series_features(
    astronaut_id: str,
    metric: MetricDef,
    daily: pd.DataFrame,
    as_of: pd.Timestamp,
    rules: RulesConfig,
) -> SeriesFeatures:
    """`daily`: tek bir (astronot, metrik) için day/value/min/max/n kolonlu günlük satırlar."""
    d = daily.set_index("day").sort_index()
    first_day = d.index.min()
    idx = pd.date_range(first_day, as_of, freq="D")
    f = d[["value", "min", "max", "n"]].reindex(idx)
    f.index.name = "day"

    baseline, eval_from = compute_baseline(f["value"], first_day, as_of, rules, metric.min_std)
    w, mp = rules.window_days, rules.min_periods
    f["roll7"] = f["value"].rolling(w, min_periods=mp).mean()
    f["slope7"] = rolling_slope(f["value"], w, mp)
    if baseline:
        f["z"] = (f["value"] - baseline.mean) / baseline.std
        f["z7"] = (f["roll7"] - baseline.mean) / baseline.std
    else:
        f["z"] = np.nan
        f["z7"] = np.nan
    return SeriesFeatures(astronaut_id=astronaut_id, metric=metric.name, frame=f, baseline=baseline, eval_from=eval_from)


def direction_sign(bad_direction: str) -> int:
    """up → +1, down → -1, both → 0 (mutlak değer kullanılır)."""
    return {"up": 1, "down": -1}.get(bad_direction, 0)


def badness(x: pd.Series | np.ndarray, bad_direction: str) -> np.ndarray:
    """Kötü yönde pozitif olacak şekilde işaretle (both → |x|)."""
    a = np.asarray(x, dtype=float)
    s = direction_sign(bad_direction)
    return np.abs(a) if s == 0 else s * a
