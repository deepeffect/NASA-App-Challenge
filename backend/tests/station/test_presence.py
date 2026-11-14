"""Terminal varlığı: /me sinyali → gemide son görülme → downlink'e sadece durum değişimi (terminal.*) → Dünya.

Gizlilik: Dünya'ya sadece kimlik, çevrimiçi / çevrimdışı ve son sinyal zamanı gider; içerik yok.
"""

import time
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, col, select

from app.config import Settings
from app.downlink import outbox, presence
from app.main import create_app
from app.models.tables import OutboxEvent, TerminalPresence, as_utc

from .conftest import login, sqlite_url

TOKEN = "presence-link-token"
LINK = {"Authorization": f"Bearer {TOKEN}"}
TIMEOUT = 120


def ship_settings(db_path, **kw) -> Settings:
    # Denetim aralığı uzun: testler sweep()'i kendisi çağırır (açılıştaki ilk tur hariç)
    return Settings(
        station_role="ship",
        data_source="astronaut_health",
        database_url=sqlite_url(db_path),
        earth_link_token=TOKEN,
        presence_timeout_seconds=TIMEOUT,
        presence_sweep_seconds=3600,
        **kw,
    )


@pytest.fixture
def ship(tmp_path):
    app = create_app(ship_settings(tmp_path / "ship.db"))
    with TestClient(app) as c:
        yield app, c


@pytest.fixture
def clock(monkeypatch):
    """Gemi saatini (outbox.utcnow) dondurur; advance(sn) ileri alır."""
    now = {"t": outbox.utcnow()}
    monkeypatch.setattr(outbox, "utcnow", lambda: now["t"])

    def advance(seconds: float = 0) -> datetime:
        now["t"] = now["t"] + timedelta(seconds=seconds)
        return now["t"]

    return advance


def terminal_events(app) -> list[OutboxEvent]:
    with Session(app.state.engine) as db:
        q = select(OutboxEvent).where(col(OutboxEvent.type).in_(outbox.TERMINAL_EVENTS)).order_by(col(OutboxEvent.seq))
        return list(db.exec(q).all())


def beat(c: TestClient, auth: dict[str, str], leaving: bool | None = None) -> dict:
    r = c.post("/api/me/presence", json=None if leaving is None else {"leaving": leaving}, headers=auth)
    assert r.status_code == 200, r.text
    return r.json()


def sweep(app) -> int:
    with Session(app.state.engine) as db:
        return presence.sweep(db, app.state.settings)


def summary(app) -> list[tuple[str, str | None, str]]:
    return [(e.type, e.astronaut_id, e.payload["presence"]["state"]) for e in terminal_events(app)]


# ---------------------------------------------------------------- uç
def test_presence_requires_astronaut_login(ship, earth_client) -> None:
    app, c = ship
    assert c.post("/api/me/presence").status_code == 401
    # Dünya salt okunur: astronot ucu yok, yazma 403
    assert earth_client.post("/api/me/presence", headers=login(earth_client, "EARTH")).status_code == 403
    assert terminal_events(app) == []


def test_first_beat_goes_online_once(ship, clock) -> None:
    app, c = ship
    auth = login(c, "A010")
    r = beat(c, auth)
    assert r == {"state": "online", "interval_seconds": 30.0, "timeout_seconds": float(TIMEOUT)}
    clock(30)
    beat(c, auth)
    clock(30)
    beat(c, auth)
    assert summary(app) == [("terminal.online", "A010", "online")]  # sinyalin kendisi downlink'e yazılmaz
    with Session(app.state.engine) as db:
        row = db.get(TerminalPresence, "A010")
        assert row.state == "online" and as_utc(row.last_seen) == clock()


def test_payload_is_presence_only(ship, clock) -> None:
    """Yük: sadece kimlik, durum, son sinyal. Gün, check-in, öneri, metin YOK (gizlilik kuralları değişmez)."""
    app, c = ship
    auth = login(c, "A011")
    secret = "PRESENCE-SECRET-41"
    for a in (secret, "Low", "A lot", "None", "No"):  # aynı oturumda check-in (içerik terminal olayına girmemeli)
        assert c.post("/api/checkin/turn?lang=en", json={"answer": a}, headers=auth).status_code == 200
    beat(c, auth)
    clock(TIMEOUT + 1)
    sweep(app)
    evs = terminal_events(app)
    assert [e.type for e in evs] == ["terminal.online", "terminal.offline"]
    stream = c.get("/api/downlink/stream?since=0&follow=false", headers=LINK).text
    for ev in evs:
        assert ev.day_index is None
        assert ev.payload["day"] is None and ev.payload["share"] is None and ev.payload["code"] is None
        assert set(ev.payload["presence"]) == {"astronaut_id", "state", "last_seen"}
        assert ev.payload["presence"]["astronaut_id"] == "A011"
    assert secret not in str([e.payload for e in evs]) and secret not in stream
    assert "event: terminal.online" in stream and "event: terminal.offline" in stream


