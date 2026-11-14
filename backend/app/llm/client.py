"""LLM istemcileri: ortak arayüz + OpenAI uyumlu gerçek istemci (Ollama/vLLM/llama.cpp).

Ollama notları (qwen3):
  - Native tool calling /v1/chat/completions üzerinden ek ayar gerektirmez.
  - /v1 istek başına num_ctx kabul etmez → sunucuda OLLAMA_CONTEXT_LENGTH ayarlayın.
  - Düşünce metni ya `reasoning`/`reasoning_content` alanında ya da içerikte <think> etiketleriyle gelir;
    ikisi de desteklenir. Thinking kapalıyken Qwen3 soft switch'i (/no_think) sistem prompt'una eklenir.
"""

from collections.abc import AsyncIterator
from typing import Any, Protocol

from app.config import Settings, get_settings
from app.llm.think import ThinkFilter, split_think
from app.llm.types import (
    LLMResponse,
    LLMUnavailable,
    Message,
    StreamDelta,
    StructuredOutputUnsupported,
    ToolCall,
    ToolsUnsupported,
    new_call_id,
)


class LLMClient(Protocol):
    provider: str
    model: str
    native_tools: bool  # False → agent prompt tabanlı tool calling kullanır

    async def chat(
        self, messages: list[Message], *, tools: list[dict] | None = None, response_format: dict | None = None,
        temperature: float | None = None, max_tokens: int | None = None,
    ) -> LLMResponse: ...

    def stream(
        self, messages: list[Message], *, tools: list[dict] | None = None, temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[StreamDelta]: ...


def _extra(obj: Any, *names: str) -> str:
    """openai SDK modellerinde standart dışı alanlar (reasoning vb.) model_extra'dadır."""
    for n in names:
        v = getattr(obj, n, None)
        if v is None and getattr(obj, "model_extra", None):
            v = obj.model_extra.get(n)
        if isinstance(v, str) and v:
            return v
    return ""


class OpenAICompatClient:
    provider = "openai"

    def __init__(self, settings: Settings | None = None) -> None:
        from openai import AsyncOpenAI

        self.s = settings or get_settings()
        self.model = self.s.llm_model
        self.native_tools = self.s.llm_tool_mode != "prompt"
        self._client = AsyncOpenAI(base_url=self.s.llm_base_url, api_key=self.s.llm_api_key,
                                   timeout=self.s.llm_timeout, max_retries=1)

    # ------------------------------------------------------------------ hazırlık
    def _prepare(self, messages: list[Message]) -> list[Message]:
        if not self.s.llm_qwen_soft_switch:
            return messages
        switch = "/think" if self.s.llm_thinking else "/no_think"
        out = [dict(m) for m in messages]
        if out and out[0].get("role") == "system":
            out[0]["content"] = f"{out[0]['content']}\n\n{switch}"
        else:
            out.insert(0, {"role": "system", "content": switch})
        return out

    def _kwargs(self, messages, tools, response_format, temperature, max_tokens) -> dict[str, Any]:
        kw: dict[str, Any] = {
            "model": self.model,
            "messages": self._prepare(messages),
            "temperature": self.s.llm_temperature if temperature is None else temperature,
            "max_tokens": max_tokens or self.s.llm_max_tokens,
        }
        if tools:
            kw["tools"] = tools
        if response_format:
            kw["response_format"] = response_format
        if self.s.llm_extra_body:
            kw["extra_body"] = self.s.llm_extra_body
        return kw

    def _translate(self, e: Exception, tools: bool, structured: bool) -> Exception:
        import openai

        if isinstance(e, (openai.APIConnectionError, openai.APITimeoutError)):
            return LLMUnavailable(f"Could not reach the LLM server ({self.s.llm_base_url}): {e}")
        if isinstance(e, openai.NotFoundError):
            return LLMUnavailable(f"Model not found: {self.model} — `ollama pull {self.model}`")
        if isinstance(e, openai.BadRequestError):
            msg = str(e).lower()
            if tools and ("tool" in msg or "function" in msg):
                return ToolsUnsupported(str(e))
            if structured and ("response_format" in msg or "json_schema" in msg or "format" in msg):
                return StructuredOutputUnsupported(str(e))
        if isinstance(e, openai.APIStatusError) and e.status_code >= 500:
            return LLMUnavailable(f"LLM server error {e.status_code}: {e}")
        return e

    # ------------------------------------------------------------------ çağrılar
    async def chat(self, messages, *, tools=None, response_format=None, temperature=None, max_tokens=None) -> LLMResponse:
        try:
            resp = await self._client.chat.completions.create(
                **self._kwargs(messages, tools, response_format, temperature, max_tokens))
        except Exception as e:  # noqa: BLE001
            raise self._translate(e, bool(tools), bool(response_format)) from e
        choice = resp.choices[0]
        msg = choice.message
        thinking, content = split_think(msg.content or "")
        reasoning = _extra(msg, "reasoning_content", "reasoning") or thinking
        calls = [ToolCall(id=tc.id or new_call_id(), name=tc.function.name, arguments=tc.function.arguments or "{}")
                 for tc in (msg.tool_calls or []) if getattr(tc, "function", None)]
        return LLMResponse(content=content, tool_calls=calls, reasoning=reasoning,
                           finish_reason=choice.finish_reason, model=resp.model)

    async def stream(self, messages, *, tools=None, temperature=None, max_tokens=None) -> AsyncIterator[StreamDelta]:
        try:
            stream = await self._client.chat.completions.create(
                **self._kwargs(messages, tools, None, temperature, max_tokens), stream=True)
        except Exception as e:  # noqa: BLE001
            raise self._translate(e, bool(tools), False) from e

        think = ThinkFilter()
        content: list[str] = []
        reasoning: list[str] = []
        calls: dict[int, dict[str, str]] = {}
        finish, model = None, None
        try:
            async for chunk in stream:
                model = model or chunk.model
                if not chunk.choices:
                    continue
                ch = chunk.choices[0]
                finish = ch.finish_reason or finish
                delta = ch.delta
                if delta is None:
                    continue
                r = _extra(delta, "reasoning_content", "reasoning")
                if r:
                    reasoning.append(r)
                    yield StreamDelta("thinking", r)
                if delta.content:
                    for kind, text in think.feed(delta.content):
                        (content if kind == "token" else reasoning).append(text)
                        yield StreamDelta(kind, text)  # type: ignore[arg-type]
                for i, tc in enumerate(delta.tool_calls or []):
                    idx = tc.index if tc.index is not None else i
                    slot = calls.setdefault(idx, {"id": "", "name": "", "arguments": ""})
                    if tc.id:
                        slot["id"] = tc.id
                    if tc.function is not None:
                        if tc.function.name:
                            slot["name"] += tc.function.name
                        if tc.function.arguments:
                            slot["arguments"] += tc.function.arguments
        except Exception as e:  # noqa: BLE001
            raise self._translate(e, bool(tools), False) from e
        for kind, text in think.flush():
            (content if kind == "token" else reasoning).append(text)
            yield StreamDelta(kind, text)  # type: ignore[arg-type]
        tool_calls = [ToolCall(id=c["id"] or new_call_id(), name=c["name"], arguments=c["arguments"] or "{}")
                      for _, c in sorted(calls.items()) if c["name"]]
        yield StreamDelta("done", response=LLMResponse(content="".join(content), tool_calls=tool_calls,
                                                       reasoning="".join(reasoning), finish_reason=finish, model=model))


def get_llm_client(settings: Settings | None = None) -> LLMClient:
    s = settings or get_settings()
    if s.llm_provider == "mock":
        from app.llm.mock import MockClient

        return MockClient(delay_ms=s.mock_stream_delay_ms)
    return OpenAICompatClient(s)
