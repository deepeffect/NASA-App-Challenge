"""Asistan katmanı (LLM ekibinin API'si): "Asistana sor" cevabını kural motoru + kaynak rozetleriyle üretir.

`ASSISTANT_LAYER_URL` doluysa /me sohbeti önce buraya gider; ulaşılamazsa çağıran Ollama yoluna düşer.
Katman durumsuzdur: astronot ve bütün günlük kayıtları her istekte gövdede gönderilir (global seçim yok).

Sözleşme (LLM ekibiyle sabitlendi):
    POST {ASSISTANT_LAYER_URL}/chat/completions
    {"model": "ai-gambit-health", "stream": false, "messages": [...user/assistant...],
     "astronaut": {"astronaut_id", "age", "sex", "mission"},
     "records": [astronaut_health.json kayıtları, eskiden yeniye; son kayıt = bugün]}
    → OpenAI biçimi + üst düzey `sources` ({"D1": {...}, "K1": {...}}) ve `intent`.

Katman LLM bilgisayarında çalışır; o makine geminin parçasıdır (README → 2b), veri Dünya'ya gitmez.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx

from app.config import Settings
from app.llm.types import LLMUnavailable
from app.personal.dataset import AstronautSeries, DayData


@dataclass
class LayerAnswer:
    text: str
    sources: dict[str, dict[str, Any]] = field(default_factory=dict)
    intent: str | None = None


def to_record(astronaut_id: str, day: DayData) -> dict[str, Any]:
    """Bir günü astronaut_health.json'daki kayıt biçimine geri çevirir (dataset._parse_reconstructed'ın tersi)."""
    return {
        "astronaut_id": astronaut_id,
        "mission_day": day.mission_day,
        **day.values,
        **{f"{area}_score": score for area, score in day.area_scores.items()},
        "daily_health_score": day.daily_score,
        "cumulative_health_score": day.cumulative_score,
        "health_status": day.health_status,
        "main_concern": day.main_concern,
        "self_care_actions": list(day.self_care),
        "needs_ground_support": day.needs_ground_support,
    }


def build_body(settings: Settings, series: AstronautSeries, history: list[dict[str, str]]) -> dict[str, Any]:
    meta = series.meta
    return {
        "model": settings.assistant_layer_model,
        "stream": False,
        "messages": [m for m in history if m["role"] in ("user", "assistant")],
        "astronaut": {"astronaut_id": meta.id, "age": meta.age, "sex": meta.sex, "mission": meta.mission},
        "records": [to_record(meta.id, d) for d in series.days],
    }


async def ask_layer(
    settings: Settings,
    series: AstronautSeries,
    history: list[dict[str, str]],
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> LayerAnswer:
    """Katmana sorar. Ulaşılamazsa, hata kodu dönerse ya da cevap boş / bozuksa `LLMUnavailable` fırlatır."""
    base = (settings.assistant_layer_url or "").rstrip("/")
    if not base:
        raise LLMUnavailable("ASSISTANT_LAYER_URL ayarlı değil")
    timeout = httpx.Timeout(settings.assistant_layer_timeout, connect=5.0)
    try:
        async with httpx.AsyncClient(timeout=timeout, transport=transport) as http:
            res = await http.post(f"{base}/chat/completions", json=build_body(settings, series, history))
    except httpx.HTTPError as e:
        raise LLMUnavailable(f"Asistan katmanına ulaşılamadı ({base}): {type(e).__name__}") from e
    if res.status_code != 200:
        raise LLMUnavailable(f"Asistan katmanı {res.status_code} döndü ({base})")
    try:
        data = res.json()
        text = data["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError) as e:
        raise LLMUnavailable(f"Asistan katmanının cevabı çözülemedi: {type(e).__name__}") from e
    if not isinstance(text, str) or not text.strip():
        raise LLMUnavailable("Asistan katmanı boş cevap döndü")
    raw_sources = data.get("sources")
    sources = {str(k): v for k, v in raw_sources.items() if isinstance(v, dict)} if isinstance(raw_sources, dict) else {}
    intent = data.get("intent")
    return LayerAnswer(text=text.strip(), sources=sources, intent=intent if isinstance(intent, str) else None)
