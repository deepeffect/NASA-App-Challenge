"""Paylaşım (sadece artar) ve gizlilik filtresi (gemide, Dünya'ya gitmeden önce)."""

import json

import pytest

from app.models.tables import CheckinSession
from app.personal.earth_view import earth_checkin_view, earth_day_view
from app.personal.evaluate import SHARE_LEVELS
from app.personal.privacy import earth_day
from app.personal.view import build_day_view

from .conftest import login

PRIVATE = ("beh_mood_score", "beh_stress_score")
EN = {"Accept-Language": "en"}


def finished(series, notes=None, share=None) -> CheckinSession:
    return CheckinSession(
        astronaut_id=series.meta.id, day_index=series.today_index, mission_day=series.days[-1].mission_day,
        notes=notes or [], done=True, share=share,
    )


# ---------------------------------------------------------------- gizlilik filtresi
def test_unshared_days_never_carry_mood_or_stress(dataset, catalog) -> None:
    """Paylaşılmamış hiçbir günün Dünya kaydında ruh hali / stres (değer, kod, davranışsal skor) yok."""
    mood_codes = {"MOOD_CONNECT"}  # sadece ruh haline bağlı çözüm
    for a in dataset.astronauts:
        for i in range(len(a.days)):
            rec = earth_day(catalog, a, i)
            blob = rec.model_dump_json()
            assert not any(col in blob for col in PRIVATE), (a.meta.id, i)
            assert "behavioral" not in rec.area_scores and rec.behavioral_hidden
            assert not mood_codes & {t.code for t in rec.todo}, (a.meta.id, i)
            assert rec.checkin is None


def test_ground_on_earth_uses_visible_readings_only(dataset, catalog) -> None:
    for a in dataset.astronauts:
        for i in range(len(a.days)):
            rec = earth_day(catalog, a, i)
            assert rec.ground == any(r.level == 2 for r in rec.readings.values())
            assert rec.status == max(a.days[i].health_status, int(rec.ground))


def test_masked_items_are_counted_not_named(dataset, catalog) -> None:
    total_masked = 0
    for a in dataset.astronauts:
        for i, day in enumerate(a.days):
            rec = earth_day(catalog, a, i)
            assert len(rec.todo) + rec.todo_masked_count == len(day.self_care)
            total_masked += rec.todo_masked_count
    assert total_masked > 0


@pytest.mark.parametrize("share", ["scores", "full"])
def test_shared_day_shows_mood_and_stress(dataset, catalog, share) -> None:
    a = dataset.by_id()["A003"]
    rec = earth_day(catalog, a, a.today_index, finished(a, share=share))
    assert set(PRIVATE) <= rec.readings.keys() and "behavioral" in rec.area_scores and not rec.behavioral_hidden
    # paylaşım sadece o güne aittir: önceki gün hâlâ gizli
    assert PRIVATE[0] not in earth_day(catalog, a, a.today_index - 1).readings


def test_checkin_payload_per_share_level(dataset, catalog) -> None:
    a = dataset.by_id()["A003"]
    notes = [
        {"topic": "Sleep", "topic_key": "sleep", "text": "badly", "flag": True, "urgent": False},
        {"topic": "Symptoms", "topic_key": "symptoms", "text": "chest pain", "flag": True, "urgent": True},
    ]
    assert earth_day(catalog, a, a.today_index, CheckinSession(astronaut_id="A003", day_index=29, mission_day=30, notes=notes)).checkin is None
    private = earth_day(catalog, a, a.today_index, finished(a, notes)).checkin
    assert private.model_dump() == {"share": "private", "notes": []}
    scores = earth_day(catalog, a, a.today_index, finished(a, notes, "scores")).checkin
    assert [n.model_dump() for n in scores.notes] == [
        {"topic_key": "sleep", "flag": True, "text": None}, {"topic_key": "symptoms", "flag": True, "text": None}]
    full = earth_day(catalog, a, a.today_index, finished(a, notes, "full"))
    assert [n.text for n in full.checkin.notes] == ["badly", "chest pain"]
    blob = full.model_dump_json()
    assert "urgent" not in blob and "cmo" not in blob.lower() and "messages" not in blob  # acil/CMO bilgisi asla


