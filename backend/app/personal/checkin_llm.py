"""LLM check-in (iskelet): aynı `assistantTurn` sözleşmesini Qwen ile, JSON şemalı çıktıyla doldurur.

LLM sadece cevap metnini ve "flag" kararını üretir. Akış (sıradaki soru, bitiş) ve güvenlik kural
tabanlıdır (CLAUDE.md kural 1–2):
  - Acil belirti kural tabanlı tespit edilir; acil ise LLM cevabı kullanılmaz, scripted cevap döner.
  - Cevaptaki sayılar bağlamda yoksa (sayı denetimi) LLM cevabı reddedilir → çağıran yedeğe düşer.
  - Not metni astronotun cevabının kendisidir (prototip), LLM yeniden yazmaz.
Prompt: app/llm/prompts/checkin_turn.md (LLM ekibi ayarlayacak).
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field

from app.i18n import Lang
from app.llm.client import LLMClient
from app.llm.prompts import prompt
from app.llm.structured import generate_structured
from app.personal.checkin_script import TOPICS, assistant_turn
from app.safety.grounding import find_ungrounded_numbers

LANG_NAME = {"tr": "Turkish", "en": "English"}


class CheckinTurnDraft(BaseModel):
    """LLM'in doldurduğu kısım."""

    reply: str = Field(min_length=1, max_length=600, description="Astronota kısa cevap (1-2 cümle)")
    flag: bool = Field(description="Bu konu bugün izlenmeli mi")
    skip: bool = Field(False, description="Sadece 'other' konusu: astronot eklenecek bir şey olmadığını söyledi")


class LLMTurnRejected(Exception):
    """LLM cevabı geçersiz veya güvenlik denetiminden geçmedi (→ yedek)."""


def turn_messages(ctx: dict[str, Any], lang: Lang) -> list[dict[str, str]]:
    t = TOPICS[ctx["step"]]
    system = prompt("checkin_turn", lang_name=LANG_NAME[lang], topic=t.key, question=t.q[lang])
    user = f"<context>\n{json.dumps(ctx, ensure_ascii=False)}\n</context>\nWrite all text fields in {LANG_NAME[lang]}."
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


async def llm_turn(client: LLMClient, ctx: dict[str, Any], lang: Lang) -> dict[str, Any]:
    scripted = assistant_turn(ctx, lang)  # akış ve güvenlik referansı
    if scripted["note"] and scripted["note"]["urgent"]:
        return scripted  # acil durum: kural tabanlı cevap, LLM'e sorulmaz
    res = await generate_structured(client, turn_messages(ctx, lang), CheckinTurnDraft)
    if res.value is None:
        raise LLMTurnRejected(res.error or "geçersiz yapılandırılmış çıktı")
    draft = res.value
    ungrounded = find_ungrounded_numbers(draft.reply, [ctx])
    if ungrounded:
        raise LLMTurnRejected(f"kaynaksız sayılar: {ungrounded}")
    t = TOPICS[ctx["step"]]
    skip = t.key == "other" and draft.skip
    note = None if skip else {"topic": t.name[lang], "topic_key": t.key, "text": ctx["answer"].strip(), "flag": draft.flag, "urgent": False}
    return {"reply": draft.reply, "note": note, "next": scripted["next"], "done": scripted["done"]}