def test_timeout_goes_offline_with_last_seen(ship, clock) -> None:
    app, c = ship
    auth = login(c, "A012")
    beat(c, auth)
    seen = clock()
    clock(TIMEOUT - 1)
    assert sweep(app) == 0  # henüz zaman aşımı yok
    clock(2)
    assert sweep(app) == 1
    assert sweep(app) == 0  # aynı geçiş iki kez yayınlanmaz
    off = terminal_events(app)[-1]
    assert off.type == "terminal.offline"
    assert datetime.fromisoformat(off.payload["presence"]["last_seen"]) == seen  # son görülme = son sinyal
    assert as_utc(off.ship_time) == clock()  # olay, fark edildiği anda
    clock(600)
    assert beat(c, auth)["state"] == "online"  # terminal geri geldi
    assert summary(app) == [
        ("terminal.online", "A012", "online"),
        ("terminal.offline", "A012", "offline"),
        ("terminal.online", "A012", "online"),
    ]


def test_regular_beats_keep_terminal_online(ship, clock) -> None:
    app, c = ship
    auth = login(c, "A013")
    for _ in range(10):  # 10 × 30 sn > zaman aşımı, ama sinyal hiç kesilmedi
        beat(c, auth)
        clock(30)
        assert sweep(app) == 0
    assert summary(app) == [("terminal.online", "A013", "online")]


def test_logout_goes_offline_immediately(ship, clock) -> None:
    app, c = ship
    auth = login(c, "A014")
    beat(c, auth)
    clock(5)
    assert beat(c, auth, leaving=True)["state"] == "offline"
    assert beat(c, auth, leaving=True)["state"] == "offline"  # ikinci çıkış olay üretmez
    off = terminal_events(app)[-1]
    assert off.type == "terminal.offline" and datetime.fromisoformat(off.payload["presence"]["last_seen"]) == clock()
    clock(TIMEOUT * 2)
    assert sweep(app) == 0
    assert summary(app) == [("terminal.online", "A014", "online"), ("terminal.offline", "A014", "offline")]
    # Hiç sinyal göndermemiş bir terminalin çıkışı: olay yok
    beat(c, login(c, "A015"), leaving=True)
    assert all(e.astronaut_id != "A015" for e in terminal_events(app))


def test_each_astronaut_has_own_terminal(ship, clock) -> None:
    app, c = ship
    a, b = login(c, "A016"), login(c, "A017")
    beat(c, a)
    beat(c, b)
    clock(TIMEOUT / 2)
    beat(c, a)
    clock(TIMEOUT / 2 + 1)
    assert sweep(app) == 1  # sadece A017 sustu
    assert summary(app)[-1] == ("terminal.offline", "A017", "offline")


def test_snapshot_has_published_presence_only(tmp_path, clock) -> None:
    """Gecikme: terminal olayı da DOWNLINK_DELAY_SECONDS bekler; snapshot yayınlanmamış durumu göstermez."""
    app = create_app(ship_settings(tmp_path / "d.db", downlink_delay_seconds=60))
    with TestClient(app) as c:
        auth = login(c, "A020")
        beat(c, auth)
        snap = c.get("/api/downlink/snapshot", headers=LINK).json()
        assert snap["presence"] == [] and snap["seq"] == 0
        clock(61)
        beat(c, auth)
        snap = c.get("/api/downlink/snapshot", headers=LINK).json()
        assert [(p["astronaut_id"], p["state"]) for p in snap["presence"]] == [("A020", "online")]
        beat(c, auth, leaving=True)  # henüz yayınlanmadı → snapshot hâlâ çevrimiçi der
        assert [p["state"] for p in c.get("/api/downlink/snapshot", headers=LINK).json()["presence"]] == ["online"]
        clock(61)
        assert [p["state"] for p in c.get("/api/downlink/snapshot", headers=LINK).json()["presence"]] == ["offline"]


def test_state_survives_ship_restart(tmp_path, monkeypatch) -> None:
    """Durum ship.db'de: gemi yeniden açılınca eskimiş terminal açılıştaki ilk denetimde çevrimdışı olur."""
    s = ship_settings(tmp_path / "r.db")
    app = create_app(s)
    with TestClient(app) as c:
        beat(c, login(c, "A030"))
        beat(c, login(c, "A031"))
    later = outbox.utcnow() + timedelta(seconds=TIMEOUT + 5)
    monkeypatch.setattr(outbox, "utcnow", lambda: later)
    app2 = create_app(s)
    with TestClient(app2) as c2:
        deadline = time.monotonic() + 5
        while len(terminal_events(app2)) < 4 and time.monotonic() < deadline:
            time.sleep(0.05)
        assert sorted(summary(app2)[2:]) == [("terminal.offline", "A030", "offline"), ("terminal.offline", "A031", "offline")]
        beat(c2, login(c2, "A030"))
        assert summary(app2)[-1] == ("terminal.online", "A030", "online")


def test_rebuild_outbox_republishes_presence(ship, clock) -> None:
    app, c = ship
    beat(c, login(c, "A040"))
    auth = login(c, "A041")
    beat(c, auth)
    beat(c, auth, leaving=True)
    outbox.rebuild_outbox(app.state.engine, app.state.settings)  # veri seti değişti: yeni dönem
    assert summary(app) == [("terminal.online", "A040", "online"), ("terminal.offline", "A041", "offline")]
    snap = c.get("/api/downlink/snapshot", headers=LINK).json()
    assert [(p["astronaut_id"], p["state"]) for p in snap["presence"]] == [("A040", "online"), ("A041", "offline")]
