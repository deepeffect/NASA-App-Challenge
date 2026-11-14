""""Asistana sor" (yeni mod): sadece kendi verisi, acil belirti → CMO (olumsuzlama ayırt edilir), tool'lar."""

import json

import pytest
from sqlmodel import Session, func, select

from app.llm.personal_tools import personal_registry
from app.llm.tools import ToolContext
from app.models.tables import CmoNotification, OutboxEvent
from app.safety.emergency import detect_emergency, get_protocol

from .conftest import login


def sse_events(text: str) -> list[tuple[str, dict]]:
    out = []
    for block in text.replace("\r\n", "\n").split("\n\n"):
        name = data = None
        for line in block.splitlines():
            if line.startswith("event:"):
                name = line[6:].strip()
            elif line.startswith("data:"):
                data = line[5:].strip()
        if name and data:
            out.append((name, json.loads(data)))
    return out


def chat(client, auth, text, **body):
    r = client.post("/api/chat", json={"messages": [{"role": "user", "content": text}], **body}, headers=auth)
    assert r.status_code == 200, r.text
    return sse_events(r.text)


def cmo_count(app, aid) -> int:
    with Session(app.state.engine) as db:
        return db.exec(select(func.count()).select_from(CmoNotification).where(CmoNotification.astronaut_id == aid)).one()


def test_chat_uses_own_data_and_numbers_are_grounded(ship_client) -> None:
    auth = login(ship_client, "A003")
    evs = chat(ship_client, auth, "How am I today?", lang="en")
    names = [n for n, _ in evs]
    assert names[0] == "meta" and evs[0][1]["astronaut_id"] == "A003"
    calls = [d for n, d in evs if n == "tool_call"]
    assert calls and calls[0]["name"] == "get_today_summary"
    assert all(d["ok"] for n, d in evs if n == "tool_result")
    done = next(d for n, d in evs if n == "done")
    assert "day 30 of 30" in done["message"] and done["ungrounded_numbers"] == []


def test_chat_turkish_sleep_question(ship_client) -> None:
    auth = login(ship_client, "A003")
    evs = chat(ship_client, auth, "Son günlerde uykum nasıl?", lang="tr")
    call = next(d for n, d in evs if n == "tool_call")
    assert call["name"] == "get_recent_readings" and call["arguments"]["cols"] == ["beh_sleep_h"]
    assert next(d for n, d in evs if n == "done")["message"].startswith("Son ölçümler: Uyku")


def test_chat_rejects_other_astronaut_and_requires_login(ship_client) -> None:
    auth = login(ship_client, "A003")
    r = ship_client.post("/api/chat", json={"astronaut_id": "A004", "messages": [{"role": "user", "content": "hi"}]}, headers=auth)
    assert r.status_code == 403 and r.json()["code"] == "forbidden_other_astronaut"
    assert ship_client.post("/api/chat", json={"messages": [{"role": "user", "content": "hi"}]}).status_code == 401


def test_tools_ignore_astronaut_argument(ship_app) -> None:
    from sqlmodel import Session as S

    reg = personal_registry()
    ctx = ToolContext(astronaut_id="A003", lang="en", session_factory=lambda: S(ship_app.state.engine))
    for name, args in [("get_today_summary", {"astronaut_id": "A004"}), ("get_todo", {"astronaut_id": "A004"}),
                       ("get_recent_readings", {"astronaut_id": "A004", "cols": ["beh_sleep_h"], "days": 3})]:
        res = reg.execute(ctx, name, args)
        assert res.ok and res.data["astronaut_id"] == "A003", name
    assert len(reg.execute(ctx, "get_recent_readings", {"cols": ["beh_sleep_h"], "days": 3}).data["readings"][0]["points"]) == 3
    assert not reg.execute(ctx, "get_recent_readings", {"cols": ["nope"]}).ok
    assert len(reg.execute(ctx, "get_selfcare_solutions", {}).data["solutions"]) == 14


def test_chat_emergency_notifies_cmo_on_ship_only(ship_client, ship_app) -> None:
    auth = login(ship_client, "A060")
    with Session(ship_app.state.engine) as db:
        outbox_before = db.exec(select(func.count()).select_from(OutboxEvent)).one()
    evs = chat(ship_client, auth, "I have sudden chest pain", lang="en")
    em = next(d for n, d in evs if n == "emergency")
    assert em["cmo_notified"] and em["message"].startswith("Crew medical officer told.")
    assert cmo_count(ship_app, "A060") == 1
    with Session(ship_app.state.engine) as db:
        row = db.exec(select(CmoNotification).where(CmoNotification.astronaut_id == "A060")).one()
        assert row.source == "chat" and row.text == "I have sudden chest pain"
        assert db.exec(select(func.count()).select_from(OutboxEvent)).one() == outbox_before  # Dünya'ya olay yok


@pytest.mark.parametrize("text", ["no chest pain, just tired", "Göğüs ağrım yok, sadece yorgunum", "I do not have chest pain"])
def test_chat_negated_symptom_does_not_trigger(ship_client, ship_app, text) -> None:
    auth = login(ship_client, "A061")
    before = cmo_count(ship_app, "A061")
    evs = chat(ship_client, auth, text)
    assert "emergency" not in [n for n, _ in evs]
    assert cmo_count(ship_app, "A061") == before


@pytest.mark.parametrize(
    ("text", "triggers"),
    [
        ("göğüs ağrısı yok", False),
        ("göğüs ağrısı var", True),
        ("no chest pain but I fainted", True),
        ("hiç bayılmadım, göğüs ağrısı yok", False),
        ("I don't have chest pain", False),
        ("without chest pain today", False),
        ("chest pain? no", True),  # belirsiz → güvenlik için tetikler
    ],
)
def test_negation_aware_detection(text, triggers) -> None:
    assert (detect_emergency(text, negation_aware=True) is not None) == triggers


def test_legacy_detection_still_over_triggers() -> None:
    assert detect_emergency("göğüs ağrısı yok") is not None  # eski ekranlar: olumsuzlama ayırt edilmez


def test_protocol_cmo_decides_about_earth() -> None:
    assert "Gerekirse Dünya ile iletişime geçme kararını CMO verir." in get_protocol("tr").steps
    assert "If needed, the CMO decides whether to contact Earth." in get_protocol("en").steps
