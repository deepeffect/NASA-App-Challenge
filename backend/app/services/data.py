"""Veri servisi: DB ↔ analiz motoru köprüsü + veri endpoint'lerinin iş mantığı.

Analiz sonucu (veri versiyonu, kural/katalog dosya zamanları, as_of) anahtarıyla önbelleğe alınır.
Veri değişince (ingest, check-in, seed) versiyon değişir ve cache kendiliğinden geçersizleşir;
rules.yaml/metrics.yaml düzenlenince de motor yeniden kurulur (sunucuyu yeniden başlatmaya gerek yok).
"""

import threading
from collections import OrderedDict
from datetime import UTC, date, datetime, timedelta

import numpy as np
import pandas as pd
from sqlalchemy import func, select, text
from sqlmodel import Session

from app.analysis.catalog import load_catalog, load_rules
from app.analysis.engine import AnalysisEngine, AnalysisResult, AstronautAnalysis, event_sort_key
from app.config import get_settings
from app.ingest.pipeline import ingest_bytes
from app.ingest.store import insert_measurements
from app.models.schemas import (
    SEVERITY_RANK,
    AlertListResponse,
    AstronautInfo,
    AstronautSummary,
    CheckinListResponse,
    CheckinRecord,
    CheckinRequest,
    CheckinResponse,
    CrewMember,
    CrewResponse,
    DailyPoint,
    DateWindow,
    EventCounts,
    FeedbackRequest,
    FeedbackResponse,
    GroundReport,
    GroundReportMember,
    HealthEvent,
    IngestReport,
    MetricSeriesResponse,
    MetricSnapshot,
    RawPoint,
    ShareRequest,
    ShareResponse,
)
from app.models.tables import AlertFeedback, AlertShare, Astronaut, Checkin, as_utc, utcnow
from app.safety.emergency import detect_emergency

_CACHE_SIZE = 96


def _f(x: object, nd: int = 3) -> float | None:
    if x is None:
        return None
    try:
        v = float(x)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return round(v, nd) if np.isfinite(v) else None


class DataService:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._frame: tuple[tuple, pd.DataFrame, list[AstronautInfo]] | None = None
        self._results: OrderedDict[tuple, AnalysisResult] = OrderedDict()
        self._engine: tuple[tuple, AnalysisEngine] | None = None

    # ------------------------------------------------------------------ yükleme + cache
    def _config_key(self) -> tuple:
        s = get_settings()
        files = (s.config_dir / "metrics.yaml", s.config_dir / "rules.yaml")
        return (tuple(f.stat().st_mtime for f in files), tuple(s.analysis_detectors))

    def engine(self) -> AnalysisEngine:
        key = self._config_key()
        with self._lock:
            if self._engine is None or self._engine[0] != key:
                self._engine = (key, AnalysisEngine(load_catalog(), load_rules(), get_settings().analysis_detectors))
                self._results.clear()
            return self._engine[1]

    @staticmethod
    def data_version(session: Session) -> tuple:
        row = session.execute(text("SELECT COUNT(*), MAX(id), TOTAL(value) FROM measurement")).one()
        batch = session.execute(text("SELECT MAX(received_at) FROM ingestbatch")).scalar()
        n_astro = session.execute(text("SELECT COUNT(*) FROM astronaut")).scalar()
        return (*row, batch, n_astro)

    def _load(self, session: Session) -> tuple[tuple, pd.DataFrame, list[AstronautInfo]]:
        version = self.data_version(session)
        with self._lock:
            if self._frame and self._frame[0] == version:
                return self._frame
        df = pd.read_sql(text("SELECT astronaut_id, timestamp, metric, value, unit, source FROM measurement"),
                         session.connection())
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, format="ISO8601")
        astronauts = [AstronautInfo(id=a.id, name=a.name, role=a.role)
                      for a in session.execute(select(Astronaut).order_by(Astronaut.id)).scalars()]
        with self._lock:
            self._frame = (version, df, astronauts)
        return self._frame

    def analysis(self, session: Session, as_of: date | None = None) -> AnalysisResult:
        eng = self.engine()
        version, df, astronauts = self._load(session)
        key = (version, self._config_key(), as_of)
        with self._lock:
            if key in self._results:
                self._results.move_to_end(key)
                return self._results[key]
        result = eng.run(df, astronauts, as_of)
        with self._lock:
            self._results[key] = result
            while len(self._results) > _CACHE_SIZE:
                self._results.popitem(last=False)
        return result

    def invalidate(self) -> None:
        with self._lock:
            self._frame = None
            self._results.clear()

    # ------------------------------------------------------------------ feedback/paylaşım bindirme
    @staticmethod
    def overlay(session: Session, events: list[HealthEvent]) -> list[HealthEvent]:
        if not events:
            return []
        ids = [e.event_id for e in events]
        shares = {s.event_id: s.share_with_ground
                  for s in session.execute(select(AlertShare).where(AlertShare.event_id.in_(ids))).scalars()}
        fb: dict[str, str] = {}
        for f in session.execute(
            select(AlertFeedback).where(AlertFeedback.event_id.in_(ids)).order_by(AlertFeedback.created_at)
        ).scalars():
            fb[f.event_id] = f.verdict
        return [
            e.model_copy(update={"share_with_ground": shares.get(e.event_id, e.share_with_ground),
                                 "feedback": fb.get(e.event_id, e.feedback)})
            for e in events
        ]


