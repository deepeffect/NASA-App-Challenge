"""LLM orkestrasyonu: açıklama (explain), günlük brifing ve sohbet (SSE).

Explain/briefing akışı (agent loop YOK — 14B model için daha güvenilir):
  1) Bağlam deterministik toplanır (olay, seriler, skorlar, check-in notları, belgeler)
  2) Tek LLM çağrısı, response_format=json_schema → Pydantic doğrulama → 1 retry
  3) Olmazsa / LLM yoksa → kural tabanlı şablon (generated_by=template_fallback). Endpoint asla LLM yüzünden düşmez.
  4) Güvenlik kuralları deterministik uygulanır (critical → escalate_to_ground=true)
  5) Sonuç cache'lenir (olay durumu değişince anahtar değişir)

Sohbet: acil belirti taraması LLM'den ÖNCE yapılır; LLM çevrim dışıysa kural tabanlı kısa özet akıtılır.
"""

import hashlib
import json
import re
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime
from typing import Any

import anyio
import numpy as np
from pydantic import BaseModel
from sqlmodel import Session

from app.analysis.catalog import load_catalog
from app.config import get_settings
from app.llm import templates
from app.llm.agent import Agent
from app.llm.client import LLMClient, get_llm_client
from app.llm.prompts import prompt
from app.llm.structured import generate_structured
from app.llm.tools import ToolContext, ToolRegistry
from app.llm.types import LLMError
from app.models.schemas import (
    AlertExplanation,
    BriefingResponse,
    ChatRequest,
    DailyBriefing,
    DocRef,
    ExplainRequest,
    ExplainResponse,
    HealthEvent,
    SSEDone,
    SSEError,
    SSEMeta,
    SSEToken,
)
from app.models.tables import LLMCache, utcnow
from app.safety.emergency import detect_emergency
from app.safety.grounding import find_ungrounded_numbers
from app.services.data import checkins as list_checkins
from app.services.data import get_data_service

LANG_NAME = {"en": "English"}
# Bağlam/şablon mantığı değişince artır → eski LLM cache kayıtları kullanılmaz
CACHE_VERSION = 2
HISTORY_LIMIT = 12

_client: tuple[tuple, LLMClient] | None = None
_registry = ToolRegistry()


def get_client() -> LLMClient:
    """İstemci önbelleklenir: auto modda 'tools desteklenmiyor' kararı istekler arasında kalıcı olsun."""
    global _client
    s = get_settings()
    key = (s.llm_provider, s.llm_base_url, s.llm_model, s.llm_tool_mode)
    if _client is None or _client[0] != key:
        _client = (key, get_llm_client(s))
    return _client[1]


def _generated_by(client: LLMClient) -> str:
    return "mock" if client.provider == "mock" else "llm"


def _r(x: Any, nd: int) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return round(v, nd) if np.isfinite(v) else None


def _search_docs(query: str, k: int = 3) -> list[DocRef]:
    try:
        from app.llm.rag import search
    except ImportError:
        return []
    try:
        return search(query, k)
    except Exception:  # noqa: BLE001 — RAG hatası açıklamayı engellemez
        return []


# ----------------------------------------------------------------------------- cache
def _cache_get(session: Session, key: str) -> dict | None:
    row = session.get(LLMCache, key)
    return row.payload if row else None


def _cache_put(session: Session, key: str, kind: str, payload: dict) -> None:
    row = session.get(LLMCache, key) or LLMCache(key=key, kind=kind)
    row.payload = payload
    row.created_at = utcnow()
    session.add(row)
    session.commit()


def _text_fields(obj: BaseModel) -> str:
    vals = []
    for v in obj.model_dump().values():
        if isinstance(v, str):
            vals.append(v)
        elif isinstance(v, list):
            vals += [x for x in v if isinstance(x, str)]
    return "\n".join(vals)


