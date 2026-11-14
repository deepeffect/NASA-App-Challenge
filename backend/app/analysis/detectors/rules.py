"""Kural tabanlı dedektörler: eşik aşımı, baseline sapması, sürekli kötüleşen trend.

LLM'den tamamen bağımsızdır. Parametreler: config/rules.yaml, eşikler: config/metrics.yaml.
"""

import numpy as np

from app.analysis.catalog import MetricDef, RulesConfig
from app.analysis.context import AnalysisContext
from app.analysis.detectors.base import register_detector
from app.analysis.episodes import LEVEL_TO_SEVERITY, day_start, event_status, find_episodes, make_event_id
from app.analysis.features import SeriesFeatures, badness, direction_sign
from app.analysis.text import fmt, fmt_val
from app.models.schemas import Contributor, DateWindow, HealthEvent


def _r(x: float | None, nd: int) -> float | None:
    if x is None or not np.isfinite(x):
        return None
    return round(float(x), nd)


def contributor(sf: SeriesFeatures, m: MetricDef, value: float | None, z: float | None, weight: float = 1.0) -> Contributor:
    b = sf.baseline
    return Contributor(
        metric=m.name,
        value=_r(value, m.decimals + 1),
        baseline=_r(b.mean, m.decimals + 1) if b else None,
        z=_r(z, 2),
        weight=round(weight, 3),
        threshold_verified=m.threshold_verified if m.has_thresholds else None,
    )


def make_rule_event(
    ctx: AnalysisContext, sf: SeriesFeatures, m: MetricDef, *, detector: str, start_i: int, end_i: int,
    level: int, score: float, title: str, description: str, contrib: Contributor,
) -> HealthEvent:
    days = sf.frame.index
    start, end = days[start_i].date(), days[end_i].date()
    return HealthEvent(
        event_id=make_event_id(sf.astronaut_id, "rule", detector, m.name, start),
        astronaut_id=sf.astronaut_id,
        detected_at=day_start(start),
        source="rule",
        system=m.system,
        severity=LEVEL_TO_SEVERITY[level],  # type: ignore[arg-type]
        score=round(float(np.clip(score, 0.0, 1.0)), 3),
        title=title,
        window=DateWindow(start=start, end=end),
        contributors=[contrib],
        status=event_status(end, ctx.as_of, ctx.rules.episodes.merge_gap_days),  # type: ignore[arg-type]
        detector=detector,
        description=description,
    )


def _ref_index(ctx: AnalysisContext, sf: SeriesFeatures, s: int, e: int, strength: np.ndarray) -> int:
    """Aktif olayda en son gün, bitmiş olayda en güçlü gün referans alınır."""
    end = sf.frame.index[e].date()
    if event_status(end, ctx.as_of, ctx.rules.episodes.merge_gap_days) == "active":
        return e
    seg = strength[s : e + 1]
    return s + int(np.nanargmax(seg)) if np.isfinite(seg).any() else e


def deviation_levels(sf: SeriesFeatures, m: MetricDef, rules: RulesConfig) -> tuple[np.ndarray, np.ndarray]:
    """(günlük seviye 0-3, kötü yönde z7) — trend dedektörü de bastırma için kullanır."""
    bad = badness(sf.frame["z7"], m.bad_direction)
    mask = sf.eval_mask
    cfg = rules.deviation
    lv = np.zeros(len(bad), dtype=int)
    with np.errstate(invalid="ignore"):
        lv[mask & (bad >= cfg.z_info)] = 1
        lv[mask & (bad >= cfg.z_warning)] = 2
        lv[mask & (bad >= cfg.z_critical)] = 3
    return lv, bad


