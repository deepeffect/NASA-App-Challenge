"""Analiz motoru: ham long ölçümler → günlük özellikler → dedektörler → olaylar → skorlar.

Saf fonksiyonel: DB'ye dokunmaz. Aynı girdi + as_of → aynı çıktı.
"""

from dataclasses import dataclass, field
from datetime import date, datetime

import pandas as pd

from app.analysis.catalog import Catalog, RulesConfig, load_catalog, load_rules
from app.analysis.context import AnalysisContext
from app.analysis.daily import to_daily, to_utc_naive
from app.analysis.detectors import build_detectors
from app.analysis.detectors.base import EventDetector
from app.analysis.features import SeriesFeatures, compute_series_features
from app.analysis.scoring import score_systems
from app.models.schemas import SEVERITY_RANK, AstronautInfo, HealthEvent, MissionInfo, OverallStatus, SystemScore

DEFAULT_DETECTORS = ["threshold", "baseline_deviation", "trend", "system_pattern"]


@dataclass
class AstronautAnalysis:
    info: AstronautInfo
    features: dict[str, SeriesFeatures]
    events: list[HealthEvent]
    systems: list[SystemScore]
    overall: OverallStatus
    last_measurement_at: datetime | None

    @property
    def active_events(self) -> list[HealthEvent]:
        return [e for e in self.events if e.status == "active"]


@dataclass
class AnalysisResult:
    as_of: date | None
    start_date: date | None
    latest_date: date | None
    astronauts: dict[str, AstronautAnalysis] = field(default_factory=dict)

    @property
    def events(self) -> list[HealthEvent]:
        return [e for a in self.astronauts.values() for e in a.events]

    def find_event(self, event_id: str) -> HealthEvent | None:
        return next((e for e in self.events if e.event_id == event_id), None)

    def mission(self) -> MissionInfo:
        if self.start_date is None or self.as_of is None or self.latest_date is None:
            return MissionInfo()
        return MissionInfo(
            start_date=self.start_date,
            latest_date=self.latest_date,
            as_of=self.as_of,
            mission_day=(self.as_of - self.start_date).days + 1,
            total_days=(self.latest_date - self.start_date).days + 1,
        )


def event_sort_key(e: HealthEvent) -> tuple:
    return (-SEVERITY_RANK[e.severity], e.status != "active", e.window.start, e.event_id)


class AnalysisEngine:
    def __init__(
        self,
        catalog: Catalog | None = None,
        rules: RulesConfig | None = None,
        detectors: list[str] | list[EventDetector] | None = None,
    ) -> None:
        self.catalog = catalog or load_catalog()
        self.rules = rules or load_rules()
        dets = detectors if detectors is not None else DEFAULT_DETECTORS
        self.detectors: list[EventDetector] = build_detectors(dets) if dets and isinstance(dets[0], str) else list(dets)  # type: ignore[arg-type]

    def run(self, measurements: pd.DataFrame, astronauts: list[AstronautInfo], as_of: date | None = None) -> AnalysisResult:
        known = {a.id: a for a in astronauts}
        if measurements.empty:
            res = AnalysisResult(as_of=None, start_date=None, latest_date=None)
            for a in astronauts:
                systems, overall = score_systems([], {}, self.catalog, self.rules)
                res.astronauts[a.id] = AstronautAnalysis(a, {}, [], systems, overall, None)
            return res

        ts = to_utc_naive(measurements["timestamp"])
        start = ts.min().floor("D")
        latest = ts.max().floor("D")
        a_ts = pd.Timestamp(as_of) if as_of else latest
        a_ts = min(max(a_ts, start), latest)

        cut_mask = ts < a_ts + pd.Timedelta(days=1)
        cut = measurements.loc[cut_mask]
        cut_ts = ts[cut_mask]
        daily = to_daily(cut, self.catalog)

        features: dict[tuple[str, str], SeriesFeatures] = {}
        for (aid, metric), g in daily.groupby(["astronaut_id", "metric"], sort=True):
            mdef = self.catalog.get(str(metric))
            if mdef is None:
                continue
            features[(str(aid), str(metric))] = compute_series_features(str(aid), mdef, g, a_ts, self.rules)

        ids = sorted(set(known) | set(cut["astronaut_id"].astype(str).unique()))
        ctx = AnalysisContext(
            as_of=a_ts.date(), catalog=self.catalog, rules=self.rules, astronaut_ids=ids, features=features, raw=cut,
        )
        for det in self.detectors:
            ctx.events.extend(det.detect(ctx))

        last_ts = cut_ts.groupby(cut["astronaut_id"].astype(str).to_numpy()).max()
        res = AnalysisResult(as_of=a_ts.date(), start_date=start.date(), latest_date=latest.date())
        for aid in ids:
            info = known.get(aid) or AstronautInfo(id=aid, name=aid)
            feats = {m: sf for (x, m), sf in features.items() if x == aid}
            evs = sorted((e for e in ctx.events if e.astronaut_id == aid), key=event_sort_key)
            systems, overall = score_systems(evs, feats, self.catalog, self.rules)
            last = last_ts.get(aid)
            res.astronauts[aid] = AstronautAnalysis(
                info=info,
                features=feats,
                events=evs,
                systems=systems,
                overall=overall,
                last_measurement_at=last.tz_localize("UTC").to_pydatetime() if last is not None and pd.notna(last) else None,
            )
        return res