_service = DataService()


def get_data_service() -> DataService:
    return _service


# =============================================================================
# Endpoint iş mantığı
# =============================================================================
def known_astronaut(session: Session, aid: str) -> bool:
    return session.get(Astronaut, aid) is not None


def _counts(events: list[HealthEvent]) -> EventCounts:
    return EventCounts(**{s: sum(1 for e in events if e.severity == s) for s in ("critical", "warning", "info")})


def crew(session: Session, as_of: date | None) -> CrewResponse:
    res = _service.analysis(session, as_of)
    members = []
    rank = {"red": 0, "yellow": 1}
    for a in res.astronauts.values():
        flagged = [s for s in a.systems if s.status in rank]
        attention = [s.system for s in sorted(flagged, key=lambda s: (rank[s.status], s.score or 0))]
        members.append(CrewMember(
            **a.info.model_dump(), status=a.overall.status, score=a.overall.score,
            active_events=_counts(a.active_events), attention_systems=attention,
            last_measurement_at=a.last_measurement_at,
        ))
    return CrewResponse(mission=res.mission(), astronauts=members)


def _snapshot(a: AstronautAnalysis, active: list[HealthEvent]) -> list[MetricSnapshot]:
    cat = load_catalog()
    alert = {c.metric for e in active if e.severity != "info" for c in e.contributors}
    watch = {c.metric for e in active if e.severity == "info" for c in e.contributors}
    out = []
    for m in cat.metrics.values():
        sf = a.features.get(m.name)
        last = sf.last_valid() if sf else None
        if last is None:
            out.append(MetricSnapshot(metric=m.name, display_name=m.label(), unit=m.unit, system=m.system,
                                      threshold_verified=m.threshold_verified, state="no_data"))
            continue
        b = sf.baseline
        out.append(MetricSnapshot(
            metric=m.name, display_name=m.label(), unit=m.unit, system=m.system, date=last.name.date(),
            value=_f(last["value"], m.decimals + 1), baseline_mean=_f(b.mean, m.decimals + 1) if b else None,
            baseline_std=_f(b.std, m.decimals + 2) if b else None, z=_f(last["z"], 2), z7=_f(last["z7"], 2),
            slope7=_f(last["slope7"], m.decimals + 2), threshold_verified=m.threshold_verified,
            state="alert" if m.name in alert else "watch" if m.name in watch else "normal",
        ))
    return out


def summary(session: Session, aid: str, as_of: date | None) -> AstronautSummary:
    res = _service.analysis(session, as_of)
    a = res.astronauts[aid]
    active = _service.overlay(session, a.active_events)
    return AstronautSummary(
        astronaut=a.info, mission=res.mission(), overall=a.overall, systems=a.systems,
        latest=_snapshot(a, active), active_events=active, last_measurement_at=a.last_measurement_at,
    )


