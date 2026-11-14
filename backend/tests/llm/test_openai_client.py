"""OpenAICompatClient — gerçek sunucu yerine Ollama/vLLM tarzı cevaplar veren sahte HTTP transport ile.

Ollama'ya karşı entegrasyon testi DEĞİLDİR; SDK cevaplarının bizim tiplerimize doğru çevrildiğini doğrular.
"""

import asyncio
import json

import httpx
import pytest
from openai import AsyncOpenAI

from app.config import get_settings
from app.llm.client import OpenAICompatClient
from app.llm.types import LLMUnavailable, ToolsUnsupported


def _chunk(delta: dict, finish=None) -> str:
    return "data: " + json.dumps({"id": "x", "object": "chat.completion.chunk", "created": 0, "model": "qwen3:14b",
                                  "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}) + "\n\n"


def make_client(handler, **settings_kw) -> tuple[OpenAICompatClient, list[dict]]:
    seen: list[dict] = []

    def wrapped(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return handler(request)

    s = get_settings().model_copy(update={"llm_provider": "openai", "llm_model": "qwen3:14b", **settings_kw})
    c = OpenAICompatClient(s)
    c._client = AsyncOpenAI(base_url="http://fake/v1", api_key="k", max_retries=0,
                            http_client=httpx.AsyncClient(transport=httpx.MockTransport(wrapped)))
    return c, seen


def collect(client, **kw):
    async def go():
        return [d async for d in client.stream([{"role": "system", "content": "sys"}, {"role": "user", "content": "hi"}], **kw)]

    return asyncio.run(go())


def test_stream_think_tags_and_tool_call_deltas():
    body = "".join([
        _chunk({"role": "assistant", "content": "<thi"}),
        _chunk({"content": "nk>\n\n</think>\n\n"}),
        _chunk({"tool_calls": [{"index": 0, "id": "call_a", "type": "function",
                                "function": {"name": "get_metric", "arguments": '{"metric": '}}]}),
        _chunk({"tool_calls": [{"index": 0, "function": {"arguments": '"sleep_duration"}'}}]}),
        _chunk({}, finish="tool_calls"),
        "data: [DONE]\n\n",
    ])
    client, seen = make_client(lambda r: httpx.Response(200, text=body, headers={"content-type": "text/event-stream"}))
    deltas = collect(client, tools=[{"type": "function", "function": {"name": "get_metric", "parameters": {}}}])
    assert [d.kind for d in deltas] == ["done"], "boş <think> bloğu token üretmemeli"
    resp = deltas[-1].response
    assert resp.content == "" and resp.finish_reason == "tool_calls"
    assert [(c.id, c.name, c.parsed_arguments()) for c in resp.tool_calls] == [("call_a", "get_metric", {"metric": "sleep_duration"})]
    req = seen[0]
    assert req["stream"] is True and req["tools"]
    assert req["messages"][0]["content"].endswith("/no_think"), "thinking kapalı → Qwen soft switch"


def test_stream_content_and_reasoning_field():
    body = "".join([
        _chunk({"reasoning": "kullanıcı uykuyu soruyor"}),
        _chunk({"content": "Uykun "}),
        _chunk({"content": "azalmış."}, finish="stop"),
        "data: [DONE]\n\n",
    ])
    client, seen = make_client(lambda r: httpx.Response(200, text=body, headers={"content-type": "text/event-stream"}),
                               llm_thinking=True, llm_extra_body={"think": True})
    deltas = collect(client)
    assert [(d.kind, d.text) for d in deltas[:-1]] == [("thinking", "kullanıcı uykuyu soruyor"), ("token", "Uykun "), ("token", "azalmış.")]
    assert deltas[-1].response.content == "Uykun azalmış."
    assert seen[0]["messages"][0]["content"].endswith("/think")
    assert seen[0]["think"] is True  # LLM_EXTRA_BODY gövdeye eklenir


def test_chat_non_stream_with_tool_calls_and_inline_think():
    payload = {"id": "x", "object": "chat.completion", "created": 0, "model": "qwen3:14b", "choices": [{
        "index": 0, "finish_reason": "stop",
        "message": {"role": "assistant", "content": "<think>plan</think>{\"a\": 1}",
                    "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "get_alerts", "arguments": "{}"}}]}}]}
    client, seen = make_client(lambda r: httpx.Response(200, json=payload))
    r = asyncio.run(client.chat([{"role": "user", "content": "x"}], response_format={"type": "json_object"}))
    assert r.content == '{"a": 1}' and r.reasoning == "plan"
    assert r.tool_calls[0].name == "get_alerts"
    assert seen[0]["response_format"] == {"type": "json_object"}


def test_error_translation():
    tools = [{"type": "function", "function": {"name": "x", "parameters": {}}}]
    c, _ = make_client(lambda r: httpx.Response(400, json={"error": {"message": "registry.ollama.ai/library/foo does not support tools"}}))
    with pytest.raises(ToolsUnsupported):
        asyncio.run(c.chat([{"role": "user", "content": "x"}], tools=tools))

    c, _ = make_client(lambda r: httpx.Response(404, json={"error": {"message": "model 'qwen3:14b' not found"}}))
    with pytest.raises(LLMUnavailable, match="ollama pull"):
        asyncio.run(c.chat([{"role": "user", "content": "x"}]))

    def boom(_r):
        raise httpx.ConnectError("refused")

    c, _ = make_client(boom)
    with pytest.raises(LLMUnavailable):
        collect(c)
