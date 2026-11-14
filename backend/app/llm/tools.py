"""LLM tool'ları (OpenAI function calling formatı).

Tool'lar SADECE analiz motorunun hesapladığı değerleri döndürür; LLM sayıları buradan alır.
Yeni tool eklemek: Pydantic argüman modeli + handler yaz, TOOLS listesine ToolSpec ekle.
"""

import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import numpy as np
from pydantic import BaseModel, Field, ValidationError
from sqlmodel import Session

from app.analysis.catalog import load_catalog
from app.db import get_engine
from app.models.schemas import SEVERITY_RANK, Severity


def _default_session() -> Session:
    return Session(get_engine())


@dataclass
class ToolContext:
    astronaut_id: str  # sohbetin bağlamındaki astronot (argüman verilmezse bu kullanılır)
    as_of: date | None = None
    lang: str = "en"
    session_factory: Callable[[], Session] = field(default=_default_session)


@dataclass
class ToolResult:
    ok: bool
    data: dict[str, Any]
    error: str | None = None
    duration_ms: float = 0.0

    def to_message(self) -> str:
        payload = self.data if self.ok else {"error": self.error}
        return json.dumps(payload, ensure_ascii=False, default=str)


@dataclass
class ToolSpec:
    name: str
    description: str
    args_model: type[BaseModel]
    handler: Callable[[ToolContext, Session, Any], dict[str, Any]]
    schema_patch: Callable[[dict], None] | None = None

    def openai_schema(self) -> dict[str, Any]:
        params = self.args_model.model_json_schema()
        params.pop("title", None)
        for p in params.get("properties", {}).values():
            p.pop("title", None)
        if self.schema_patch:
            self.schema_patch(params)
        return {"type": "function", "function": {"name": self.name, "description": self.description, "parameters": params}}


# =============================================================================
# Argüman modelleri
# =============================================================================
class AstronautArgs(BaseModel):
    astronaut_id: str | None = Field(None, description="Astronaut id, e.g. AST-02. Defaults to the current user.")


class MetricArgs(AstronautArgs):
    metric: str = Field(description="Metric name from the catalog, e.g. sleep_duration")
    days: int = Field(14, ge=1, le=90, description="How many recent days to return")


class AlertsArgs(AstronautArgs):
    severity: Severity | None = Field(None, description="Minimum severity: info | warning | critical")


class CheckinsArgs(AstronautArgs):
    days: int = Field(7, ge=1, le=30)


class SearchDocsArgs(BaseModel):
    query: str = Field(description="What to look for in onboard reference documents")
    top_k: int = Field(4, ge=1, le=8)


# =============================================================================
# Yardımcılar
# =============================================================================
def _r(x: Any, nd: int) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return round(v, nd) if np.isfinite(v) else None


def _analysis(ctx: ToolContext, session: Session):
    from app.services.data import get_data_service

    return get_data_service().analysis(session, ctx.as_of)


def _astronaut(ctx: ToolContext, session: Session, aid: str | None):
    res = _analysis(ctx, session)
    aid = aid or ctx.astronaut_id
    a = res.astronauts.get(aid)
    if a is None:
        raise ValueError(f"unknown astronaut_id '{aid}'. Known: {sorted(res.astronauts)}")
    return res, a


def _event_brief(e) -> dict[str, Any]:
    return {"event_id": e.event_id, "severity": e.severity, "source": e.source, "system": e.system,
            "title": e.title, "description": e.description, "since": str(e.window.start)}


# =============================================================================
# Handler'lar
# =============================================================================
def get_health_summary(ctx: ToolContext, session: Session, args: AstronautArgs) -> dict[str, Any]:
    res, a = _astronaut(ctx, session, args.astronaut_id)
    cat = load_catalog()
    active = a.active_events
    flagged = {c.metric for e in active if e.severity != "info" for c in e.contributors}
    out_of_normal = []
    for metric in sorted(flagged):
        sf = a.features.get(metric)
        m = cat.get(metric)
        last = sf.last_valid() if sf else None
        if m is None or last is None:
            continue
        out_of_normal.append({
            "metric": metric, "display_name": m.label(ctx.lang), "unit": m.unit, "date": str(last.name.date()),
            "value": _r(last["value"], m.decimals + 1), "rolling_7d_mean": _r(last["roll7"], m.decimals + 1),
            "personal_baseline": _r(sf.baseline.mean, m.decimals + 1) if sf.baseline else None,
            "z7": _r(last["z7"], 2), "threshold_verified": m.threshold_verified,
        })
    mission = res.mission()
    return {
        "astronaut_id": a.info.id, "name": a.info.name, "as_of": str(res.as_of), "mission_day": mission.mission_day,
        "overall": a.overall.model_dump(mode="json"),
        "systems": [{"system": s.system, "status": s.status, "score": s.score} for s in a.systems],
        "active_alerts": [_event_brief(e) for e in active if e.severity != "info"][:8],
        "info_notes": [e.title for e in active if e.severity == "info"][:5],
        "out_of_normal_metrics": out_of_normal,
        "note": "All thresholds are placeholders (threshold_verified=false) pending NASA-STD-3001 validation.",
    }


