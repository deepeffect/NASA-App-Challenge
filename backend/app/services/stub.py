"""(a) ADIMI — SÖZLEŞME STUB'LARI.

Arayüz ekibi gerçek backend hazır olmadan çalışabilsin diye ŞEMAYA UYGUN SAHTE veri döner.
Tüm olay türleri (rule / anomaly / changepoint / forecast) ve tüm SSE olayları burada örneklenir.
`feat/backend-core` branch'inde gerçek servislerle değiştirilir.
"""

import asyncio
import hashlib
import json
import random
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, time, timedelta

from pydantic import BaseModel

from app.analysis.catalog import load_catalog
from app.models.schemas import (
    SEVERITY_RANK,
    AlertExplanation,
    AlertListResponse,
    AstronautInfo,
    AstronautSummary,
    Baseline,
    BriefingResponse,
    CheckinListResponse,
    CheckinRecord,
    CheckinRequest,
    CheckinResponse,
    ChatRequest,
    Contributor,
    CrewMember,
    CrewResponse,
    DailyBriefing,
    DailyPoint,
    DateWindow,
    EventCounts,
    ExplainRequest,
    ExplainResponse,
    FeedbackRequest,
    FeedbackResponse,
    Forecast,
    ForecastPoint,
    GroundReport,
    GroundReportMember,
    HealthEvent,
    IngestReport,
    MetricSeriesResponse,
    MetricSnapshot,
    MissionInfo,
    OverallStatus,
    RawPoint,
    ScorePenalty,
    ShareRequest,
    ShareResponse,
    SSEDone,
    SSEMeta,
    SSEToken,
    SSEToolCall,
    SSEToolResult,
    SystemScore,
)
from app.safety.emergency import detect_emergency

MISSION_START = date(2026, 5, 19)
MISSION_DAYS = 180
LATEST = MISSION_START + timedelta(days=MISSION_DAYS - 1)  # 2026-11-14

ASTRONAUTS = [
    AstronautInfo(id="AST-01", name="Astronot 1", role="Komutan"),
    AstronautInfo(id="AST-02", name="Astronot 2", role="Uçuş mühendisi"),
    AstronautInfo(id="AST-03", name="Astronot 3", role="Mürettebat sağlık sorumlusu (CMO)"),
    AstronautInfo(id="AST-04", name="Astronot 4", role="Görev uzmanı"),
]
_IDS = {a.id for a in ASTRONAUTS}

_BASE = {
    "resting_hr": (60, 2.0), "heart_rate": (72, 6.0), "hrv_rmssd": (55, 5.0), "bp_systolic": (117, 4.0),
    "bp_diastolic": (75, 3.0), "spo2": (97.6, 0.4), "body_temp": (36.9, 0.15), "body_mass": (74, 0.3),
    "exercise_minutes": (130, 12.0), "sleep_duration": (7.3, 0.35), "sleep_quality": (3.8, 0.5),
    "mood": (3.9, 0.5), "stress": (2.0, 0.5), "reaction_time": (265, 12.0), "radiation_daily_dose": (1.8, 0.08),
}
_SCALES = {"sleep_quality", "mood", "stress"}
# metric: (başlangıç görev günü, rampa gün, toplam değişim) — sadece AST-02
_SCENARIO = {
    "sleep_duration": (150, 5, -2.2), "sleep_quality": (150, 5, -1.6), "stress": (153, 4, 2.0),
    "mood": (153, 4, -1.5), "hrv_rmssd": (153, 7, -16), "reaction_time": (152, 6, 45),
    "resting_hr": (156, 6, 11), "heart_rate": (156, 6, 11), "exercise_minutes": (165, 6, -35),
}

_FEEDBACK: dict[str, str] = {}
_SHARED: dict[str, bool] = {}
_CHECKINS: list[CheckinRecord] = []


def _day(n: int) -> date:
    """Görev günü (1'den başlar) → tarih."""
    return MISSION_START + timedelta(days=n - 1)


