"""Agent loop: native, metin içi tool call, prompt modu, auto geçişi, adım sınırı, sayı denetimi."""

import asyncio
import json

import pytest

from app.config import get_settings
from app.llm.agent import Agent
from app.llm.tools import ToolContext, ToolRegistry
from app.llm.types import LLMResponse, LLMUnavailable, ToolsUnsupported

from .fakes import ScriptedClient, call

pytestmark = pytest.mark.usefixtures("seeded_db")
SYSTEM = {"role": "system", "content": "test system. astronaut_id: AST-02"}


def settings(**kw):
    return get_settings().model_copy(update={"llm_max_tool_steps": 3, **kw})


def run_agent(client, user="Uykum nasıl?", **kw):
    agent = Agent(client, ToolRegistry(), settings(**kw))
    ctx = ToolContext(astronaut_id="AST-02")

    async def collect():
        return [ev async for ev in agent.run([SYSTEM, {"role": "user", "content": user}], ctx)]

    return asyncio.run(collect())


def names(events):
    return [n for n, _ in events]


def tokens(events):
    return "".join(p.text for n, p in events if n == "token")


def _sleep_value():
    """Gerçek tool verisinden sayı (cevap metninde kullanmak için)."""
    reg = ToolRegistry()
    res = reg.execute(ToolContext(astronaut_id="AST-02"), "get_metric", {"metric": "sleep_duration", "days": 7})
    return res.data["latest"]["value"]


def test_native_tool_loop():
    v = _sleep_value()
    client = ScriptedClient([
        LLMResponse(tool_calls=[call("get_metric", '{"metric": "sleep_duration", "days": 7}')]),
        f"Son uyku süren {v} saat; kişisel normalinin altında.",
    ])
    events = run_agent(client)
    assert names(events)[:2] == ["tool_call", "tool_result"]
    assert names(events)[-1] == "done"
    tr = dict(events)["tool_result"]
    assert tr.ok and "sleep_duration" in tr.preview
    done = events[-1][1]
    assert (done.finish_reason, done.tool_calls, done.steps) == ("stop", 1, 2)
    assert done.ungrounded_numbers == []
    assert tokens(events).startswith("Son uyku")
    # 2. istekte tool sonucu native formatta geri verilmiş olmalı
    second = client.requests[1]["messages"]
    assert second[-1]["role"] == "tool" and "name" not in second[-1]
    assert second[-2]["tool_calls"][0]["function"]["name"] == "get_metric"
    assert client.requests[0]["tools"] and client.requests[1]["tools"]


def test_textual_tool_call_in_native_mode_is_parsed_and_not_leaked():
    client = ScriptedClient([
        '<tool_call>{"name": "get_alerts", "arguments": {"astronaut_id": "AST-02"}}</tool_call>',
        "Aktif uyarıların var.",
    ])
    events = run_agent(client, "Uyarılarım neler?")
    assert "<tool_call>" not in tokens(events)
    assert names(events).count("tool_call") == 1
    assert tokens(events) == "Aktif uyarıların var."


def test_prompt_mode():
    client = ScriptedClient([
        'Hemen bakıyorum <tool_call>{"name": "get_health_summary", "arguments": {}}</tool_call>',
        "Genel durumun kırmızı.",
    ], native_tools=False)
    events = run_agent(client, "Bugün nasılım?", llm_tool_mode="prompt")
    first = client.requests[0]
    assert first["tools"] is None
    assert "<tool_call>" in first["messages"][0]["content"] and "get_health_summary" in first["messages"][0]["content"]
    second = client.requests[1]["messages"]
    assert second[-1]["role"] == "user" and second[-1]["content"].startswith("<tool_response")
    assert "<tool_call>" in second[-2]["content"]
    assert tokens(events) == "Hemen bakıyorum Genel durumun kırmızı."
    assert dict(events)["tool_result"].ok


def test_auto_switches_to_prompt_mode_when_tools_rejected():
    client = ScriptedClient([
        ToolsUnsupported("model does not support tools"),
        '<tool_call>{"name": "get_alerts", "arguments": {}}</tool_call>',
        "Tamam.",
    ])
    events = run_agent(client, llm_tool_mode="auto")
    assert client.native_tools is False
    assert client.requests[1]["tools"] is None
    assert events[-1][1].finish_reason == "stop" and events[-1][1].steps == 2


def test_max_steps_forces_final_answer():
    loop = [LLMResponse(tool_calls=[call("get_alerts", "{}", f"c{i}")]) for i in range(3)]
    client = ScriptedClient([*loop, "Elimdeki veriyle özet: uyarıların var."])
    events = run_agent(client)
    done = events[-1][1]
    assert done.finish_reason == "max_steps" and done.tool_calls == 3
    assert client.requests[-1]["tools"] is None
    assert tokens(events).endswith("uyarıların var.")


def test_unknown_tool_and_bad_args_do_not_crash():
    client = ScriptedClient([
        LLMResponse(tool_calls=[call("nope", "{}", "a"), call("get_metric", '{"metric": "bogus"}', "b")]),
        "Veri alınamadı.",
    ])
    events = run_agent(client)
    results = [p for n, p in events if n == "tool_result"]
    assert [r.ok for r in results] == [False, False]
    assert "unknown tool" in results[0].error and "unknown metric" in results[1].error
    assert events[-1][0] == "done"


def test_ungrounded_number_flagged():
    client = ScriptedClient([
        LLMResponse(tool_calls=[call("get_metric", '{"metric": "sleep_duration"}')]),
        "Uykun 12,7 saat görünüyor.",
    ])
    assert run_agent(client)[-1][1].ungrounded_numbers == ["12,7"]


def test_llm_unavailable_propagates():
    client = ScriptedClient([LLMUnavailable("down")])
    with pytest.raises(LLMUnavailable):
        run_agent(client)


def test_tool_schemas_are_openai_compatible():
    tools = ToolRegistry().openai_tools()
    assert {t["function"]["name"] for t in tools} == {
        "get_metric", "get_health_summary", "get_alerts", "get_radiation_dose", "get_checkins", "search_docs"}
    gm = next(t for t in tools if t["function"]["name"] == "get_metric")["function"]["parameters"]
    assert "sleep_duration" in gm["properties"]["metric"]["enum"]
    assert gm["required"] == ["metric"]
    json.dumps(tools)


def test_tools_return_engine_values():
    reg = ToolRegistry()
    ctx = ToolContext(astronaut_id="AST-02")
    s = reg.execute(ctx, "get_health_summary", {})
    assert s.ok and s.data["overall"]["status"] == "red" and s.data["active_alerts"]
    rad = reg.execute(ctx, "get_radiation_dose", "{}")
    assert rad.ok and rad.data["cumulative"]["value"] > 0
    own = reg.execute(ctx, "get_checkins", {"days": 7})
    other = reg.execute(ctx, "get_checkins", {"astronaut_id": "AST-01", "days": 7})
    assert own.ok and other.ok
    assert all("note" not in c for c in other.data["checkins"]), "başkasının notları gizli"
    bad = reg.execute(ctx, "get_metric", {"metric": "sleep_duration", "days": 999})
    assert not bad.ok and "invalid call" in bad.error
