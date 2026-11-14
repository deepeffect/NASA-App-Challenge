"""Giriş ve yetki: ayrı hata mesajları, token kapsamı, 403 durumları, iki istasyon."""

import pytest

from .conftest import login

EN = {"Accept-Language": "en"}
TR = {"Accept-Language": "tr"}


def test_ship_hint(ship_client) -> None:
    h = ship_client.get("/api/auth/hint", headers=EN).json()
    assert h["station"] == "ship" and h["astronauts"] == {"first_id": "A000", "last_id": "A199", "count": 200}
    assert h["text"] == "Astronauts: A000 to A199 (200 accounts); the password is the same as the ID."
    assert ship_client.get("/api/auth/hint?lang=tr").json()["text"].startswith("Astronotlar: A000 – A199 (200 hesap)")


@pytest.mark.parametrize(("uid", "pw"), [("A003", "A003"), (" a003 ", "a003"), ("a003", "A003 ")])
def test_ship_login_case_insensitive(ship_client, uid, pw) -> None:
    r = ship_client.post("/api/auth/login", json={"id": uid, "password": pw})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["kind"] == "astronaut" and body["astronaut_id"] == "A003" and body["home_path"] == "/me"
    me = ship_client.get("/api/auth/me", headers={"Authorization": f"Bearer {body['token']}"}).json()
    assert me == {"kind": "astronaut", "subject": "A003", "astronaut_id": "A003", "station": "ship", "read_only": False}


@pytest.mark.parametrize(
    ("payload", "status", "code", "en_text"),
    [
        ({"id": "  ", "password": "x"}, 400, "empty_id", "Enter an ID."),
        (
            {"id": "A999", "password": "A999"},
            401,
            "unknown_id",
            "No account has the ID A999. Astronaut IDs run from A000 to A199.",
        ),
        (
            {"id": "A003", "password": "A004"},
            401,
            "wrong_password",
            "Wrong password. In this demo the password is the same as the ID.",
        ),
        ({"id": "earth", "password": "earth"}, 403, "wrong_station", "The Earth base account is not used on the ship."),
    ],
)
def test_ship_login_errors(ship_client, payload, status, code, en_text) -> None:
    r = ship_client.post("/api/auth/login", json=payload, headers=EN)
    assert r.status_code == status and r.json()["code"] == code
    assert r.json()["detail"].startswith(en_text)
    tr = ship_client.post("/api/auth/login", json=payload, headers=TR).json()["detail"]
    assert tr != r.json()["detail"]  # Türkçe metin ayrı


def test_login_error_messages_in_turkish(ship_client) -> None:
    r = ship_client.post("/api/auth/login?lang=tr", json={"id": "X1", "password": ""})
    assert r.json()["detail"] == "X1 kimlikli bir hesap yok. Astronot kimlikleri A000 ile A199 arasındadır."


def test_token_required_and_validated(ship_client) -> None:
    r = ship_client.get("/api/me", headers=EN)
    assert r.status_code == 401 and r.json()["code"] == "auth_required"
    r = ship_client.get("/api/me", headers={**EN, "Authorization": "Bearer not.a-token"})
    assert r.status_code == 401 and r.json()["code"] == "auth_invalid"
    good = login(ship_client, "A003")["Authorization"]
    body, sig = good.split(" ", 1)[1].split(".")
    r = ship_client.get("/api/me", headers={"Authorization": f"Bearer {body}.{sig[:-2]}xx"})
    assert r.status_code == 401


def test_token_limited_to_own_astronaut(ship_client) -> None:
    auth = login(ship_client, "A003")
    assert ship_client.get("/api/personal/A003", headers=auth).status_code == 200
    assert ship_client.get("/api/personal/a003/days/30", headers=auth).status_code == 200
    for path in ["/api/personal/A004", "/api/personal/A004/days/1"]:
        r = ship_client.get(path, headers={**auth, **EN})
        assert r.status_code == 403 and r.json()["code"] == "forbidden_other_astronaut", path


def test_me_overview_and_days(ship_client) -> None:
    auth = login(ship_client, "A000")
    ov = ship_client.get("/api/me", headers={**auth, **EN}).json()
    assert ov["astronaut"]["id"] == "A000" and ov["today"] == 30 and len(ov["strip"]) == 30
    assert ov["astronaut"]["mission_label"] == "Mars surface" and ov["astronaut"]["first_mission_day"] == 126
    today = ship_client.get("/api/me/days/30", headers={**auth, **EN}).json()
    assert today["is_today"] and today["day_label"] == "Day 30 of 30 · mission day 155"
    tr = ship_client.get("/api/me/days/30?lang=tr", headers=auth).json()
    assert tr["day_label"] == "30 günün 30. günü · görev günü 155"
    assert ship_client.get("/api/me/days/31", headers=auth).status_code == 404
    assert ship_client.get("/api/me/days/0", headers=auth).status_code == 422


def test_catalog_is_public_and_bilingual(ship_client, earth_client) -> None:
    for c in (ship_client, earth_client):
        cat = c.get("/api/catalog?lang=en").json()
        assert len(cat["indicators"]) == 18 and len(cat["solutions"]) == 14 and cat["verified"] is False
        assert cat["threshold_note"] == "Ranges come from the simulated dataset and have not been medically validated."
    assert ship_client.get("/api/catalog?lang=tr").json()["statuses"] == ["Normal", "Dikkat", "Rahatsız"]


# ---------------------------------------------------------------- Dünya üssü
def test_earth_hint_and_login(earth_client) -> None:
    h = earth_client.get("/api/auth/hint", headers=EN).json()
    assert h == {"station": "earth", "astronauts": None, "earth_id": "EARTH", "text": "Earth base: EARTH, password EARTH."}
    auth = login(earth_client, "earth", "Earth")
    me = earth_client.get("/api/auth/me", headers=auth).json()
    assert me["kind"] == "earth" and me["read_only"] is True and me["station"] == "earth"


@pytest.mark.parametrize(
    ("payload", "status", "code"),
    [
        ({"id": "A003", "password": "A003"}, 403, "wrong_station"),
        ({"id": "EARTH", "password": "MARS"}, 401, "wrong_password"),
        ({"id": "MOON", "password": "MOON"}, 401, "unknown_id"),
        ({"id": "", "password": ""}, 400, "empty_id"),
    ],
)
def test_earth_login_errors(earth_client, payload, status, code) -> None:
    r = earth_client.post("/api/auth/login", json=payload)
    assert r.status_code == status and r.json()["code"] == code


def test_tokens_do_not_cross_stations(ship_client, earth_client) -> None:
    ship_token = login(ship_client, "A003")
    earth_token = login(earth_client, "EARTH")
    assert earth_client.get("/api/auth/me", headers=ship_token).status_code == 401
    assert ship_client.get("/api/auth/me", headers=earth_token).status_code == 401


def test_earth_writes_are_forbidden(earth_client) -> None:
    auth = login(earth_client, "EARTH")
    for path in ["/api/checkin/turn", "/api/checkin/share", "/api/actions/done", "/api/auth/logout"]:
        r = earth_client.post(path, json={}, headers={**auth, **EN})
        assert r.status_code == 403 and r.json()["code"] == "read_only", path


def test_earth_has_no_astronaut_screen(earth_client) -> None:
    assert earth_client.get("/api/me").status_code == 404
