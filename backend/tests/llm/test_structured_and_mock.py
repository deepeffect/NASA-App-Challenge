import asyncio
import json

import pytest

from app.llm.mock import MockClient
from app.llm.structured import extract_json, generate_structured
from app.llm.types import LLMResponse, StructuredOutputUnsupported
from app.models.schemas import AlertExplanation

from .fakes import ScriptedClient

GOOD = {"summary": "s", "likely_factors": ["a"], "recommended_actions": ["b"], "escalate_to_ground": False,
        "sources": ["metric:sleep_duration"], "uncertainty": None}


def gen(client):
    return asyncio.run(generate_structured(client, [{"role": "user", "content": "x"}], AlertExplanation))


def test_valid_first_try_with_think_and_fence():
    raw = "<think>\n\n</think>\n```json\n" + json.dumps(GOOD) + "\n```"
    client = ScriptedClient([raw])
    r = gen(client)
    assert r.value is not None and r.attempts == 1
    fmt = client.requests[0]["response_format"]
    assert fmt["type"] == "json_schema" and fmt["json_schema"]["name"] == "AlertExplanation"


def test_retry_once_with_validation_feedback():
    client = ScriptedClient([json.dumps({"summary": "eksik"}), json.dumps(GOOD)])
    r = gen(client)
    assert r.value is not None and r.attempts == 2
    retry_msgs = client.requests[1]["messages"]
    assert retry_msgs[-1]["role"] == "user" and "invalid" in retry_msgs[-1]["content"]
    assert "likely_factors" in retry_msgs[-1]["content"]


def test_gives_up_after_retry():
    r = gen(ScriptedClient(["not json", "still not json"]))
    assert r.value is None and r.attempts == 2 and r.error


def test_falls_back_to_json_object_when_schema_unsupported():
    client = ScriptedClient([StructuredOutputUnsupported("json_schema unsupported"), json.dumps(GOOD)])
    r = gen(client)
    assert r.value is not None
    assert [q["response_format"]["type"] for q in client.requests] == ["json_schema", "json_object"]


def test_extract_json():
    assert extract_json('Sonuç: {"a": 1} tamam') == '{"a": 1}'


# --------------------------------------------------------------------------- mock
@pytest.mark.usefixtures("seeded_db")
def test_mock_plans_tools_by_keyword_and_answers():
    m = MockClient(delay_ms=0)
    tools = [{"type": "function", "function": {"name": n}} for n in ("get_metric", "get_radiation_dose", "get_health_summary")]
    msgs = [{"role": "system", "content": "astronaut_id: AST-02"}, {"role": "user", "content": "How is my sleep and radiation dose?"}]
    r = asyncio.run(m.chat(msgs, tools=tools))
    assert {c.name for c in r.tool_calls} == {"get_metric", "get_radiation_dose"}
    assert all(c.parsed_arguments().get("astronaut_id") == "AST-02" for c in r.tool_calls)
    metric_call = next(c for c in r.tool_calls if c.name == "get_metric")
    follow = msgs + [
        {"role": "assistant", "content": None, "tool_calls": [metric_call.as_openai()]},
        {"role": "tool", "tool_call_id": metric_call.id, "content": json.dumps(
            {"display_name": "Sleep duration", "unit": "h", "latest": {"value": 5.1, "date": "2026-11-14"},
             "personal_baseline": {"mean": 7.2}, "active_alerts": []})},
    ]
    ans = asyncio.run(m.chat(follow, tools=tools))
    assert not ans.tool_calls and "5.1 h" in ans.content and "Mock mode" in ans.content


def test_mock_structured_uses_context():
    ctx = {"event": {"event_id": "evt_x", "severity": "critical", "system": "sleep", "title": "Sleep duration below personal normal",
                     "description": "7-day mean 5.1 h.", "window": {"start": "2026-10-18", "end": "2026-11-14"},
                     "contributors": [{"metric": "sleep_duration", "value": 5.1, "baseline": 7.2, "z": -6.0, "weight": 1}]},
           "metrics": {"sleep_duration": {"display_name": "Sleep duration", "display_name_en": "Sleep duration", "unit": "h",
                                          "decimals": 1, "threshold_verified": False}},
           "related_active_events": [], "recent_checkin_notes": ["Can't fall asleep"], "docs": []}
    m = MockClient(delay_ms=0)
    msg = [{"role": "user", "content": f"Write all text fields in English.\n<context>\n{json.dumps(ctx)}\n</context>"}]
    rf = {"type": "json_schema", "json_schema": {"name": "AlertExplanation", "schema": {}}}
    r: LLMResponse = asyncio.run(m.chat(msg, response_format=rf))
    exp = AlertExplanation.model_validate_json(r.content)
    assert exp.escalate_to_ground is True
    assert any("Can't fall asleep" in f for f in exp.likely_factors)
    assert "placeholder" in exp.uncertainty