# ============================================================================= explain
def build_explain_context(session: Session, event: HealthEvent, as_of: date | None) -> tuple[dict[str, Any], list[DocRef]]:
    res = get_data_service().analysis(session, as_of)
    a = res.astronauts[event.astronaut_id]
    cat = load_catalog()
    metrics: dict[str, Any] = {}
    for c in event.contributors:
        m = cat.get(c.metric)
        if m is None:
            continue
        sf = a.features.get(c.metric)
        nd = m.decimals + 1
        recent = []
        if sf is not None:
            for d, v in sf.frame["value"].iloc[-14:].items():
                if np.isfinite(v):
                    recent.append({"date": str(d.date()), "value": _r(v, nd)})
        metrics[c.metric] = {
            "display_name": m.label(), "display_name_en": m.label(), "unit": m.unit, "decimals": m.decimals,
            "bad_direction": m.bad_direction, "normal_range": m.normal_range.model_dump() if m.normal_range else None,
            "thresholds": m.thresholds.model_dump() if m.thresholds else None, "threshold_verified": m.threshold_verified,
            "personal_baseline": ({"mean": _r(sf.baseline.mean, nd), "std": _r(sf.baseline.std, nd + 1),
                                   "n_days": sf.baseline.n_days} if sf is not None and sf.baseline else None),
            "recent_daily": recent,
        }
    own_metrics = {c.metric for c in event.contributors}
    rank = {"info": 1, "warning": 2, "critical": 3}
    by_metric: dict[str, dict[str, Any]] = {}  # metrik başına en ciddi olay (sapma + trend tekrarını önler)
    for e in a.active_events:
        metric = e.contributors[0].metric
        if (e.event_id == event.event_id or e.severity == "info" or metric in own_metrics or len(e.contributors) != 1):
            continue
        if metric not in by_metric or rank[e.severity] > rank[by_metric[metric]["severity"]]:
            by_metric[metric] = {"metric": metric, "severity": e.severity, "title": e.title, "system": e.system}
    related = sorted(by_metric.values(), key=lambda r: -rank[r["severity"]])[:6]
    for r in related:  # şablon ve model ilgili metriklerin okunur adlarına ihtiyaç duyar
        m = cat.get(r["metric"])
        if m:
            metrics.setdefault(r["metric"], {"display_name": m.label(), "display_name_en": m.label(),
                                             "unit": m.unit, "decimals": m.decimals, "related_only": True})
    notes = [c.note for c in list_checkins(session, event.astronaut_id, 5, as_of).checkins if c.note][:3]
    system = next((s for s in a.systems if s.system == event.system), None)
    docs = _search_docs(" ".join([event.title, *[cat.metrics[m].label() for m in own_metrics if m in cat.metrics]]))
    ctx = {
        "astronaut": a.info.model_dump(),
        "as_of": str(res.as_of),
        "mission_day": res.mission().mission_day,
        "event": event.model_dump(mode="json", exclude={"feedback", "share_with_ground"}),
        "metrics": metrics,
        "system_status": system.model_dump(mode="json", exclude={"metrics"}) if system else None,
        "related_active_events": related,
        "recent_checkin_notes": notes,
        "docs": [d.model_dump() for d in docs],
    }
    return ctx, docs


async def explain(session: Session, event: HealthEvent, req: ExplainRequest) -> ExplainResponse:
    client = get_client()
    state = f"v{CACHE_VERSION}|{event.event_id}|{event.window.end}|{event.severity}|{req.lang}|{client.provider}|{client.model}"
    key = "explain:" + hashlib.sha1(state.encode()).hexdigest()
    if not req.refresh and (hit := _cache_get(session, key)):
        resp = ExplainResponse.model_validate(hit)
        return resp.model_copy(update={"cached": True, "event": event})

    ctx, docs = build_explain_context(session, event, req.as_of)
    messages = [{"role": "user", "content": prompt("explain_alert", lang_name=LANG_NAME[req.lang],
                                                   context_json=json.dumps(ctx, ensure_ascii=False, indent=1))}]
    explanation: AlertExplanation | None = None
    model_name = None
    try:
        result = await generate_structured(client, messages, AlertExplanation)
        explanation, model_name = result.value, result.model or client.model
    except LLMError:
        explanation = None
    generated_by = _generated_by(client)
    if explanation is None:
        explanation = AlertExplanation(**templates.alert_explanation(ctx, req.lang))
        generated_by, model_name = "template_fallback", None
    if event.severity == "critical":
        explanation.escalate_to_ground = True  # deterministik güvenlik kuralı
    out = ExplainResponse(
        event_id=event.event_id, event=event, explanation=explanation, generated_by=generated_by,  # type: ignore[arg-type]
        model=model_name, cached=False, ungrounded_numbers=find_ungrounded_numbers(_text_fields(explanation), [ctx]),
        doc_refs=docs, created_at=datetime.now(UTC),
    )
    _cache_put(session, key, "explain", out.model_dump(mode="json"))
    return out


