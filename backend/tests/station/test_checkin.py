"""Check-in: scripted akış (EN ve TR), API, sadece bugün, baştan başla, acil belirti → CMO, LLM modları."""

import asyncio

import pytest
from sqlmodel import Session, select

from app.config import Settings
from app.models.tables import CmoNotification
from app.personal.checkin_context import build_context
from app.personal.checkin_script import TOPIC_BY_KEY, FlowState, apply_turn, assistant_turn, grade
from app.services.checkin import run_mode

from .conftest import login

EN = {"Accept-Language": "en"}


def play(cat, series, answers, lang):
    st = FlowState.initial(lang)
    i = series.today_index
    for text in answers:
        ctx = build_context(cat, series, i, lang, [*st.msgs, {"who": "me", "text": text}], st.step, text)
        apply_turn(st, text, assistant_turn(ctx, lang), lang)
    return st


# ---------------------------------------------------------------- Türkçe notlama
@pytest.mark.parametrize(
    ("topic", "answer", "expected"),
    [
        ("sleep", "İyi", "good"),
        ("sleep", "İdare eder", "mid"),
        ("sleep", "Kötü", "bad"),
        ("sleep", "pek iyi değil", "bad"),
        ("sleep", "gece üç kez uyandım", "bad"),
        ("sleep", "fena değil", "mid"),
        ("sleep", "derin uyudum", "good"),
        ("mood", "Şöyle böyle", "mid"),
        ("mood", "Düşük", "bad"),
        ("mood", "ailemi özledim", "bad"),
        ("mood", "harika", "good"),
        ("stress", "Hayır", "good"),
        ("stress", "Biraz", "mid"),
        ("stress", "Çok", "bad"),
        ("stress", "çok değil", "good"),
        ("stress", "iş yükü çok fazla", "bad"),
        ("symptoms", "Yok", "good"),
        ("symptoms", "hiçbir şey yok", "good"),
        ("symptoms", "baş ağrısı", "bad"),
        ("other", "Hayır", "skip"),
        ("other", "CO2 temizleyici gürültülü", "mid"),
    ],
)
def test_turkish_grading(topic, answer, expected) -> None:
    assert grade(TOPIC_BY_KEY[topic], answer, "tr") == expected


@pytest.mark.parametrize(
    ("lang", "topic", "answer", "expected"),
    [("tr", "sleep", "Badly", "bad"), ("en", "sleep", "kötü", "bad"), ("tr", "symptoms", "none", "good"), ("en", "stress", "hayır", "good")],
)
def test_other_language_answer_falls_back(lang, topic, answer, expected) -> None:
    assert grade(TOPIC_BY_KEY[topic], answer, lang) == expected


def test_scripted_flow_turkish(dataset, catalog) -> None:
    series = dataset.by_id()["A003"]
    st = play(catalog, series, ["Kötü", "Düşük", "Çok", "göğsümde ağrı var", "Hayır"], "tr")
    assert st.msgs[0]["text"] == "Dün gece nasıl uyudunuz?"
    assert st.done and st.cmo
    assert [(n["topic_key"], n["flag"], n["urgent"]) for n in st.notes] == [
        ("sleep", True, False), ("mood", True, False), ("stress", True, False), ("symptoms", True, True)]
    replies = [m["text"] for m in st.msgs if m["who"] == "bot"]
    assert "Gemideki sağlık sorumlusu şimdi bilgilendiriliyor." in replies[-4]
    assert replies[-2] == "Tamam."
    assert replies[-1] == "Check-in tamamlandı. Bugün işaretlenenler: uyku, ruh hali, stres, belirtiler."
    sleep_reply = replies[1]
    assert sleep_reply.startswith("Not edildi.") and "uyku ortalaması" in sleep_reply and "saat" in sleep_reply


def test_scripted_flow_english_quick_replies(dataset, catalog) -> None:
    series = dataset.by_id()["A000"]
    st = play(catalog, series, ["Well", "Good", "No", "None", "No"], "en")
    assert st.done and not st.cmo
    assert st.msgs[-1]["text"] == "Check-in complete. Nothing flagged."
    assert [n["topic"] for n in st.notes] == ["Sleep", "Mood", "Stress", "Symptoms"]  # 'other' = skip


