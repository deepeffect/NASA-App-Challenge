"""MockClient: GPU/model olmadan çalışan sahte LLM (LLM_PROVIDER=mock).

Gerçek bir model gibi davranır ki arayüz ekibi tüm akışı görebilsin:
  - Kullanıcı mesajındaki anahtar kelimelere göre GERÇEK tool çağrıları ister (gerçek veri döner)
  - Tool sonuçlarından şablon cevap üretir ve token token akıtır
  - response_format (json_schema) istenirse <context> bloğundan şablonla geçerli JSON üretir
"""

import asyncio
import json
import re
from collections.abc import AsyncIterator
from typing import Any

from app.llm import templates
from app.llm.lang import detect_lang
from app.llm.types import LLMResponse, Message, StreamDelta, ToolCall, new_call_id
from app.safety.emergency import fold_text

_AID = re.compile(r"astronaut_id:\s*([A-Za-z0-9_-]+)")
_CTX = re.compile(r"<context>\s*(.*?)\s*</context>", re.DOTALL)
_LANG = re.compile(r"Write all text fields in (\w+)")

# (anahtar kelimeler (katlanmış), tool, ek argümanlar)
_RULES: list[tuple[tuple[str, ...], str, dict[str, Any]]] = [
    (("nasilim", "nasil gidiyor", "durumum", "genel durum", "ozet", "how am i", "how are", "overall", "summary", "today"),
     "get_health_summary", {}),
    (("radyasyon", "radiation", "doz", "dose", "msv"), "get_radiation_dose", {}),
    (("uyku", "uyu", "sleep"), "get_metric", {"metric": "sleep_duration", "days": 14}),
    (("nabiz", "kalp", "heart", "pulse"), "get_metric", {"metric": "resting_hr", "days": 14}),
    (("hrv", "degiskenlik", "variability"), "get_metric", {"metric": "hrv_rmssd", "days": 14}),
    (("stres", "stress", "ruh hali", "mood", "check-in", "checkin"), "get_checkins", {"days": 7}),
    (("uyari", "alarm", "alert"), "get_alerts", {}),
    (("belge", "dokuman", "kaynak", "nasa", "protokol", "standart", "document", "guideline", "procedure"), "search_docs", {}),
]


class MockClient:
    provider = "mock"
    model = "mock"
    native_tools = True

    def __init__(self, delay_ms: int = 15) -> None:
        self.delay = delay_ms / 1000

    # ------------------------------------------------------------------ karar
    @staticmethod
    def _astronaut(messages: list[Message]) -> str | None:
        for m in messages:
            if m.get("role") == "system" and isinstance(m.get("content"), str):
                hit = _AID.search(m["content"])
                if hit:
                    return hit.group(1)
        return None

    @staticmethod
    def _last_user_index(messages: list[Message]) -> int:
        return max((i for i, m in enumerate(messages) if m.get("role") == "user" and "<tool_response" not in str(m.get("content"))), default=-1)

    def _plan(self, question: str, aid: str | None, tool_names: set[str]) -> list[ToolCall]:
        q = fold_text(question)
        calls: list[ToolCall] = []
        for keys, tool, extra in _RULES:
            if tool in tool_names and any(k in q for k in keys) and len(calls) < 3:
                args = dict(extra)
                if tool == "search_docs":
                    args["query"] = question[:200]
                elif aid:
                    args["astronaut_id"] = aid
                if all(c.name != tool or c.parsed_arguments() != args for c in calls):
                    calls.append(ToolCall(new_call_id(), tool, json.dumps(args, ensure_ascii=False)))
        if not calls and "get_health_summary" in tool_names:
            calls.append(ToolCall(new_call_id(), "get_health_summary",
                                  json.dumps({"astronaut_id": aid} if aid else {})))
        return calls

    def _decide(self, messages: list[Message], tools: list[dict] | None) -> LLMResponse:
        i = self._last_user_index(messages)
        question = str(messages[i]["content"]) if i >= 0 else ""
        lang = detect_lang(question)
        after = messages[i + 1:] if i >= 0 else []
        tool_results: list[tuple[str, dict]] = []
        names: dict[str, str] = {}
        for m in after:
            for tc in m.get("tool_calls") or []:
                names[tc["id"]] = tc["function"]["name"]
            if m.get("role") == "tool":
                try:
                    tool_results.append((names.get(m.get("tool_call_id", ""), ""), json.loads(m["content"])))
                except (json.JSONDecodeError, TypeError):
                    pass
        if tools and not tool_results:
            tool_names = {t["function"]["name"] for t in tools}
            return LLMResponse(content="", tool_calls=self._plan(question, self._astronaut(messages), tool_names),
                               finish_reason="tool_calls", model=self.model)
        return LLMResponse(content=templates.chat_answer(tool_results, lang, "mock"), finish_reason="stop", model=self.model)

    def _structured(self, messages: list[Message], response_format: dict) -> str:
        name = (response_format.get("json_schema") or {}).get("name", "")
        text = str(messages[-1].get("content", ""))
        m = _CTX.search(text)
        ctx = json.loads(m.group(1)) if m else {}
        lm = _LANG.search(text)
        lang = "en" if lm and lm.group(1).lower().startswith("english") else "tr"
        if name == "AlertExplanation":
            return json.dumps(templates.alert_explanation(ctx, lang), ensure_ascii=False)
        if name == "DailyBriefing":
            return json.dumps(templates.daily_briefing(ctx, lang), ensure_ascii=False)
        if name == "CheckinTurnDraft":  # mock: scripted check-in ile aynı karar
            from app.personal.checkin_script import assistant_turn

            out = assistant_turn(ctx, lang)
            note = out["note"]
            return json.dumps({"reply": out["reply"], "flag": bool(note and note["flag"]), "skip": note is None}, ensure_ascii=False)
        return "{}"

    # ------------------------------------------------------------------ arayüz
    async def chat(self, messages, *, tools=None, response_format=None, temperature=None, max_tokens=None) -> LLMResponse:
        if response_format:
            return LLMResponse(content=self._structured(messages, response_format), finish_reason="stop", model=self.model)
        return self._decide(messages, tools)

    async def stream(self, messages, *, tools=None, temperature=None, max_tokens=None) -> AsyncIterator[StreamDelta]:
        resp = self._decide(messages, tools)
        if not resp.tool_calls:
            for piece in re.findall(r"\S+\s*", resp.content):
                if self.delay:
                    await asyncio.sleep(self.delay)
                yield StreamDelta("token", piece)
        yield StreamDelta("done", response=resp)