# ============================================================================= briefing
def build_briefing_context(session: Session, aid: str, as_of: date | None) -> tuple[dict[str, Any], list[HealthEvent]]:
    svc = get_data_service()
    res = svc.analysis(session, as_of)
    a = res.astronauts[aid]
    cat = load_catalog()
    active = svc.overlay(session, a.active_events)
    out_of_normal = []
    for metric in dict.fromkeys(c.metric for e in active if e.severity != "info" for c in e.contributors):
        sf, m = a.features.get(metric), cat.get(metric)
        last = sf.last_valid() if sf else None
        if m and last is not None:
            out_of_normal.append({"metric": metric, "display_name": m.label(), "display_name_en": m.label(),
                                  "unit": m.unit, "rolling_7d_mean": _r(last["roll7"], m.decimals + 1),
                                  "personal_baseline": _r(sf.baseline.mean, m.decimals + 1) if sf.baseline else None})
    brief = lambda e: {"event_id": e.event_id, "severity": e.severity, "system": e.system, "title": e.title,  # noqa: E731
                       "description": e.description, "since": str(e.window.start)}
    ctx = {
        "astronaut": a.info.model_dump(),
        "as_of": str(res.as_of),
        "mission_day": res.mission().mission_day,
        "overall": a.overall.model_dump(mode="json"),
        "systems": [{"system": s.system, "display_name": s.display_name, "status": s.status, "score": s.score} for s in a.systems],
        "active_alerts": [brief(e) for e in active if e.severity != "info"][:8],
        "info_alerts": [brief(e) for e in active if e.severity == "info"][:5],
        "out_of_normal_metrics": out_of_normal[:6],
        "thresholds_verified": False,
    }
    return ctx, [e for e in active if e.severity == "info"]


async def briefing(session: Session, aid: str, as_of: date | None, lang: str, refresh: bool = False) -> BriefingResponse:
    client = get_client()
    ctx, info_events = build_briefing_context(session, aid, as_of)
    sig = json.dumps([ctx["as_of"], ctx["overall"], [(x["event_id"], x["severity"]) for x in ctx["active_alerts"] + ctx["info_alerts"]]])
    key = "briefing:" + hashlib.sha1(f"v{CACHE_VERSION}|{aid}|{sig}|{lang}|{client.provider}|{client.model}".encode()).hexdigest()
    if not refresh and (hit := _cache_get(session, key)):
        resp = BriefingResponse.model_validate(hit)
        return resp.model_copy(update={"cached": True, "info_events": info_events})

    messages = [{"role": "user", "content": prompt("briefing", lang_name=LANG_NAME.get(lang, "English"),
                                                   context_json=json.dumps(ctx, ensure_ascii=False, indent=1))}]
    value: DailyBriefing | None = None
    model_name = None
    try:
        result = await generate_structured(client, messages, DailyBriefing)
        value, model_name = result.value, result.model or client.model
    except LLMError:
        value = None
    generated_by = _generated_by(client)
    if value is None:
        value = DailyBriefing(**templates.daily_briefing(ctx, lang))
        generated_by, model_name = "template_fallback", None
    if any(x["severity"] == "critical" for x in ctx["active_alerts"]):
        value.escalate_to_ground = True
    out = BriefingResponse(
        astronaut_id=aid, as_of=date.fromisoformat(ctx["as_of"]) if ctx["as_of"] != "None" else None, lang=lang,  # type: ignore[arg-type]
        briefing=value, generated_by=generated_by, model=model_name, cached=False,  # type: ignore[arg-type]
        ungrounded_numbers=find_ungrounded_numbers(_text_fields(value), [ctx]), info_events=info_events,
        created_at=datetime.now(UTC),
    )
    _cache_put(session, key, "briefing", out.model_dump(mode="json"))
    return out