# ---------------------------------------------------------------- API
def test_checkin_api_flow(ship_client, ship_app) -> None:
    auth = {**login(ship_client, "A010"), **EN}
    st = ship_client.get("/api/checkin", headers=auth).json()
    assert st["editable"] and not st["started"] and st["messages"] == [{"who": "bot", "text": "How did you sleep last night?"}]
    assert st["options"] == ["Well", "OK", "Badly"] and st["day"] == 30

    r = ship_client.post("/api/checkin/turn", json={"answer": "  "}, headers=auth)
    assert r.status_code == 400 and r.json()["code"] == "empty_answer"

    out = None
    for ans in ["OK", "So-so", "A little", "I feel dizzy", "No"]:
        r = ship_client.post("/api/checkin/turn", json={"answer": ans}, headers=auth)
        assert r.status_code == 200, r.text
        out = r.json()
        assert set(out) == {"reply", "note", "next", "done", "checkin"}
    assert out["done"] and out["next"] is None and out["note"] is None  # 'No' → skip
    st = out["checkin"]
    assert st["done"] and st["share"] == "private" and st["can_reset"] and st["cmo_notified"]
    assert st["cmo_notice"]["title"] == "Crew medical officer told."
    assert st["messages"][-1]["text"] == "Check-in complete. Flagged for today: symptoms."

    r = ship_client.post("/api/checkin/turn", json={"answer": "more"}, headers=auth)
    assert r.status_code == 409 and r.json()["code"] == "checkin_done"

    with Session(ship_app.state.engine) as s:
        cmo = s.exec(select(CmoNotification).where(CmoNotification.astronaut_id == "A010")).all()
    assert len(cmo) == 1 and cmo[0].source == "checkin" and cmo[0].text == "I feel dizzy" and cmo[0].day_index == 29

    st = ship_client.post("/api/checkin/reset", headers=auth).json()  # private → baştan başlanabilir
    assert not st["started"] and not st["done"] and len(st["messages"]) == 1
    with Session(ship_app.state.engine) as s:  # CMO kaydı silinmez
        assert len(s.exec(select(CmoNotification).where(CmoNotification.astronaut_id == "A010")).all()) == 1


def test_cmo_notice_in_turkish(ship_client) -> None:
    auth = login(ship_client, "A011")
    for ans in ["İyi", "İyi", "Hayır", "nefes almakta zorlanıyorum"]:
        st = ship_client.post("/api/checkin/turn?lang=tr", json={"answer": ans}, headers=auth).json()["checkin"]
    assert st["cmo_notified"] and st["cmo_notice"]["title"] == "Gemideki sağlık sorumlusu bilgilendirildi."
    assert "Dünya'ya gönderilmedi" in st["cmo_notice"]["text"]


def test_past_days_are_read_only(ship_client) -> None:
    auth = login(ship_client, "A012")
    past = ship_client.get("/api/checkin/days/5", headers=auth).json()
    assert not past["is_today"] and not past["editable"] and past["messages"] == [] and past["options"] == []
    assert ship_client.get("/api/checkin/days/30", headers=auth).json()["editable"]
    assert ship_client.get("/api/checkin/days/31", headers=auth).status_code == 404


# ---------------------------------------------------------------- modlar
def _ctx(dataset, catalog, aid="A003", answer="Badly"):
    series = dataset.by_id()[aid]
    return build_context(catalog, series, series.today_index, "en", [], 0, answer)


def test_llm_mode_with_mock_follows_contract(dataset, catalog) -> None:
    ctx = _ctx(dataset, catalog)
    out, mode = asyncio.run(run_mode(Settings(checkin_mode="llm", llm_provider="mock"), ctx, "en"))
    assert mode == "llm" and out == assistant_turn(ctx, "en")


def test_auto_mode_falls_back_to_scripted_when_llm_unreachable(dataset, catalog) -> None:
    ctx = _ctx(dataset, catalog)
    s = Settings(checkin_mode="auto", llm_provider="openai", llm_base_url="http://127.0.0.1:9/v1", llm_timeout=5)
    out, mode = asyncio.run(run_mode(s, ctx, "en"))
    assert mode == "scripted" and out == assistant_turn(ctx, "en")


def test_llm_mode_failure_does_not_advance(dataset, catalog) -> None:
    ctx = _ctx(dataset, catalog)
    s = Settings(checkin_mode="llm", llm_provider="openai", llm_base_url="http://127.0.0.1:9/v1", llm_timeout=5)
    out, mode = asyncio.run(run_mode(s, ctx, "en"))
    assert out is None and mode == "llm"
    st = FlowState.initial("en")
    apply_turn(st, "Badly", out, "en")
    assert st.step == 0 and st.msgs[-1]["text"] == "That did not go through. Please answer again."


def test_llm_mode_never_handles_urgent_symptoms(dataset, catalog) -> None:
    series = dataset.by_id()["A003"]
    ctx = build_context(catalog, series, series.today_index, "en", [], 3, "chest pain")
    out, mode = asyncio.run(run_mode(Settings(checkin_mode="llm", llm_provider="mock"), ctx, "en"))
    assert out["note"]["urgent"] and "crew medical officer" in out["reply"]


def test_auto_mode_circuit_breaker_skips_dead_llm(dataset, catalog) -> None:
    """auto: bir hatadan sonra LLM bir süre denenmez → turlar beklemeden scripted."""
    import time

    ctx = _ctx(dataset, catalog)
    s = Settings(checkin_mode="auto", llm_provider="openai", llm_base_url="http://127.0.0.1:9/v2", llm_timeout=5)
    asyncio.run(run_mode(s, ctx, "en"))  # ilk hata devreyi açar
    t0 = time.monotonic()
    out, mode = asyncio.run(run_mode(s, ctx, "en"))
    assert mode == "scripted" and out == assistant_turn(ctx, "en") and time.monotonic() - t0 < 0.5