# =============================================================================
@register_detector("threshold")
class ThresholdDetector:
    """Günlük değer (ortalama metriklerde günün en kötü ölçümü) eşik dışında."""

    name = "rule.threshold"

    def detect(self, ctx: AnalysisContext) -> list[HealthEvent]:
        out: list[HealthEvent] = []
        gap = ctx.rules.episodes.merge_gap_days
        for sf, m in ctx.iter_series(rule="threshold"):
            if not m.has_thresholds:
                continue
            t = m.thresholds
            f = sf.frame
            extremes = m.aggregation == "mean"
            low_v = (f["min"] if extremes else f["value"]).to_numpy(dtype=float)
            high_v = (f["max"] if extremes else f["value"]).to_numpy(dtype=float)
            lvl_low = np.zeros(len(f), dtype=int)
            lvl_high = np.zeros(len(f), dtype=int)
            with np.errstate(invalid="ignore"):
                for num, rng in ((2, t.warning), (3, t.critical)):
                    if rng is None:
                        continue
                    if rng.low is not None:
                        lvl_low = np.where(low_v < rng.low, np.maximum(lvl_low, num), lvl_low)
                    if rng.high is not None:
                        lvl_high = np.where(high_v > rng.high, np.maximum(lvl_high, num), lvl_high)
            level = np.maximum(lvl_low, lvl_high)
            for s, e in find_episodes(level, gap):
                sev = int(level[s : e + 1].max())
                ref = _ref_index(ctx, sf, s, e, level.astype(float))
                side = "low" if lvl_low[ref] >= lvl_high[ref] and lvl_low[ref] > 0 else "high"
                value = low_v[ref] if side == "low" else high_v[ref]
                ref_lvl = lvl_low[ref] if side == "low" else lvl_high[ref]
                rng = t.critical if ref_lvl == 3 else t.warning
                thr = (rng.low if side == "low" else rng.high) if rng else None
                kind = "critical" if sev == 3 else "warning"
                title = f"{m.label()} {'below lower' if side == 'low' else 'above upper'} {kind} threshold"
                verified = "verified" if m.threshold_verified else "placeholder, not verified"
                desc = (
                    f"{f.index[ref].date():%Y-%m-%d}: {fmt_val(value, m.unit, m.decimals)} — "
                    f"{'critical' if ref_lvl == 3 else 'warning'} threshold {fmt_val(thr, m.unit, m.decimals)} ({verified})."
                )
                b = sf.baseline
                z = (value - b.mean) / b.std if b else None
                out.append(make_rule_event(
                    ctx, sf, m, detector=self.name, start_i=s, end_i=e, level=sev,
                    score=0.95 if m.threshold_verified else 0.7, title=title, description=desc,
                    contrib=contributor(sf, m, value, z),
                ))
        return out


# =============================================================================
@register_detector("baseline_deviation")
class DeviationDetector:
    """7 günlük ortalama, kişisel baseline'dan kötü yönde |z| eşiği kadar sapmış."""

    name = "rule.baseline_deviation"

    def detect(self, ctx: AnalysisContext) -> list[HealthEvent]:
        out: list[HealthEvent] = []
        cfg = ctx.rules.deviation
        for sf, m in ctx.iter_series(rule="baseline_deviation"):
            if sf.baseline is None:
                continue
            level, bad = deviation_levels(sf, m, ctx.rules)
            f = sf.frame
            for s, e in find_episodes(level, ctx.rules.episodes.merge_gap_days):
                sev = int(level[s : e + 1].max())
                ref = _ref_index(ctx, sf, s, e, bad)
                z7 = float(f["z7"].iloc[ref])
                roll = float(f["roll7"].iloc[ref])
                peak = float(np.nanmax(bad[s : e + 1]))
                word = "below" if z7 < 0 else "above"
                b = sf.baseline
                desc = (
                    f"7-day mean {fmt_val(roll, m.unit, m.decimals)}; personal normal "
                    f"{fmt_val(b.mean, m.unit, m.decimals)} ± {fmt_val(b.std, m.unit, m.decimals)} (z = {fmt(z7, 1)})."
                )
                out.append(make_rule_event(
                    ctx, sf, m, detector=self.name, start_i=s, end_i=e, level=sev,
                    score=float(np.clip(0.5 + (peak - cfg.z_warning) * 0.15, 0.3, 0.99)),
                    title=f"{m.label()} {word} personal normal",
                    description=desc, contrib=contributor(sf, m, roll, z7),
                ))
        return out