def get_metric(ctx: ToolContext, session: Session, args: MetricArgs) -> dict[str, Any]:
    cat = load_catalog()
    m = cat.resolve(args.metric)
    if m is None:
        raise ValueError(f"unknown metric '{args.metric}'. Valid: {sorted(cat.metrics)}")
    res, a = _astronaut(ctx, session, args.astronaut_id)
    sf = a.features.get(m.name)
    base = {"astronaut_id": a.info.id, "metric": m.name, "display_name": m.label(ctx.lang), "unit": m.unit,
            "system": m.system, "as_of": str(res.as_of)}
    if sf is None or sf.last_valid() is None:
        return {**base, "error": "no data for this metric"}
    nd = m.decimals + 1
    f = sf.frame.iloc[-args.days:]
    last = sf.last_valid()
    t = m.thresholds
    return {
        **base,
        "latest": {"date": str(last.name.date()), "value": _r(last["value"], nd), "rolling_7d_mean": _r(last["roll7"], nd),
                   "z7": _r(last["z7"], 2), "slope_7d_per_day": _r(last["slope7"], nd + 1)},
        "personal_baseline": ({"mean": _r(sf.baseline.mean, nd), "std": _r(sf.baseline.std, nd + 1),
                               "from": str(sf.baseline.start), "to": str(sf.baseline.end)} if sf.baseline else None),
        "normal_range": m.normal_range.model_dump() if m.normal_range else None,
        "thresholds": ({"warning": t.warning.model_dump() if t.warning else None,
                        "critical": t.critical.model_dump() if t.critical else None,
                        "threshold_verified": t.verified} if t else None),
        "daily": [{"date": str(d.date()), "value": _r(v, nd)} for d, v in f["value"].items() if np.isfinite(v)],
        "active_alerts": [_event_brief(e) for e in a.active_events if any(c.metric == m.name for c in e.contributors)],
    }


def get_alerts(ctx: ToolContext, session: Session, args: AlertsArgs) -> dict[str, Any]:
    _, a = _astronaut(ctx, session, args.astronaut_id)
    min_rank = SEVERITY_RANK[args.severity] if args.severity else 1
    evs = [e for e in a.active_events if SEVERITY_RANK[e.severity] >= min_rank]
    return {"astronaut_id": a.info.id, "count": len(evs), "alerts": [
        {**_event_brief(e), "score": e.score,
         "contributors": [{"metric": c.metric, "value": c.value, "baseline": c.baseline, "z": c.z} for c in e.contributors]}
        for e in evs[:12]
    ]}


def get_radiation_dose(ctx: ToolContext, session: Session, args: AstronautArgs) -> dict[str, Any]:
    res, a = _astronaut(ctx, session, args.astronaut_id)
    cat = load_catalog()
    out: dict[str, Any] = {"astronaut_id": a.info.id, "as_of": str(res.as_of), "unit": "mSv"}
    daily = a.features.get("radiation_daily_dose")
    cum = a.features.get("radiation_cumulative")
    if daily is not None and daily.last_valid() is not None:
        last = daily.last_valid()
        out["daily_latest"] = {"date": str(last.name.date()), "value": _r(last["value"], 3)}
        out["last_7_days_total"] = _r(daily.frame["value"].iloc[-7:].sum(min_count=1), 2)
    if cum is not None and cum.last_valid() is not None:
        last = cum.last_valid()
        out["cumulative"] = {"date": str(last.name.date()), "value": _r(last["value"], 2)}
    out["thresholds"] = {
        name: ({"warning": cat.metrics[name].thresholds.warning.model_dump() if cat.metrics[name].thresholds.warning else None,
                "critical": cat.metrics[name].thresholds.critical.model_dump() if cat.metrics[name].thresholds.critical else None,
                "threshold_verified": cat.metrics[name].thresholds.verified} if cat.metrics[name].thresholds else None)
        for name in ("radiation_daily_dose", "radiation_cumulative")
    }
    out["active_alerts"] = [_event_brief(e) for e in a.active_events if e.system == "radiation"]
    return out


