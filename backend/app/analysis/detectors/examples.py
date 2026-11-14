"""ÖRNEK ML-tarzı dedektörler — GERÇEK ML DEĞİLDİR.

Amaç: (1) ML ekibine dedektör arayüzünü göstermek, (2) arayüz ekibinin changepoint ve forecast
katmanlarını gerçek veriyle görebilmesi. Varsayılan olarak KAPALIDIR; açmak için:
  ANALYSIS_DETECTORS=threshold,baseline_deviation,trend,example_changepoint,example_forecast,system_pattern

ML ekibi bunları ruptures / Isolation Forest / gerçek tahmin modelleriyle değiştirecek.
Sadece warning+ aktif kural olayı olan metriklerde çalışırlar (ctx.events'e bakarak).
"""

import numpy as np

from app.analysis.context import AnalysisContext
from app.analysis.detectors.base import register_detector
from app.analysis.detectors.rules import contributor
from app.analysis.episodes import day_start, make_event_id
from app.analysis.features import badness
from app.analysis.text import fmt
from app.models.schemas import SEVERITY_RANK, DateWindow, Forecast, ForecastPoint, HealthEvent

_TRIGGERS = ("rule.baseline_deviation", "rule.trend", "rule.threshold")


def _flagged_series(ctx: AnalysisContext) -> dict[tuple[str, str], HealthEvent]:
    """warning+ aktif kural olayı olan (astronot, metrik) → en erken başlayan olay."""
    out: dict[tuple[str, str], HealthEvent] = {}
    for e in ctx.events:
        if e.detector in _TRIGGERS and e.status == "active" and SEVERITY_RANK[e.severity] >= 2:
            key = (e.astronaut_id, e.contributors[0].metric)
            if key not in out or e.window.start < out[key].window.start:
                out[key] = e
    return out


@register_detector("example_changepoint")
class ExampleChangepointDetector:
    """Tek değişim noktalı ortalama kayması (ikili bölme, t-istatistiği). ruptures yerine geçici."""

    name = "ml.example_changepoint"
    LOOKBACK_DAYS = 60
    MIN_STAT = 5.0

    def detect(self, ctx: AnalysisContext) -> list[HealthEvent]:
        out: list[HealthEvent] = []
        for (aid, metric), trigger in sorted(_flagged_series(ctx).items()):
            sf = ctx.series(aid, metric)
            m = ctx.catalog.metrics[metric]
            if sf is None or sf.baseline is None:
                continue
            y = sf.frame["value"].iloc[-self.LOOKBACK_DAYS :].dropna()
            if len(y) < 20:
                continue
            v = y.to_numpy(dtype=float)
            best_k, best_stat = None, 0.0
            for k in range(7, len(v) - 3):
                a, b = v[:k], v[k:]
                pooled = np.sqrt(((len(a) - 1) * a.var(ddof=1) + (len(b) - 1) * b.var(ddof=1)) / (len(v) - 2))
                stat = abs(b.mean() - a.mean()) / (max(pooled, 1e-9) * np.sqrt(1 / len(a) + 1 / len(b)))
                if stat > best_stat:
                    best_k, best_stat = k, stat
            if best_k is None or best_stat < self.MIN_STAT:
                continue
            cp = y.index[best_k].date()
            after = float(v[best_k:].mean())
            z = (after - sf.baseline.mean) / sf.baseline.std
            if badness(np.array([z]), m.bad_direction)[0] <= 0:
                continue  # iyileşme yönünde kayma
            out.append(HealthEvent(
                event_id=make_event_id(aid, "changepoint", self.name, metric, cp),
                astronaut_id=aid,
                detected_at=day_start(ctx.as_of),
                source="changepoint",
                system=m.system,
                severity="warning",
                score=round(min(0.95, best_stat / 15), 3),
                title=f"{m.label()}: persistent level shift (example detector)",
                window=DateWindow(start=cp, end=ctx.as_of),
                contributors=[contributor(sf, m, after, z)],
                changepoint_date=cp,
                status="active",
                detector=self.name,
                description=f"Change point on {cp:%Y-%m-%d}; mean since then is z = {fmt(z, 1)} from baseline.",
            ))
        return out


@register_detector("example_forecast")
class ExampleForecastDetector:
    """Son 14 güne doğrusal fit, 7 gün ileri projeksiyon. Gerçek tahmin modeli yerine geçici."""

    name = "ml.example_forecast"
    FIT_DAYS = 14
    HORIZON = 7

    def detect(self, ctx: AnalysisContext) -> list[HealthEvent]:
        import pandas as pd

        out: list[HealthEvent] = []
        zw = ctx.rules.deviation.z_warning
        for (aid, metric), trigger in sorted(_flagged_series(ctx).items()):
            sf = ctx.series(aid, metric)
            m = ctx.catalog.metrics[metric]
            if sf is None or sf.baseline is None:
                continue
            y = sf.frame["value"].iloc[-self.FIT_DAYS :]
            t = np.arange(len(y), dtype=float)
            ok = y.notna().to_numpy()
            if ok.sum() < 7:
                continue
            slope, intercept = np.polyfit(t[ok], y.to_numpy(dtype=float)[ok], 1)
            resid = y.to_numpy(dtype=float)[ok] - (intercept + slope * t[ok])
            sd = float(np.std(resid, ddof=2)) if ok.sum() > 2 else 0.0
            pts = []
            for h in range(1, self.HORIZON + 1):
                x = len(y) - 1 + h
                val = intercept + slope * x
                band = 1.96 * sd * np.sqrt(1 + h / ok.sum())
                d = (pd.Timestamp(ctx.as_of) + pd.Timedelta(days=h)).date()
                pts.append(ForecastPoint(date=d, value=round(val, m.decimals + 1),
                                         lower=round(val - band, m.decimals + 1), upper=round(val + band, m.decimals + 1)))
            z_end = (pts[-1].value - sf.baseline.mean) / sf.baseline.std
            if badness(np.array([z_end]), m.bad_direction)[0] < zw:
                continue
            out.append(HealthEvent(
                event_id=make_event_id(aid, "forecast", self.name, metric, trigger.window.start),
                astronaut_id=aid,
                detected_at=day_start(ctx.as_of),
                source="forecast",
                system=m.system,
                severity="warning",
                score=0.55,
                title=f"{m.label()}: may keep worsening over the next {self.HORIZON} days (example forecast)",
                window=DateWindow(start=y.index[0].date(), end=ctx.as_of),
                contributors=[contributor(sf, m, pts[-1].value, z_end)],
                forecast=Forecast(metric=metric, method="linear", horizon_days=self.HORIZON, points=pts),
                status="active",
                detector=self.name,
                description=f"If the linear trend of the last {self.FIT_DAYS} days continues, forecast z on day {self.HORIZON} = {fmt(z_end, 1)}.",
            ))
        return out