def clamp_as_of(as_of: date | None) -> date:
    if as_of is None:
        return LATEST
    return min(max(as_of, MISSION_START), LATEST)


def mission_info(as_of: date | None) -> MissionInfo:
    a = clamp_as_of(as_of)
    return MissionInfo(
        start_date=MISSION_START, latest_date=LATEST, as_of=a,
        mission_day=(a - MISSION_START).days + 1, total_days=MISSION_DAYS,
    )


def astronaut(aid: str) -> AstronautInfo | None:
    return next((a for a in ASTRONAUTS if a.id == aid), None)


def _value(aid: str, metric: str, d: date) -> float:
    n = (d - MISSION_START).days + 1
    if metric == "radiation_cumulative":
        return round(12.0 + 1.8 * n, 1)
    mean, std = _BASE[metric]
    v = mean + random.Random(f"{aid}|{metric}|{n}").gauss(0, std)
    if aid == "AST-02" and metric in _SCENARIO:
        start, ramp, delta = _SCENARIO[metric]
        if n >= start:
            v += delta * min(1.0, (n - start + 1) / ramp)
    if metric in _SCALES:
        v = float(min(5, max(1, round(v))))
    return round(v, 2)


# ----------------------------------------------------------------------------- olaylar
def _eid(*parts: object) -> str:
    return "evt_" + hashlib.sha1("|".join(map(str, parts)).encode()).hexdigest()[:12]


def _contrib(aid: str, metric: str, d: date, weight: float = 1.0) -> Contributor:
    cat = load_catalog()
    mean = _BASE.get(metric, (0, 1))[0]
    std = _BASE.get(metric, (0, 1))[1]
    val = _value(aid, metric, d)
    return Contributor(
        metric=metric, value=val, baseline=mean, z=round((val - mean) / std, 2), weight=weight,
        threshold_verified=cat.metrics[metric].threshold_verified if cat.metrics[metric].has_thresholds else None,
    )


def _events_for(aid: str, as_of: date) -> list[HealthEvent]:
    out: list[HealthEvent] = []

    def ev(source, system, severity, score, title, start_day, contributors, detector, desc,
           end: date | None = None, **kw) -> None:
        start = _day(start_day)
        if start > as_of:
            return
        end_d = min(end or as_of, as_of)
        status = "active" if (as_of - end_d).days <= 2 else "resolved"
        eid = _eid(aid, source, detector, contributors[0].metric, start)
        out.append(HealthEvent(
            event_id=eid, astronaut_id=aid, detected_at=datetime.combine(start, time(8, 0), UTC),
            source=source, system=system, severity=severity, score=score, title=title,
            window=DateWindow(start=start, end=end_d), contributors=contributors, detector=detector,
            description=desc, status=status, share_with_ground=_SHARED.get(eid, False),
            feedback=_FEEDBACK.get(eid), **kw,
        ))

    if aid == "AST-02":
        ev("rule", "sleep", "warning", 0.7, "Uyku süresi alt uyarı eşiğinin altında", 152,
           [_contrib(aid, "sleep_duration", as_of)], "rule.threshold",
           "Uyku süresi 6,0 sa placeholder eşiğinin altına indi.")
        ev("rule", "sleep", "critical", 0.92, "Uyku süresi kişisel normalin altında", 153,
           [_contrib(aid, "sleep_duration", as_of)], "rule.baseline_deviation",
           "Son 7 gün ortalaması kişisel baseline'ın belirgin altında.")
        ev("rule", "behavioral", "warning", 0.71, "Davranışsal sağlık: birden fazla göstergede eşzamanlı değişim", 156,
           [_contrib(aid, "stress", as_of, 0.45), _contrib(aid, "mood", as_of, 0.35),
            _contrib(aid, "reaction_time", as_of, 0.20)], "rule.system_pattern",
           "Stres, ruh hali ve reaksiyon süresi aynı dönemde kötüleşti.")
        ev("anomaly", "cardiovascular", "warning", 0.66, "Kardiyovasküler göstergelerde olağandışı örüntü", 158,
           [_contrib(aid, "resting_hr", as_of, 0.6), _contrib(aid, "hrv_rmssd", as_of, 0.4)],
           "ml.example_anomaly", "Örnek ML olayı (stub).")
        ev("changepoint", "sleep", "warning", 0.81, "Uyku süresinde kalıcı düşüş", 155,
           [_contrib(aid, "sleep_duration", as_of)], "ml.example_changepoint",
           "Uyku süresi serisinde ortalama değişim noktası.", changepoint_date=_day(150))
        if as_of >= _day(158):
            last = _value(aid, "resting_hr", as_of)
            ev("forecast", "cardiovascular", "warning", 0.58, "İstirahat nabzında artış eğilimi sürebilir", 158,
               [_contrib(aid, "resting_hr", as_of)], "ml.example_forecast",
               "Doğrusal tahmin: önümüzdeki 7 günde artış sürebilir.",
               forecast=Forecast(metric="resting_hr", method="linear", horizon_days=7, points=[
                   ForecastPoint(date=as_of + timedelta(days=i), value=round(last + 0.8 * i, 1),
                                 lower=round(last + 0.8 * i - 1.5 - 0.3 * i, 1),
                                 upper=round(last + 0.8 * i + 1.5 + 0.3 * i, 1)) for i in range(1, 8)]))
        ev("rule", "musculoskeletal", "info", 0.42, "Egzersiz süresi: sürekli düşüş eğilimi", 166,
           [_contrib(aid, "exercise_minutes", as_of)], "rule.trend", "Egzersiz süresi son günlerde azalıyor.")
    if aid == "AST-04":
        ev("rule", "immune", "info", 0.4, "Vücut ısısı kişisel normalin üstünde", 60,
           [_contrib(aid, "body_temp", _day(62))], "rule.baseline_deviation",
           "Kısa süreli hafif yükselme.", end=_day(63))
    return out