def metric_series(session: Session, aid: str, metric: str, days: int, as_of: date | None, resolution: str) -> MetricSeriesResponse:
    res = _service.analysis(session, as_of)
    m = load_catalog().metrics[metric]
    a = res.astronauts[aid]
    sf = a.features.get(metric)
    eff_as_of = res.as_of
    daily: list[DailyPoint] = []
    raw: list[RawPoint] = []
    events: list[HealthEvent] = []
    if sf is not None and eff_as_of is not None:
        start = pd.Timestamp(eff_as_of) - pd.Timedelta(days=days - 1)
        f = sf.frame.loc[start:]
        for d, row in f[f["value"].notna()].iterrows():
            daily.append(DailyPoint(
                date=d.date(), value=_f(row["value"], 4), min=_f(row["min"], 4), max=_f(row["max"], 4),
                n=int(row["n"]), roll7=_f(row["roll7"], 4), z7=_f(row["z7"], 3),
            ))
        if resolution == "raw":
            rows = session.execute(
                text("SELECT timestamp, value, source FROM measurement WHERE astronaut_id=:a AND metric=:m "
                     "AND timestamp >= :s AND timestamp < :e ORDER BY timestamp"),
                {"a": aid, "m": metric, "s": start.strftime("%Y-%m-%d %H:%M:%S"),
                 "e": (pd.Timestamp(eff_as_of) + pd.Timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")},
            ).all()
            raw = [RawPoint(timestamp=as_utc(t), value=float(v), source=s) for t, v, s in rows]
        first = start.date()
        events = [e for e in a.events if any(c.metric == metric for c in e.contributors)
                  and (e.window.end >= first or (e.forecast is not None))]
    return MetricSeriesResponse(
        astronaut_id=aid, metric=m.to_info(), as_of=eff_as_of, resolution=resolution,  # type: ignore[arg-type]
        baseline=sf.baseline if sf else None, daily=daily, raw=raw, events=_service.overlay(session, events),
    )


def _checkin_record(c: Checkin) -> CheckinRecord:
    return CheckinRecord(id=c.id, astronaut_id=c.astronaut_id, timestamp=c.timestamp, mood=c.mood, stress=c.stress,
                         sleep_quality=c.sleep_quality, note=c.note, share_with_ground=c.share_with_ground,
                         emergency=c.emergency)


def _as_of_day_end(session: Session, as_of: date | None) -> datetime:
    res = _service.analysis(session, as_of)
    d = res.as_of or datetime.now(UTC).date()
    if as_of is None:  # canlı: sonradan eklenen check-in'ler de görünsün
        return datetime.now(UTC) + timedelta(days=1)
    return datetime.combine(d + timedelta(days=1), datetime.min.time(), UTC)


def checkins(session: Session, aid: str, days: int, as_of: date | None) -> CheckinListResponse:
    end = _as_of_day_end(session, as_of)
    res = _service.analysis(session, as_of)
    ref = res.as_of or end.date()
    start = datetime.combine(ref - timedelta(days=days - 1), datetime.min.time(), UTC)
    rows = session.execute(
        select(Checkin).where(Checkin.astronaut_id == aid, Checkin.timestamp >= start, Checkin.timestamp < end)
        .order_by(Checkin.timestamp.desc())
    ).scalars()
    return CheckinListResponse(astronaut_id=aid, checkins=[_checkin_record(c) for c in rows])


def create_checkin(session: Session, req: CheckinRequest) -> CheckinResponse:
    ts = req.timestamp or datetime.now(UTC)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    emergency = detect_emergency(req.note, req.lang)
    row = Checkin(astronaut_id=req.astronaut_id, timestamp=ts, mood=req.mood, stress=req.stress,
                  sleep_quality=req.sleep_quality, note=req.note, share_with_ground=req.share_with_ground,
                  emergency=emergency is not None)
    session.add(row)
    session.flush()
    df = pd.DataFrame([
        {"astronaut_id": req.astronaut_id, "timestamp": ts, "metric": m, "value": float(v), "unit": "score_1_5",
         "source": "checkin"}
        for m, v in (("mood", req.mood), ("stress", req.stress), ("sleep_quality", req.sleep_quality))
    ])
    insert_measurements(session, df, None)
    session.commit()
    session.refresh(row)
    return CheckinResponse(checkin=_checkin_record(row), emergency=emergency)


def alerts(session: Session, *, astronaut_id=None, severity=None, min_severity=None, system=None, source=None,
           metric=None, status="active", as_of=None) -> AlertListResponse:
    res = _service.analysis(session, as_of)
    evs = res.events
    if astronaut_id:
        evs = [e for e in evs if e.astronaut_id == astronaut_id]
    if severity:
        evs = [e for e in evs if e.severity in severity]
    if min_severity:
        evs = [e for e in evs if SEVERITY_RANK[e.severity] >= SEVERITY_RANK[min_severity]]
    if system:
        evs = [e for e in evs if e.system == system]
    if source:
        evs = [e for e in evs if e.source == source]
    if metric:
        evs = [e for e in evs if any(c.metric == metric for c in e.contributors)]
    if status != "all":
        evs = [e for e in evs if e.status == status]
    evs = sorted(evs, key=event_sort_key)
    return AlertListResponse(as_of=res.as_of, count=len(evs), events=_service.overlay(session, evs))


def find_event(session: Session, event_id: str, as_of: date | None = None) -> HealthEvent | None:
    for a in dict.fromkeys([as_of, None]):  # önce istenen gün, sonra güncel
        ev = _service.analysis(session, a).find_event(event_id)
        if ev is not None:
            return _service.overlay(session, [ev])[0]
    return None


def feedback(session: Session, event_id: str, req: FeedbackRequest) -> FeedbackResponse:
    row = AlertFeedback(event_id=event_id, verdict=req.verdict, comment=req.comment)
    session.add(row)
    session.commit()
    session.refresh(row)
    return FeedbackResponse(feedback_id=row.id, event_id=event_id, verdict=row.verdict, comment=row.comment,  # type: ignore[arg-type]
                            created_at=row.created_at)


def share(session: Session, event_id: str, req: ShareRequest) -> ShareResponse:
    row = session.get(AlertShare, event_id) or AlertShare(event_id=event_id)
    row.share_with_ground = req.share_with_ground
    row.updated_at = utcnow()
    session.add(row)
    session.commit()
    return ShareResponse(event_id=event_id, share_with_ground=row.share_with_ground, updated_at=row.updated_at)


def ingest(session: Session, filename: str, content: bytes, adapter: str | None, astronaut_id: str | None) -> IngestReport:
    report = ingest_bytes(session, filename, content, adapter, astronaut_id)
    _service.invalidate()
    return report


def ground_report(session: Session, as_of: date | None, days: int) -> GroundReport:
    res = _service.analysis(session, as_of)
    now = datetime.now(UTC)
    if res.as_of is None:
        return GroundReport(generated_at=now, as_of=None, period=None, crew=[], note="Veri yok.")
    start = res.as_of - timedelta(days=days - 1)
    end = _as_of_day_end(session, as_of)
    period_start = datetime.combine(start, datetime.min.time(), UTC)
    out = []
    for aid, a in res.astronauts.items():
        cks = session.execute(
            select(Checkin).where(Checkin.astronaut_id == aid, Checkin.share_with_ground.is_(True),
                                  Checkin.timestamp >= period_start, Checkin.timestamp < end)
            .order_by(Checkin.timestamp.desc())
        ).scalars()
        evs = [e for e in _service.overlay(session, [e for e in a.events if e.window.end >= start]) if e.share_with_ground]
        out.append(GroundReportMember(astronaut=a.info, status=a.overall.status, score=a.overall.score,
                                      shared_checkins=[_checkin_record(c) for c in cks], shared_events=evs))
    return GroundReport(
        generated_at=now, as_of=res.as_of, period=DateWindow(start=start, end=res.as_of), crew=out,
        note="Sadece astronotun share_with_ground=true işaretlediği check-in'ler ve olaylar dahildir; genel durum renkleri her zaman paylaşılır.",
    )


def astronaut_count(session: Session) -> int:
    return session.execute(select(func.count()).select_from(Astronaut)).scalar_one()