def test_earth_view_from_record_equals_ship_side_earth_view(dataset, catalog) -> None:
    """Dünya sadece filtrelenmiş kayıttan ekran kurar; gemide hesaplanan Dünya görünümüyle aynıdır."""
    for a in dataset.astronauts:
        for i in range(len(a.days)):
            for lang in ("en", "tr") if i == a.today_index else ("en",):
                ours = earth_day_view(catalog, earth_day(catalog, a, i), lang)
                ref = build_day_view(catalog, a, i, lang, earth=True)
                assert ours == ref, (a.meta.id, i, lang)
    a = dataset.by_id()["A139"]
    for share in SHARE_LEVELS:
        rec = earth_day(catalog, a, a.today_index, finished(a, share=share))
        ref = build_day_view(catalog, a, a.today_index, "en", earth=True, shared=SHARE_LEVELS[share], share=share)
        assert earth_day_view(catalog, rec, "en") == ref


def test_earth_checkin_texts() -> None:
    assert earth_checkin_view(None, "en").text == "No completed check-in for this day."
    assert earth_checkin_view(None, "tr").text == "Bu gün için tamamlanmış bir check-in yok."


# ---------------------------------------------------------------- paylaşım API'si
def _finish_checkin(client, auth) -> dict:
    out = None
    for ans in ["Badly", "Low", "A lot", "None", "No"]:
        out = client.post("/api/checkin/turn", json={"answer": ans}, headers=auth).json()
    return out["checkin"]


def test_share_only_increases(ship_client) -> None:
    auth = {**login(ship_client, "A020"), **EN}
    r = ship_client.post("/api/checkin/share", json={"level": "scores"}, headers=auth)
    assert r.status_code == 409 and r.json()["code"] == "checkin_not_done"

    st = _finish_checkin(ship_client, auth)
    assert st["share"] == "private" and [o["enabled"] for o in st["share_options"]] == [True, True, True]
    assert st["share_note"] == "Earth sees only that you completed a check-in. Sharing cannot be undone."

    st = ship_client.post("/api/checkin/share", json={"level": "scores"}, headers=auth).json()
    assert st["share"] == "scores" and not st["can_reset"]
    assert [(o["level"], o["selected"], o["enabled"]) for o in st["share_options"]] == [
        ("private", False, False), ("scores", True, True), ("full", False, True)]

    r = ship_client.post("/api/checkin/share", json={"level": "private"}, headers=auth)
    assert r.status_code == 409 and r.json()["code"] == "share_downgrade"
    assert ship_client.post("/api/checkin/share", json={"level": "scores"}, headers=auth).status_code == 200  # aynı seviye
    assert ship_client.post("/api/checkin/share", json={"level": "full"}, headers=auth).json()["share"] == "full"
    for lower in ("private", "scores"):
        assert ship_client.post("/api/checkin/share", json={"level": lower}, headers=auth).status_code == 409

    r = ship_client.post("/api/checkin/reset", headers=auth)  # paylaşılmış → baştan başlanamaz
    assert r.status_code == 409 and r.json()["code"] == "reset_locked"
    day = ship_client.get("/api/me/days/30", headers=auth).json()
    assert day["share"] == "full"


def test_share_texts_in_turkish(ship_client) -> None:
    auth = login(ship_client, "A021")
    _finish_checkin(ship_client, auth)
    st = ship_client.post("/api/checkin/share?lang=tr", json={"level": "full"}, headers=auth).json()
    assert [o["label"] for o in st["share_options"]] == ["Gizli tut", "Sadece skorlar", "Her şey"]
    assert st["share_note"].endswith("Paylaşım geri alınamaz.")
    assert "Dünya'ya gönderilmez" in st["share_cmo_note"]


def test_share_rejects_unknown_level(ship_client) -> None:
    auth = login(ship_client, "A022")
    assert ship_client.post("/api/checkin/share", json={"level": "public"}, headers=auth).status_code == 422


def test_record_json_is_plain(dataset, catalog) -> None:
    """Kayıt düz JSON (downlink'te olduğu gibi taşınır)."""
    a = dataset.by_id()["A000"]
    assert json.loads(earth_day(catalog, a, 0).model_dump_json())["astronaut_id"] == "A000"