def all_events(as_of: date | None) -> list[HealthEvent]:
    a = clamp_as_of(as_of)
    return [e for x in ASTRONAUTS for e in _events_for(x.id, a)]


def find_event(event_id: str, as_of: date | None = None) -> HealthEvent | None:
    for a in (clamp_as_of(as_of), LATEST):
        for e in all_events(a):
            if e.event_id == event_id:
                return e
    return None


# ----------------------------------------------------------------------------- skorlar
_PEN = {"critical": 45, "warning": 20, "info": 3}


def _scores(aid: str, as_of: date) -> tuple[list[SystemScore], OverallStatus, list[HealthEvent]]:
    cat = load_catalog()
    active = [e for e in _events_for(aid, as_of) if e.status == "active"]
    systems: list[SystemScore] = []
    for s in cat.system_infos():
        evs = [e for e in active if e.system == s.id and e.detector != "rule.system_pattern"]
        per_metric: dict[str, HealthEvent] = {}
        for e in evs:
            m = e.contributors[0].metric
            if m not in per_metric or _PEN[e.severity] > _PEN[per_metric[m].severity]:
                per_metric[m] = e
        pens = [ScorePenalty(event_id=e.event_id, title=e.title, metric=m, severity=e.severity, penalty=_PEN[e.severity])
                for m, e in per_metric.items()]
        score = max(0.0, 100.0 - sum(p.penalty for p in pens))
        worst = max((SEVERITY_RANK[e.severity] for e in active if e.system == s.id), default=0)
        status = "red" if worst == 3 or score < 50 else "yellow" if worst == 2 or score < 80 else "green"
        systems.append(SystemScore(system=s.id, display_name=s.display_name, score=score, status=status,
                                   metrics=s.metrics, penalties=pens))
    worst_sys = min(systems, key=lambda x: x.score or 0)
    rank = {"red": 3, "yellow": 2, "green": 1, "unknown": 0}
    overall = max((x.status for x in systems), key=lambda st: rank[st])
    return systems, OverallStatus(status=overall, score=worst_sys.score,
                                  worst_system=worst_sys.system if worst_sys.status != "green" else None), active


