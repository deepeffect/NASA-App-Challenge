""""Asistana sor" (gemi, astronaut_health): LLM sohbeti, sadece giriş yapan astronotun verisiyle.

- Acil belirti taraması kural tabanlıdır ve LLM'den ÖNCE çalışır; basit olumsuzlama ayırt edilir
  ("göğüs ağrım yok" tetiklemez). Eşleşirse gemide CMO kaydı oluşur; Dünya'ya gönderilmez.
- LLM'e ulaşılamazsa kural tabanlı özet (get_today_summary + şablon) döner.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import AsyncIterator

import anyio
from pydantic import BaseModel
from sqlalchemy.engine import Engine
from sqlmodel import Session

from app.config import Settings
from app.i18n import Lang, t
from app.llm import templates
from app.llm.agent import Agent
from app.llm.client import LLMClient
from app.llm.personal_tools import personal_registry
from app.llm.prompts import prompt
from app.llm.tools import ToolContext
from app.llm.types import LLMError
from app.models.schemas import ChatRequest, SSEDone, SSEError, SSEMeta, SSEToken
from app.personal.catalog import load_personal_catalog
from app.personal.dataset import AstronautSeries
from app.safety.emergency import detect_emergency
from app.services.checkin import record_cmo

HISTORY_LIMIT = 12
LANG_NAME = {"tr": "Turkish", "en": "English"}
_registry = personal_registry()


def system_prompt(series: AstronautSeries, lang: Lang, emergency_labels: list[str]) -> str:
    cat = load_personal_catalog()
    text = prompt(
        "personal_system",
        astronaut_id=series.meta.id,
        mission=cat.missions[series.meta.mission].get("en"),
        day=len(series.days),
        n_days=len(series.days),
        mission_day=series.days[-1].mission_day,
        lang_hint=LANG_NAME[lang],
    )
    if emergency_labels:
        text += (
            "\n\nIMPORTANT: the rule-based emergency detector flagged possible emergency symptoms in the user's last "
            f"message ({', '.join(emergency_labels)}). The crew medical officer (CMO) on board has been notified. Begin "
            "your answer by telling them to stop, rest and contact the CMO now."
        )
    return text


async def chat_stream(
    engine: Engine, settings: Settings, client: LLMClient, series: AstronautSeries, req: ChatRequest, lang: Lang
) -> AsyncIterator[tuple[str, BaseModel]]:
    last = req.messages[-1].content
    yield "meta", SSEMeta(
        request_id=uuid.uuid4().hex[:12],
        provider=client.provider,  # type: ignore[attr-defined]
        model=client.model,  # type: ignore[attr-defined]
        tool_mode="native" if getattr(client, "native_tools", True) and settings.llm_tool_mode != "prompt" else "prompt",
        astronaut_id=series.meta.id,
        as_of=None,
    )

    emergency = detect_emergency(last, lang, negation_aware=True)  # LLM'den ÖNCE, kural tabanlı
    if emergency:
        with Session(engine) as db:
            record_cmo(db, series, series.today_index, "chat", None, last)
            db.commit()
        emergency.cmo_notified = True
        emergency.message = f"{t('cmo_title', lang)} {emergency.message}"
        yield "emergency", emergency

    history = [{"role": m.role, "content": m.content} for m in req.messages[-HISTORY_LIMIT:]]
    labels = emergency.matched_labels if emergency else []
    messages = [{"role": "system", "content": system_prompt(series, lang, labels)}, *history]
    ctx = ToolContext(astronaut_id=series.meta.id, as_of=None, lang=lang, session_factory=lambda: Session(engine))
    agent = Agent(client, _registry, settings)
    try:
        async for ev in agent.run(messages, ctx):
            yield ev
    except LLMError as e:
        yield "error", SSEError(code="llm_unavailable", message=str(e))
        async for ev in offline_answer(ctx, lang, emergency.message if emergency else None):
            yield ev
    except Exception as e:  # noqa: BLE001
        yield "error", SSEError(code="llm_error", message=f"{type(e).__name__}: {e}")
        yield "done", SSEDone(message="", finish_reason="error", steps=0, tool_calls=0, degraded=True)


async def offline_answer(ctx: ToolContext, lang: str, emergency_msg: str | None) -> AsyncIterator[tuple[str, BaseModel]]:
    result = await anyio.to_thread.run_sync(_registry.execute, ctx, "get_today_summary", {})
    text = templates.chat_answer([("get_today_summary", result.data)] if result.ok else [], lang, "offline")
    if emergency_msg:
        text = f"{emergency_msg}\n\n{text}"
    for piece in re.findall(r"\S+\s*", text):
        yield "token", SSEToken(text=piece)
    yield "done", SSEDone(message=text, finish_reason="llm_unavailable", steps=0, tool_calls=0, degraded=True)