# ============================================================================= chat
def _system_prompt(session: Session, req: ChatRequest, lang: str, emergency_labels: list[str]) -> str:
    res = get_data_service().analysis(session, req.as_of)
    a = res.astronauts[req.astronaut_id]
    text = prompt("system", astronaut_name=a.info.name, astronaut_id=a.info.id, astronaut_role=a.info.role or "-",
                  as_of=res.as_of, mission_day=res.mission().mission_day, lang_hint=LANG_NAME[lang])
    if emergency_labels:
        text += (
            "\n\nIMPORTANT: the rule-based emergency detector flagged possible emergency symptoms in the user's last "
            f"message ({', '.join(emergency_labels)}). Begin your answer by telling them to start the medical emergency "
            "protocol and contact the crew medical officer (CMO) immediately."
        )
    return text


def _chunks(text: str) -> list[str]:
    return re.findall(r"\S+\s*", text)


async def chat_stream(session: Session, req: ChatRequest) -> AsyncIterator[tuple[str, BaseModel]]:
    s = get_settings()
    client = get_client()
    last = req.messages[-1].content
    lang = req.lang or "en"
    res = get_data_service().analysis(session, req.as_of)
    yield "meta", SSEMeta(request_id=uuid.uuid4().hex[:12], provider=client.provider, model=client.model,
                          tool_mode=("native" if getattr(client, "native_tools", True) and s.llm_tool_mode != "prompt" else "prompt"),
                          astronaut_id=req.astronaut_id, as_of=res.as_of)

    emergency = detect_emergency(last, lang)  # LLM'den ÖNCE, kural tabanlı
    if emergency:
        yield "emergency", emergency

    history = [{"role": m.role, "content": m.content} for m in req.messages[-HISTORY_LIMIT:]]
    messages = [{"role": "system", "content": _system_prompt(session, req, lang, emergency.matched_labels if emergency else [])},
                *history]
    ctx = ToolContext(astronaut_id=req.astronaut_id, as_of=req.as_of, lang=lang)
    agent = Agent(client, _registry, s)
    try:
        async for ev in agent.run(messages, ctx):
            yield ev
    except LLMError as e:
        yield "error", SSEError(code="llm_unavailable", message=str(e))
        async for ev in _offline_answer(ctx, lang, emergency.message if emergency else None):
            yield ev
    except Exception as e:  # noqa: BLE001
        yield "error", SSEError(code="llm_error", message=f"{type(e).__name__}: {e}")
        yield "done", SSEDone(message="", finish_reason="error", steps=0, tool_calls=0, degraded=True)


async def _offline_answer(ctx: ToolContext, lang: str, emergency_msg: str | None) -> AsyncIterator[tuple[str, BaseModel]]:
    """LLM yokken: sağlık özetini doğrudan tool ile al, şablonla cevapla."""
    result = await anyio.to_thread.run_sync(_registry.execute, ctx, "get_health_summary", {})
    text = templates.chat_answer([("get_health_summary", result.data)] if result.ok else [], lang, "offline")
    if emergency_msg:
        text = f"{emergency_msg}\n\n{text}"
    for piece in _chunks(text):
        yield "token", SSEToken(text=piece)
    yield "done", SSEDone(message=text, finish_reason="llm_unavailable", steps=0, tool_calls=0, degraded=True)