# ----------------------------------------------------------------------------- endpoint'ler
def crew(as_of: date | None) -> CrewResponse:
    a = clamp_as_of(as_of)
    members = []
    for x in ASTRONAUTS:
        systems, overall, active = _scores(x.id, a)
        counts = EventCounts(**{sev: sum(1 for e in active if e.severity == sev) for sev in ("critical", "warning", "info")})
        attention = [s.system for s in sorted(systems, key=lambda s: s.score or 0) if s.status != "green"]
        members.append(CrewMember(**x.model_dump(), status=overall.status, score=overall.score, active_events=counts,
                                  attention_systems=attention, last_measurement_at=datetime.combine(a, time(23, 0), UTC)))
    return CrewResponse(mission=mission_info(a), astronauts=members)


def summary(aid: str, as_of: date | None) -> AstronautSummary:
    a = clamp_as_of(as_of)
    cat = load_catalog()
    systems, overall, active = _scores(aid, a)
    alert_metrics = {c.metric for e in active if e.severity != "info" for c in e.contributors}
    watch_metrics = {c.metric for e in active if e.severity == "info" for c in e.contributors}
    latest = []
    for m in cat.metrics.values():
        if m.name not in _BASE and m.name != "radiation_cumulative":
            continue
        v = _value(aid, m.name, a)
        mean, std = _BASE.get(m.name, (v, 1.0))
        latest.append(MetricSnapshot(
            metric=m.name, display_name=m.label(), unit=m.unit, system=m.system, date=a, value=v,
            baseline_mean=mean, baseline_std=std, z=round((v - mean) / std, 2), z7=round((v - mean) / std * 0.8, 2),
            slope7=0.0, threshold_verified=m.threshold_verified,
            state="alert" if m.name in alert_metrics else "watch" if m.name in watch_metrics else "normal",
        ))
    return AstronautSummary(astronaut=astronaut(aid), mission=mission_info(a), overall=overall, systems=systems,
                            latest=latest, active_events=active, last_measurement_at=datetime.combine(a, time(23, 0), UTC))


def metric_series(aid: str, metric: str, days: int, as_of: date | None, resolution: str) -> MetricSeriesResponse:
    a = clamp_as_of(as_of)
    m = load_catalog().metrics[metric]
    start = max(MISSION_START, a - timedelta(days=days - 1))
    dates = [start + timedelta(days=i) for i in range((a - start).days + 1)]
    base_vals = [_value(aid, metric, MISSION_START + timedelta(days=i)) for i in range(14)]
    bmean = sum(base_vals) / len(base_vals)
    bstd = max((sum((v - bmean) ** 2 for v in base_vals) / (len(base_vals) - 1)) ** 0.5, m.min_std)
    daily, window = [], []
    for d in dates:
        v = _value(aid, metric, d)
        window = (window + [v])[-7:]
        r7 = sum(window) / len(window)
        daily.append(DailyPoint(date=d, value=v, min=round(v - bstd * 0.3, 2), max=round(v + bstd * 0.3, 2), n=1,
                                roll7=round(r7, 2), z7=round((r7 - bmean) / bstd, 2)))
    raw: list[RawPoint] = []
    if resolution == "raw":
        hours = range(24) if m.frequency == "hourly" else [7]
        for p in daily:
            for h in hours:
                jitter = random.Random(f"{aid}{metric}{p.date}{h}").gauss(0, bstd * 0.5)
                raw.append(RawPoint(timestamp=datetime.combine(p.date, time(h), UTC), value=round(p.value + jitter, 2),
                                    source="stub"))
    events = [e for e in _events_for(aid, a) if any(c.metric == metric for c in e.contributors)]
    return MetricSeriesResponse(
        astronaut_id=aid, metric=m.to_info(), as_of=a, resolution=resolution,  # type: ignore[arg-type]
        baseline=Baseline(mean=round(bmean, 2), std=round(bstd, 2), n_days=14, start=MISSION_START, end=_day(14)),
        daily=daily, raw=raw, events=events,
    )