# =============================================================================
def run_lengths(b: np.ndarray) -> np.ndarray:
    out = np.zeros(len(b), dtype=int)
    c = 0
    for i, v in enumerate(b):
        c = c + 1 if v else 0
        out[i] = c
    return out


@register_detector("trend")
class TrendDetector:
    """7 günlük eğim art arda N gün kötü yönde VE 7 günlük ortalama belirgin değişmiş (erken uyarı)."""

    name = "rule.trend"

    def detect(self, ctx: AnalysisContext) -> list[HealthEvent]:
        out: list[HealthEvent] = []
        cfg, w = ctx.rules.trend, ctx.rules.window_days
        for sf, m in ctx.iter_series(rule="trend"):
            if sf.baseline is None:
                continue
            f = sf.frame
            n = len(f)
            slope = f["slope7"].to_numpy(dtype=float)
            roll = f["roll7"].to_numpy(dtype=float)
            z7_bad = badness(f["z7"], m.bad_direction)
            mask = sf.eval_mask
            with np.errstate(invalid="ignore"):
                z7_ok = z7_bad >= cfg.min_z7
            sgn = direction_sign(m.bad_direction)
            level = np.zeros(n, dtype=int)
            change_bad = np.full(n, np.nan)
            runs = np.zeros(n, dtype=int)
            dirs = np.zeros(n, dtype=int)
            for d in ([sgn] if sgn else [1, -1]):
                with np.errstate(invalid="ignore"):
                    run = run_lengths(mask & (d * slope > 0))
                k = np.minimum(run, w)
                prev_idx = np.arange(n) - k
                prev = np.where(prev_idx >= 0, roll[np.clip(prev_idx, 0, None)], np.nan)
                ch = d * (roll - prev) / sf.baseline.std
                with np.errstate(invalid="ignore"):
                    lv = np.where((run >= cfg.min_consecutive_days) & (ch >= cfg.warning_change_std), 2,
                                  np.where((run >= cfg.min_consecutive_days) & (ch >= cfg.info_change_std), 1, 0))
                lv = np.where(z7_ok, lv, 0)
                better = lv > level
                level = np.where(better, lv, level)
                change_bad = np.where(better, ch, change_bad)
                runs = np.where(better, run, runs)
                dirs = np.where(better, d, dirs)
            if cfg.suppress_when_deviation and "baseline_deviation" in m.rules:
                dev, _ = deviation_levels(sf, m, ctx.rules)
                level[dev >= 2] = 0
            for s, e in find_episodes(level, ctx.rules.episodes.merge_gap_days):
                sev = int(level[s : e + 1].max())
                ref = _ref_index(ctx, sf, s, e, np.where(level > 0, change_bad, np.nan))
                if level[ref] == 0:  # aktif epizodun son günü bastırılmış olabilir
                    ref = s + int(np.flatnonzero(level[s : e + 1])[-1])
                k = int(min(runs[ref], w))
                delta = float(roll[ref] - roll[ref - k]) if ref - k >= 0 else float("nan")
                word = "rising" if dirs[ref] > 0 else "falling"
                desc = (
                    f"Worsening for {int(runs[ref])} days: 7-day mean {'rose' if delta > 0 else 'fell'} by "
                    f"{fmt_val(abs(delta), m.unit, m.decimals)} over the last {k} days "
                    f"(about {fmt(abs(delta) / max(k, 1), m.decimals + 1)} per day)."
                )
                peak = float(np.nanmax(np.where(level[s : e + 1] > 0, change_bad[s : e + 1], np.nan)))
                out.append(make_rule_event(
                    ctx, sf, m, detector=self.name, start_i=s, end_i=e, level=sev,
                    score=float(np.clip(peak / 4.0, 0.3, 0.95)),
                    title=f"{m.label()}: sustained {word} trend", description=desc,
                    contrib=contributor(sf, m, float(roll[ref]), float(f["z7"].iloc[ref])),
                ))
        return out