def get_checkins(ctx: ToolContext, session: Session, args: CheckinsArgs) -> dict[str, Any]:
    from app.services.data import checkins

    aid = args.astronaut_id or ctx.astronaut_id
    _astronaut(ctx, session, aid)
    rows = checkins(session, aid, args.days, ctx.as_of).checkins
    own = aid == ctx.astronaut_id  # serbest metin notları sadece astronotun kendisine
    return {"astronaut_id": aid, "scale": "1-5 (stress: 5 = very high)", "checkins": [
        {"date": str(c.timestamp.date()), "mood": c.mood, "stress": c.stress, "sleep_quality": c.sleep_quality,
         **({"note": c.note} if own and c.note else {})}
        for c in rows
    ], **({} if own else {"note": "free-text notes are private to the astronaut"})}


def search_docs(ctx: ToolContext, session: Session, args: SearchDocsArgs) -> dict[str, Any]:
    try:
        from app.llm.rag import search
    except ImportError:
        return {"query": args.query, "results": [], "note": "document index not available"}
    hits = search(args.query, args.top_k)
    return {"query": args.query, "results": [h.model_dump() for h in hits],
            **({} if hits else {"note": "no matching onboard document found"})}


def _metric_enum(params: dict) -> None:
    params["properties"]["metric"]["enum"] = sorted(load_catalog().metrics)


TOOLS: list[ToolSpec] = [
    ToolSpec("get_health_summary", "Overall health status / daily report / status report of an astronaut: overall and system scores, active alerts, "
             "metrics outside the personal normal. Use this first for any general 'how am I' or report question.",
             AstronautArgs, get_health_summary),
    ToolSpec("get_metric", "Recent daily values of one metric with personal baseline, thresholds and related alerts.",
             MetricArgs, get_metric, _metric_enum),
    ToolSpec("get_alerts", "Active rule-based alerts of an astronaut (optionally filtered by minimum severity).",
             AlertsArgs, get_alerts),
    ToolSpec("get_radiation_dose", "Latest daily, 7-day and cumulative radiation dose with thresholds.", AstronautArgs,
             get_radiation_dose),
    ToolSpec("get_checkins", "Subjective check-in questionnaire answers only (mood, stress, sleep quality 1-5 and notes). Not a health "
             "report: use it only when the user asks about mood, stress, feelings or their check-in.", CheckinsArgs,
             get_checkins),
    ToolSpec("search_docs", "Search onboard reference documents (NASA standards, procedures). Returns file/section references.",
             SearchDocsArgs, search_docs),
]


class ToolRegistry:
    def __init__(self, specs: list[ToolSpec] | None = None) -> None:
        self.specs = {s.name: s for s in (specs if specs is not None else TOOLS)}

    @property
    def names(self) -> set[str]:
        return set(self.specs)

    def openai_tools(self) -> list[dict[str, Any]]:
        return [s.openai_schema() for s in self.specs.values()]

    def execute(self, ctx: ToolContext, name: str, arguments: str | dict[str, Any]) -> ToolResult:
        t0 = time.perf_counter()
        spec = self.specs.get(name)
        if spec is None:
            return ToolResult(False, {}, f"unknown tool '{name}'. Available: {sorted(self.specs)}", 0.0)
        try:
            raw = json.loads(arguments) if isinstance(arguments, str) and arguments.strip() else (arguments or {})
            if not isinstance(raw, dict):
                raise ValueError("arguments must be a JSON object")
            args = spec.args_model.model_validate(raw)
            with ctx.session_factory() as session:
                data = spec.handler(ctx, session, args)
            return ToolResult(True, data, None, (time.perf_counter() - t0) * 1000)
        except (ValidationError, ValueError, json.JSONDecodeError) as e:
            return ToolResult(False, {}, f"invalid call: {e}", (time.perf_counter() - t0) * 1000)
        except Exception as e:  # noqa: BLE001 — tool hatası sohbeti düşürmemeli
            return ToolResult(False, {}, f"{type(e).__name__}: {e}", (time.perf_counter() - t0) * 1000)
