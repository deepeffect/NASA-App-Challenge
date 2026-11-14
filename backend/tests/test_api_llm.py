"""LLM endpoint'leri uçtan uca (mock modda) + LLM arızası senaryoları."""

import json

import pytest

from app.llm.types import LLMUnavailable
from app.models.schemas import BriefingResponse, ExplainResponse
from app.services import llm_service

from .llm.fakes import ScriptedClient
from .test_contract import parse_sse


@pytest.fixture
def critical_event(client):
    return client.get("/api/alerts", params={"astronaut_id": "AST-02", "min_severity": "critical"}).json()["events"][0]


@pytest.fixture
def broken_llm(monkeypatch):
    """LLM'i değiştir: verilen cevap listesiyle ScriptedClient."""

    def install(responses):
        fake = ScriptedClient(responses)
        monkeypatch.setattr(llm_service, "get_client", lambda: fake)
        return fake

    return install


# --------------------------------------------------------------------------- explain
def test_explain_mock_end_to_end_and_cache(client, critical_event):
    eid = critical_event["event_id"]
    r = ExplainResponse.model_validate(client.post(f"/api/alerts/{eid}/explain", json={"lang": "tr", "refresh": True}).json())
    assert r.generated_by == "mock" and r.cached is False
    assert r.explanation.escalate_to_ground is True, "critical → yer ekibine bildir (deterministik)"
    assert r.explanation.recommended_actions and r.explanation.likely_factors
    assert f"event:{eid}" in r.explanation.sources
    assert r.ungrounded_numbers == [], "şablon sadece bağlamdaki sayıları kullanır"
    again = ExplainResponse.model_validate(client.post(f"/api/alerts/{eid}/explain", json={"lang": "tr"}).json())
    assert again.cached is True and again.explanation == r.explanation
    en = ExplainResponse.model_validate(client.post(f"/api/alerts/{eid}/explain", json={"lang": "en"}).json())
    assert en.cached is False and "alert" in en.explanation.summary.lower()


def test_explain_falls_back_to_template_on_invalid_output(client, critical_event, broken_llm):
    fake = broken_llm(["bu json değil", '{"summary": "eksik alanlar"}'])
    r = ExplainResponse.model_validate(client.post(f"/api/alerts/{critical_event['event_id']}/explain",
                                                   json={"refresh": True}).json())
    assert r.generated_by == "template_fallback" and r.model is None
    assert len(fake.requests) == 2, "bir kez yeniden denenir"
    assert fake.requests[0]["response_format"]["json_schema"]["name"] == "AlertExplanation"
    assert "<context>" in fake.requests[0]["messages"][0]["content"]


def test_explain_survives_llm_down(client, critical_event, broken_llm):
    broken_llm([LLMUnavailable("down")])
    r = client.post(f"/api/alerts/{critical_event['event_id']}/explain", json={"refresh": True})
    assert r.status_code == 200 and r.json()["generated_by"] == "template_fallback"


def test_explain_valid_llm_output_with_ungrounded_number(client, critical_event, broken_llm):
    out = {"summary": "Uyku süren 3,3 saat düştü.", "likely_factors": ["stres"], "recommended_actions": ["CMO ile görüş"],
           "escalate_to_ground": False, "sources": ["metric:sleep_duration"], "uncertainty": None}
    broken_llm([json.dumps(out, ensure_ascii=False)])
    r = ExplainResponse.model_validate(client.post(f"/api/alerts/{critical_event['event_id']}/explain",
                                                   json={"refresh": True}).json())
    assert r.generated_by == "llm"
    assert r.explanation.escalate_to_ground is True, "model false dese de critical → true"
    assert "3,3" in r.ungrounded_numbers


# --------------------------------------------------------------------------- briefing
def test_briefing_mock(client):
    b = BriefingResponse.model_validate(client.get("/api/astronauts/AST-02/briefing", params={"refresh": True}).json())
    assert b.generated_by == "mock" and b.briefing.escalate_to_ground is True
    assert b.briefing.concerns and b.briefing.summary.startswith("Görev günü 180")
    assert all(e.severity == "info" for e in b.info_events)
    assert b.ungrounded_numbers == []
    ok = BriefingResponse.model_validate(client.get("/api/astronauts/AST-01/briefing", params={"lang": "en"}).json())
    assert ok.briefing.concerns == [] and ok.briefing.escalate_to_ground is False
    assert ok.briefing.summary.startswith("Mission day")


def test_briefing_time_slider(client):
    early = BriefingResponse.model_validate(client.get("/api/astronauts/AST-02/briefing",
                                                       params={"as_of": "2026-10-01"}).json())
    assert early.as_of.isoformat() == "2026-10-01" and early.briefing.escalate_to_ground is False


# --------------------------------------------------------------------------- chat
def _chat(client, text, aid="AST-02", **extra):
    body = {"astronaut_id": aid, "messages": [{"role": "user", "content": text}], **extra}
    with client.stream("POST", "/api/chat", json=body) as r:
        assert r.status_code == 200
        return parse_sse("".join(r.iter_text()))


def test_chat_mock_uses_real_tools_and_is_grounded(client):
    events = _chat(client, "Son günlerde uykum nasıl?")
    names = [n for n, _ in events]
    assert names[0] == "meta" and names[-1] == "done"
    calls = [p for n, p in events if n == "tool_call"]
    assert calls and calls[0]["name"] == "get_metric" and calls[0]["arguments"]["metric"] == "sleep_duration"
    results = [p for n, p in events if n == "tool_result"]
    assert results[0]["ok"] and "sleep_duration" in results[0]["preview"]
    done = events[-1][1]
    assert done["finish_reason"] == "stop" and done["tool_calls"] >= 1 and not done["degraded"]
    assert done["ungrounded_numbers"] == []
    text = "".join(p["text"] for n, p in events if n == "token")
    assert "Uyku süresi" in text and text.strip() == done["message"]


def test_chat_english(client):
    events = _chat(client, "How am I doing today?")
    assert "overall status" in events[-1][1]["message"]


def test_chat_multiple_tools(client):
    events = _chat(client, "Bugün nasılım? Radyasyon dozum ne durumda?")
    called = {p["name"] for n, p in events if n == "tool_call"}
    assert called == {"get_health_summary", "get_radiation_dose"}
    assert events[-1][1]["ungrounded_numbers"] == []


def test_chat_emergency_comes_first_even_if_llm_down(client, broken_llm):
    broken_llm([LLMUnavailable("connection refused")])
    events = _chat(client, "Göğsümde baskı var ve nefes darlığı çekiyorum")
    names = [n for n, _ in events]
    assert names[:2] == ["meta", "emergency"]
    assert set(events[1][1]["matched_symptoms"]) == {"chest_pain", "breathing"}
    assert "error" in names and dict(events)["error"]["code"] == "llm_unavailable"
    done = events[-1][1]
    assert done["degraded"] is True and done["finish_reason"] == "llm_unavailable"
    assert "Olası acil belirti" in done["message"] and "çevrim dışı" in done["message"]


def test_chat_system_prompt_rules(client, broken_llm):
    fake = broken_llm(["Merhaba."])
    _chat(client, "selam", as_of="2026-10-10")
    system = fake.requests[0]["messages"][0]["content"]
    for rule in ("do not diagnose", "Numbers come only from tools", "uncertainty", "emergency protocol", "user's language"):
        assert rule.lower() in system.lower(), rule
    assert "AST-02" in system and "2026-10-10" in system and "mission day 145" in system
