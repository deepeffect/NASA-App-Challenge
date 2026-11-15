"""Asistan katmanı ("Asistana sor" → LLM ekibinin API'si): gövde sözleşmesi, rozet kaynakları, Ollama yoluna düşme."""

import asyncio
import json

import httpx
import pytest
from sqlmodel import Session

from app.config import Settings
from app.llm.assistant_layer import ask_layer, build_body, to_record
from app.llm.types import LLMUnavailable
from app.personal.store import personal_data
from app.services import personal_chat

from .conftest import login
from .test_assistant import chat

LAYER_URL = "http://layer.test:8000/v1"


def series_of(app, aid: str):
    with Session(app.state.engine) as db:
        return personal_data(app.state.engine).series(db, aid)


def raw_records(settings: Settings, aid: str) -> list[dict]:
    raw = json.loads(settings.dataset_path.read_text(encoding="utf-8"))
    return sorted((r for r in raw["records"] if r["astronaut_id"] == aid), key=lambda r: r["mission_day"])


def layer_reply(text: str, sources: dict | None = None, intent: str = "data_question") -> dict:
    return {"id": "chatcmpl-x", "object": "chat.completion", "model": "ai-gambit-health",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
            "intent": intent, "sources": sources or {}}


def test_records_are_sent_exactly_as_in_dataset(ship_client, ship_app, ship_settings) -> None:
    series = series_of(ship_app, "A003")
    sent = [to_record("A003", d) for d in series.days]
    assert sent == raw_records(ship_settings, "A003")  # olduğu gibi, eskiden yeniye; son kayıt = bugün
    body = build_body(ship_settings, series, [{"role": "system", "content": "x"}, {"role": "user", "content": "hi"}])
    assert body["model"] == "ai-gambit-health" and body["stream"] is False
    assert body["messages"] == [{"role": "user", "content": "hi"}]  # sistem promptu gönderilmez
    assert body["astronaut"] == {"astronaut_id": "A003", "age": series.meta.age, "sex": series.meta.sex, "mission": series.meta.mission}
    assert len(body["records"]) == 30 and body["records"][-1]["mission_day"] == series.days[-1].mission_day


def test_ask_layer_parses_answer_and_maps_failures(ship_client, ship_app, ship_settings) -> None:
    series = series_of(ship_app, "A003")
    s = ship_settings.model_copy(update={"assistant_layer_url": LAYER_URL})
    seen: dict = {}

    def ok(request: httpx.Request) -> httpx.Response:
        seen["url"], seen["body"] = str(request.url), json.loads(request.content)
        return httpx.Response(200, json=layer_reply("Sleep is 5.2 h [D1].", {"D1": {"type": "data", "label": "Sleep duration", "value": 5.2, "unit": "h", "status": "YELLOW"}, "bad": "x"}))

    ans = asyncio.run(ask_layer(s, series, [{"role": "user", "content": "How is my sleep?"}], transport=httpx.MockTransport(ok)))
    assert seen["url"] == f"{LAYER_URL}/chat/completions" and seen["body"]["astronaut"]["astronaut_id"] == "A003"
    assert ans.text == "Sleep is 5.2 h [D1]." and list(ans.sources) == ["D1"] and ans.intent == "data_question"

    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    for transport in (httpx.MockTransport(refuse),
                      httpx.MockTransport(lambda r: httpx.Response(503, json={"detail": "LLM backend unreachable"})),
                      httpx.MockTransport(lambda r: httpx.Response(200, text="not json")),
                      httpx.MockTransport(lambda r: httpx.Response(200, json=layer_reply("  ")))):
        with pytest.raises(LLMUnavailable):
            asyncio.run(ask_layer(s, series, [{"role": "user", "content": "hi"}], transport=transport))


def test_chat_uses_layer_and_returns_sources(ship_client, ship_app, ship_settings, monkeypatch) -> None:
    today = raw_records(ship_settings, "A003")[-1]
    sleep = today["beh_sleep_h"]
    calls: list[dict] = []

    async def fake(settings, series, history, **kw):
        calls.append({"aid": series.meta.id, "history": history})
        from app.llm.assistant_layer import LayerAnswer

        return LayerAnswer(
            text=f"Your sleep duration is {sleep} h [D1]. Keep a regular schedule [K1]. Invented 987.6 bpm.",
            sources={"D1": {"type": "data", "label": "Sleep duration", "value": sleep, "unit": "h", "status": "GREEN"},
                     "K1": {"type": "knowledge", "label": "Sleep hygiene", "text": "Regular sleep schedule helps."}},
            intent="data_question",
        )

    monkeypatch.setattr(ship_settings, "assistant_layer_url", LAYER_URL)
    monkeypatch.setattr(personal_chat, "ask_layer", fake)
    evs = chat(ship_client, login(ship_client, "A003"), "How is my sleep?", lang="en")
    assert calls and calls[0]["aid"] == "A003" and calls[0]["history"][-1] == {"role": "user", "content": "How is my sleep?"}
    assert evs[0][0] == "meta" and evs[0][1]["provider"] == "assistant_layer" and evs[0][1]["model"] == "ai-gambit-health"
    assert not [n for n, _ in evs if n in ("tool_call", "error")]
    done = next(d for n, d in evs if n == "done")
    assert done["finish_reason"] == "stop" and not done["degraded"]
    assert "".join(d["text"] for n, d in evs if n == "token") == done["message"]
    assert done["sources"]["D1"] == {"type": "data", "label": "Sleep duration", "value": sleep, "unit": "h", "status": "GREEN", "text": None}
    assert done["sources"]["K1"]["type"] == "knowledge" and done["sources"]["K1"]["text"].startswith("Regular")
    assert done["ungrounded_numbers"] == ["987.6"]  # kayıtlarda / kaynaklarda olmayan sayı işaretlenir, [D1] etiketi sayılmaz


def test_chat_falls_back_to_llm_path_when_layer_is_down(ship_client, ship_settings, monkeypatch) -> None:
    async def down(settings, series, history, **kw):
        raise LLMUnavailable("Asistan katmanına ulaşılamadı")

    monkeypatch.setattr(ship_settings, "assistant_layer_url", LAYER_URL)
    monkeypatch.setattr(personal_chat, "ask_layer", down)
    evs = chat(ship_client, login(ship_client, "A003"), "How am I today?", lang="en")
    done = next(d for n, d in evs if n == "done")
    assert [d["name"] for n, d in evs if n == "tool_call"] == ["get_today_summary"]  # bugünkü yol (mock LLM + tool'lar)
    assert "day 30 of 30" in done["message"] and done["sources"] == {} and not done["degraded"]


def test_layer_is_off_by_default_and_emergency_still_rule_based(ship_client, ship_app, ship_settings, monkeypatch) -> None:
    assert Settings().assistant_layer_url is None

    async def fake(settings, series, history, **kw):
        from app.llm.assistant_layer import LayerAnswer

        return LayerAnswer(text="Start the onboard medical emergency protocol and contact the Crew Medical Officer now.", intent="emergency")

    monkeypatch.setattr(ship_settings, "assistant_layer_url", LAYER_URL)
    monkeypatch.setattr(personal_chat, "ask_layer", fake)
    evs = chat(ship_client, login(ship_client, "A005"), "I have chest pain and I can't breathe", lang="en")
    names = [n for n, _ in evs]
    assert names.index("emergency") < names.index("token")  # kural tabanlı acil kutusu katmandan ÖNCE gelir
    assert next(d for n, d in evs if n == "emergency")["cmo_notified"] is True