def checkins(aid: str, days: int, as_of: date | None) -> CheckinListResponse:
    a = clamp_as_of(as_of)
    notes = [None, None, "Yoğun bir gündü.", None, "Deney planı yetişti.", None]
    if aid == "AST-02":
        notes += ["Uyuyamıyorum, kafam çok dolu."] * 3
    out = []
    for i in range(days):
        d = a - timedelta(days=i)
        if d < MISSION_START:
            break
        rnd = random.Random(f"ck{aid}{d}")
        note = rnd.choice(notes) if (aid != "AST-02" or (d - MISSION_START).days < 150) else rnd.choice(notes[-3:] + [None])
        out.append(CheckinRecord(
            id=int(hashlib.md5(f"{aid}{d}".encode()).hexdigest()[:6], 16), astronaut_id=aid,
            timestamp=datetime.combine(d, time(21, 0), UTC), mood=int(_value(aid, "mood", d)),
            stress=int(_value(aid, "stress", d)), sleep_quality=int(_value(aid, "sleep_quality", d)),
            note=note, share_with_ground=rnd.random() < 0.25, emergency=False,
        ))
    out = [c for c in _CHECKINS if c.astronaut_id == aid] + out
    return CheckinListResponse(astronaut_id=aid, checkins=out)


def alerts(*, astronaut_id=None, severity=None, min_severity=None, system=None, source=None, metric=None,
           status="active", as_of=None) -> AlertListResponse:
    a = clamp_as_of(as_of)
    evs = all_events(a)
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
    evs.sort(key=lambda e: (-SEVERITY_RANK[e.severity], e.window.start), reverse=False)
    return AlertListResponse(as_of=a, count=len(evs), events=evs)


def explain(event: HealthEvent, req: ExplainRequest) -> ExplainResponse:
    tr = req.lang == "tr"
    exp = AlertExplanation(
        summary=(f"[STUB] {event.title}. " + (event.description or "")) if tr else f"[STUB] {event.title}.",
        likely_factors=["Uyku programındaki değişiklik veya iş yükü artışı", "Eşzamanlı stres artışı"] if tr
        else ["Change in sleep schedule or workload", "Concurrent stress increase"],
        recommended_actions=["Mürettebat sağlık sorumlusu (CMO) ile değerlendirin", "Göstergeyi 3 gün daha izleyin"] if tr
        else ["Review with the crew medical officer (CMO)", "Keep monitoring for 3 more days"],
        escalate_to_ground=event.severity == "critical",
        sources=[f"metric:{c.metric}" for c in event.contributors] + [f"event:{event.event_id}"],
        uncertainty="Bu bir stub cevabıdır; gerçek LLM bağlı değil." if tr else "Stub response; no real LLM.",
    )
    return ExplainResponse(event_id=event.event_id, event=event, explanation=exp, generated_by="mock", model="mock",
                           cached=False, created_at=datetime.now(UTC))


def feedback(event_id: str, req: FeedbackRequest) -> FeedbackResponse:
    _FEEDBACK[event_id] = req.verdict
    return FeedbackResponse(feedback_id=len(_FEEDBACK), event_id=event_id, verdict=req.verdict, comment=req.comment,
                            created_at=datetime.now(UTC))


def share(event_id: str, req: ShareRequest) -> ShareResponse:
    _SHARED[event_id] = req.share_with_ground
    return ShareResponse(event_id=event_id, share_with_ground=req.share_with_ground, updated_at=datetime.now(UTC))


def briefing(aid: str, as_of: date | None, lang: str) -> BriefingResponse:
    a = clamp_as_of(as_of)
    _, overall, active = _scores(aid, a)
    concerns = [e.title for e in active if e.severity != "info"]
    info = [e for e in active if e.severity == "info"]
    b = DailyBriefing(
        summary=f"[STUB] Görev günü {mission_info(a).mission_day}: genel durum {overall.status}.",
        highlights=["Radyasyon ve bağışıklık göstergeleri kişisel normal aralıkta."],
        concerns=concerns,
        recommended_actions=["Uyku programını CMO ile gözden geçirin."] if concerns else ["Rutine devam edin."],
        info_notes=[e.title for e in info],
        escalate_to_ground=any(e.severity == "critical" for e in active),
        sources=[f"event:{e.event_id}" for e in active],
        uncertainty="Stub cevabı.",
    )
    return BriefingResponse(astronaut_id=aid, as_of=a, lang=lang, briefing=b, generated_by="mock", model="mock",  # type: ignore[arg-type]
                            cached=False, info_events=info, created_at=datetime.now(UTC))


