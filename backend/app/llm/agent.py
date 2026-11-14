"""Agent loop: model tool çağırır → tool çalışır → sonuç modele döner → … → final cevap (streaming).

Tool çağırma modları (LLM_TOOL_MODE):
  native  sunucunun function calling'i (Ollama/vLLM `tools` parametresi)
  prompt  tool şemaları sistem prompt'una yazılır, model <tool_call>{json}</tool_call> basar, biz ayrıştırırız
  auto    native dener; sunucu tools'u reddederse bu istemci için kalıcı olarak prompt moduna geçer.
          Native modda model çağrıyı düz metin olarak basarsa da (şablon uyumsuzluğu) ayrıştırılır.

Mesaj geçmişi her zaman OpenAI native formatında tutulur; prompt modunda istek öncesi dönüştürülür.
Model token'ları gelirken StreamGuard olası tool-call metnini kullanıcıya sızdırmaz.
"""

import json
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import anyio
from pydantic import BaseModel

from app.config import Settings, get_settings
from app.llm.client import LLMClient
from app.llm.prompts import prompt
from app.llm.think import strip_think
from app.llm.toolcall_parser import StreamGuard, parse_tool_calls
from app.llm.tools import ToolContext, ToolRegistry, ToolResult
from app.llm.types import LLMError, LLMResponse, LLMUnavailable, Message, ToolCall, ToolsUnsupported
from app.models.schemas import DocRef, SSEDone, SSEError, SSEThinking, SSEToken, SSEToolCall, SSEToolResult
from app.safety.grounding import find_ungrounded_numbers

AgentEvent = tuple[str, BaseModel]  # (SSE olay adı, payload)


@dataclass
class AgentState:
    messages: list[Message]
    steps: int = 0
    tool_calls: int = 0
    tool_data: list[Any] = field(default_factory=list)
    doc_refs: list[DocRef] = field(default_factory=list)
    text: str = ""


def _args_obj(raw: str | None) -> Any:
    try:
        return json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}


def native_messages(messages: list[Message]) -> list[Message]:
    """OpenAI şemasına uymayan iç alanları temizle (tool mesajındaki 'name' gibi)."""
    return [{k: v for k, v in m.items() if not (m.get("role") == "tool" and k == "name")} for m in messages]


def to_prompt_mode(messages: list[Message], registry: ToolRegistry) -> list[Message]:
    """Native formatlı geçmişi, tools parametresi olmayan sunucular için düz metne çevir."""
    tools_json = json.dumps([t["function"] for t in registry.openai_tools()], ensure_ascii=False, indent=1)
    instructions = prompt("tool_fallback", tools_json=tools_json)
    out: list[Message] = []
    for m in messages:
        role = m.get("role")
        if role == "system" and not out:
            out.append({"role": "system", "content": f"{m['content']}\n\n{instructions}"})
        elif role == "assistant" and m.get("tool_calls"):
            calls = "\n".join(
                "<tool_call>"
                + json.dumps({"name": tc["function"]["name"], "arguments": _args_obj(tc["function"]["arguments"])},
                             ensure_ascii=False)
                + "</tool_call>"
                for tc in m["tool_calls"]
            )
            out.append({"role": "assistant", "content": ((m.get("content") or "") + "\n" + calls).strip()})
        elif role == "tool":
            out.append({"role": "user", "content": f'<tool_response name="{m.get("name", "")}">\n{m["content"]}\n</tool_response>'})
        else:
            out.append({k: v for k, v in m.items() if k in ("role", "content")})
    if not out or out[0].get("role") != "system":
        out.insert(0, {"role": "system", "content": instructions})
    return out


