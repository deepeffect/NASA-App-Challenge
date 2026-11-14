"""Dil: ?lang= (veya gövdedeki lang) > Accept-Language > tr. Bütün metin tabloları TR ve EN."""

import pytest

from app.i18n import MESSAGES
from app.personal import checkin_script, earth_view, view

from .conftest import login


def test_header_selects_language_and_param_wins(ship_client) -> None:
    get = lambda **kw: ship_client.get("/api/catalog", **kw).json()["statuses"]  # noqa: E731
    assert get() == ["Normal", "Dikkat", "Rahatsız"]  # varsayılan tr
    assert get(headers={"Accept-Language": "en-US,en;q=0.9"}) == ["Normal", "Needs attention", "Unwell"]
    assert get(headers={"Accept-Language": "tr-TR"}) == ["Normal", "Dikkat", "Rahatsız"]
    assert ship_client.get("/api/catalog?lang=en", headers={"Accept-Language": "tr"}).json()["statuses"][1] == "Needs attention"


def test_checkin_turn_language_from_header(ship_client) -> None:
    auth = login(ship_client, "A070")
    r = ship_client.post("/api/checkin/turn", json={"answer": "Well"}, headers={**auth, "Accept-Language": "en"}).json()
    assert r["next"]["text"] == "How is your mood today?"
    r = ship_client.post("/api/checkin/turn", json={"answer": "İyi"}, headers={**auth, "Accept-Language": "tr"}).json()
    assert r["next"]["text"] == "Bugün sizi strese sokan bir şey var mı?"


@pytest.mark.parametrize(("lang", "text"), [("en", "Invalid request: level"), ("tr", "İstek geçersiz: level")])
def test_validation_errors_are_localized(ship_client, lang, text) -> None:
    auth = login(ship_client, "A071")
    r = ship_client.post("/api/checkin/share", json={"level": "x"}, headers={**auth, "Accept-Language": lang})
    assert r.status_code == 422 and r.json()["code"] == "validation_error" and r.json()["detail"] == text
    assert r.json()["errors"][0]["loc"] == ["body", "level"]


@pytest.mark.parametrize("fixture", ["ship_client", "earth_client"])
def test_unknown_address_is_localized(request, fixture) -> None:
    c = request.getfixturevalue(fixture)
    r = c.get("/api/nowhere", headers={"Accept-Language": "en"})
    assert r.status_code == 404 and r.json() == {"detail": "There is no such address at this station.", "code": "not_found"}
    assert c.get("/api/nowhere?lang=tr").json()["detail"] == "Bu istasyonda böyle bir adres yok."


def test_legacy_endpoints_fall_back_to_accept_language(client) -> None:
    """Eski uçlar (synthetic): lang yoksa Accept-Language."""
    assert client.get("/api/astronauts/NOPE/summary").json()["detail"] == "Astronot bulunamadı: NOPE"
    assert client.get("/api/astronauts/NOPE/summary", headers={"Accept-Language": "en"}).json()["detail"] == "Astronaut not found: NOPE"
    body = {"astronaut_id": "AST-01", "mood": 3, "stress": 3, "sleep_quality": 3, "note": "chest pain since morning"}
    r = client.post("/api/checkin", json=body, headers={"Accept-Language": "en"})
    assert r.status_code == 201 and r.json()["emergency"]["message"].startswith("Possible emergency")
    r = client.post("/api/checkin", json={**body, "lang": "tr"}, headers={"Accept-Language": "en"})
    assert r.json()["emergency"]["message"].startswith("Olası acil belirti")


def _complete(table: dict, name: str) -> None:
    for key, texts in table.items():
        assert set(texts) == {"tr", "en"}, f"{name}.{key}"
        assert all(isinstance(v, str) and v.strip() for v in texts.values()), f"{name}.{key}"


def test_every_text_table_has_both_languages() -> None:
    _complete(MESSAGES, "i18n.MESSAGES")
    _complete(view.TEXTS, "view.TEXTS")
    _complete(checkin_script.TEXTS, "checkin_script.TEXTS")
    _complete(earth_view.TEXTS, "earth_view.TEXTS")
    for topic in checkin_script.TOPICS:
        for field in (topic.name, topic.q, topic.options):
            assert set(field) == {"tr", "en"}, topic.key
        assert len(topic.options["tr"]) == len(topic.options["en"]), topic.key


def test_format_placeholders_match_between_languages() -> None:
    import string

    def fields(s: str) -> set[str]:
        return {f for _, f, _, _ in string.Formatter().parse(s) if f}

    for name, table in [("i18n", MESSAGES), ("view", view.TEXTS), ("checkin", checkin_script.TEXTS)]:
        for key, texts in table.items():
            assert fields(texts["tr"]) == fields(texts["en"]), f"{name}.{key}"
