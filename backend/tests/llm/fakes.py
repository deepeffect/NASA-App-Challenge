"""Testler için kurgulanmış (scripted) LLM istemcisi."""

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from app.llm.types import LLMResponse, StreamDelta, ToolCall


def call(name: str, args: str, cid: str = "call_1") -> ToolCall:
    return ToolCall(id=cid, name=name, arguments=args)


class ScriptedClient:
    """Sırayla verilen cevapları döner. Eleman: LLMResponse | str (içerik) | Exception (fırlatılır)."""

    provider = "scripted"
    model = "scripted-model"

    def __init__(self, responses: list[Any], native_tools: bool = True, chunk: int = 4) -> None:
        self.responses = list(responses)
        self.native_tools = native_tools
        self.chunk = chunk
        self.requests: list[dict[str, Any]] = []

    def _next(self, **req: Any) -> LLMResponse:
        self.requests.append(req)
        if not self.responses:
            raise AssertionError("ScriptedClient: beklenmeyen ek çağrı")
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return LLMResponse(content=r, model=self.model) if isinstance(r, str) else r

    async def chat(self, messages, *, tools=None, response_format=None, temperature=None, max_tokens=None) -> LLMResponse:
        return self._next(messages=messages, tools=tools, response_format=response_format)

    async def stream(self, messages, *, tools=None, temperature=None, max_tokens=None) -> AsyncIterator[StreamDelta]:
        resp = self._next(messages=messages, tools=tools)
        text = resp.content
        for i in range(0, len(text), self.chunk):
            await asyncio.sleep(0)
            yield StreamDelta("token", text[i : i + self.chunk])
        yield StreamDelta("done", response=resp)