class Agent:
    def __init__(self, client: LLMClient, registry: ToolRegistry, settings: Settings | None = None) -> None:
        self.client = client
        self.registry = registry
        self.s = settings or get_settings()

    def _use_native(self) -> bool:
        return self.s.llm_tool_mode != "prompt" and getattr(self.client, "native_tools", True)

    async def _step(self, st: AgentState, allow_tools: bool) -> AsyncIterator[AgentEvent | LLMResponse]:
        """Tek model çağrısı (stream). Token/thinking olaylarını yield eder, en sonda LLMResponse döner."""
        native = self._use_native()
        req = native_messages(st.messages) if native else to_prompt_mode(st.messages, self.registry)
        tools = self.registry.openai_tools() if (allow_tools and native) else None
        guard = StreamGuard() if allow_tools else None
        final: LLMResponse | None = None
        async for d in self.client.stream(req, tools=tools):
            if d.kind == "thinking":
                if self.s.llm_thinking:
                    yield ("thinking", SSEThinking(text=d.text))
            elif d.kind == "token":
                out = guard.feed(d.text) if guard else d.text
                if out:
                    st.text += out
                    yield ("token", SSEToken(text=out))
            else:
                final = d.response
        final = final or LLMResponse()
        if guard is not None:
            calls = final.tool_calls
            if not calls:
                calls, _ = parse_tool_calls(final.content, self.registry.names)
                final.tool_calls = calls
            if not calls:
                rest = guard.flush()
                if rest:
                    st.text += rest
                    yield ("token", SSEToken(text=rest))
        yield final

    async def _run_tools(self, st: AgentState, ctx: ToolContext, resp: LLMResponse) -> AsyncIterator[AgentEvent]:
        st.messages.append({"role": "assistant", "content": strip_think(resp.content) or None,
                            "tool_calls": [c.as_openai() for c in resp.tool_calls]})
        for call in resp.tool_calls:
            st.tool_calls += 1
            yield ("tool_call", SSEToolCall(id=call.id, name=call.name, arguments=call.parsed_arguments()))
            t0 = time.perf_counter()
            result: ToolResult = await anyio.to_thread.run_sync(self.registry.execute, ctx, call.name, call.arguments)
            msg = result.to_message()
            yield ("tool_result", SSEToolResult(id=call.id, name=call.name, ok=result.ok,
                                                duration_ms=round((time.perf_counter() - t0) * 1000, 1),
                                                preview=msg[:500], error=result.error))
            if result.ok:
                st.tool_data.append(result.data)
                if call.name == "search_docs":
                    st.doc_refs += [DocRef(**r) for r in result.data.get("results", [])]
            st.messages.append({"role": "tool", "tool_call_id": call.id, "name": call.name, "content": msg})

    def _done(self, st: AgentState, finish: str, user_texts: list[str], degraded: bool = False) -> AgentEvent:
        ungrounded = find_ungrounded_numbers(st.text, [*st.tool_data, *user_texts])
        return ("done", SSEDone(message=st.text.strip(), finish_reason=finish, steps=st.steps,  # type: ignore[arg-type]
                                tool_calls=st.tool_calls, ungrounded_numbers=ungrounded, doc_refs=st.doc_refs,
                                degraded=degraded))

    async def run(self, messages: list[Message], ctx: ToolContext) -> AsyncIterator[AgentEvent]:
        """messages: [system, ...geçmiş, user]. LLMUnavailable dışarı fırlatılır (servis yedek cevabı üretir)."""
        st = AgentState(messages=list(messages))
        user_texts = [str(m.get("content", "")) for m in messages if m.get("role") == "user"]
        max_steps = self.s.llm_max_tool_steps
        while st.steps < max_steps:
            st.steps += 1
            final: LLMResponse | None = None
            try:
                async for item in self._step(st, allow_tools=True):
                    if isinstance(item, LLMResponse):
                        final = item
                    else:
                        yield item
            except ToolsUnsupported:
                if self.s.llm_tool_mode == "auto" and getattr(self.client, "native_tools", False):
                    self.client.native_tools = False  # bu istemci için kalıcı: prompt moduna geç
                    st.steps -= 1
                    continue
                raise
            assert final is not None
            if final.tool_calls:
                async for ev in self._run_tools(st, ctx, final):
                    yield ev
                continue
            yield self._done(st, "stop", user_texts)
            return

        # Adım sınırı aşıldı: tool'suz son bir çağrıyla cevap iste
        st.messages.append({"role": "user", "content": prompt("final_answer")})
        st.steps += 1
        async for item in self._step(st, allow_tools=False):
            if not isinstance(item, LLMResponse):
                yield item
        yield self._done(st, "max_steps", user_texts)


__all__ = ["Agent", "AgentEvent", "LLMError", "LLMUnavailable", "SSEError", "native_messages", "to_prompt_mode"]