def checkin(req: CheckinRequest) -> CheckinResponse:
    emergency = detect_emergency(req.note, req.lang)
    rec = CheckinRecord(id=len(_CHECKINS) + 1, astronaut_id=req.astronaut_id,
                        timestamp=req.timestamp or datetime.now(UTC), mood=req.mood, stress=req.stress,
                        sleep_quality=req.sleep_quality, note=req.note, share_with_ground=req.share_with_ground,
                        emergency=emergency is not None)
    _CHECKINS.insert(0, rec)
    return CheckinResponse(checkin=rec, emergency=emergency)


def ingest(filename: str, content: bytes) -> IngestReport:
    lines = [ln for ln in content.decode("utf-8", errors="replace").splitlines() if ln.strip()]
    n = max(0, len(lines) - 1)
    return IngestReport(batch_id=None, filename=filename, adapter="stub", rows_total=n, rows_accepted=0,
                        rows_duplicate=0, rows_rejected=0, warnings=["STUB: veri kaydedilmedi"])


def ground_report(as_of: date | None, days: int) -> GroundReport:
    a = clamp_as_of(as_of)
    start = max(MISSION_START, a - timedelta(days=days - 1))
    crew_out = []
    for x in ASTRONAUTS:
        _, overall, _ = _scores(x.id, a)
        cks = [c for c in checkins(x.id, days, a).checkins if c.share_with_ground]
        evs = [e for e in _events_for(x.id, a) if e.share_with_ground]
        crew_out.append(GroundReportMember(astronaut=x, status=overall.status, score=overall.score,
                                           shared_checkins=cks, shared_events=evs))
    return GroundReport(generated_at=datetime.now(UTC), as_of=a, period=DateWindow(start=start, end=a), crew=crew_out,
                        note="Sadece share_with_ground=true olan check-in'ler ve olaylar dahildir.")


async def chat_stream(req: ChatRequest) -> AsyncIterator[tuple[str, BaseModel]]:
    """Stub SSE akışı: tüm olay tiplerini örnekler."""
    last = req.messages[-1].content
    lang = req.lang or "tr"
    yield "meta", SSEMeta(request_id=uuid.uuid4().hex[:12], provider="mock", model="stub", tool_mode="native",
                          astronaut_id=req.astronaut_id, as_of=clamp_as_of(req.as_of))
    em = detect_emergency(last, lang)
    if em:
        yield "emergency", em
    call_id = "call_" + uuid.uuid4().hex[:8]
    args = {"astronaut_id": req.astronaut_id}
    yield "tool_call", SSEToolCall(id=call_id, name="get_health_summary", arguments=args)
    await asyncio.sleep(0.3)
    s = summary(req.astronaut_id, req.as_of)
    preview = json.dumps({"overall": s.overall.model_dump(), "active_events": len(s.active_events)}, ensure_ascii=False)
    yield "tool_result", SSEToolResult(id=call_id, name="get_health_summary", ok=True, duration_ms=300.0, preview=preview)
    text = (f"[STUB] {s.astronaut.name} için genel durum: {s.overall.status}. "
            f"Aktif olay sayısı: {len(s.active_events)}. Bu cevap stub servisten geliyor.")
    for word in text.split(" "):
        await asyncio.sleep(0.02)
        yield "token", SSEToken(text=word + " ")
    yield "done", SSEDone(message=text, finish_reason="stop", steps=2, tool_calls=1)


def known_astronaut(aid: str) -> bool:
    return aid in _IDS
