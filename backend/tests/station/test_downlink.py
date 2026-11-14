"""Downlink (gemi → Dünya): outbox, gecikme, gizlilik, alıcı, kopma/yeniden bağlanma, Dünya ekranı."""

import asyncio
import json
from datetime import timedelta

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.config import Settings
from app.db import engine_for, init_db
from app.downlink import earth_store, outbox
from app.downlink.receiver import EpochChanged, Receiver
from app.main import create_app
from app.models.tables import CmoNotification, EarthEvent, OutboxEvent
from app.personal.store import personal_data

from .conftest import login, sqlite_url

TOKEN = "test-link-token"
LINK = {"Authorization": f"Bearer {TOKEN}"}
PRIVATE = ("beh_mood_score", "beh_stress_score")


# ---------------------------------------------------------------- fikstürler
@pytest.fixture(scope="module")
def ship(tmp_path_factory):
    db = tmp_path_factory.mktemp("linkship") / "ship.db"
    s = Settings(station_role="ship", data_source="astronaut_health", database_url=sqlite_url(db), earth_link_token=TOKEN)
    app = create_app(s)
    with TestClient(app) as c:
        yield app, c


@pytest.fixture(scope="module")
def earth_engine(tmp_path_factory):
    eng = engine_for(sqlite_url(tmp_path_factory.mktemp("linkearth") / "earth.db"))
    init_db(eng)
    return eng


@pytest.fixture(scope="module")
def receiver(earth_engine):
    s = Settings(station_role="earth", data_source="astronaut_health", ship_url="http://ship", earth_link_token=TOKEN)
    return Receiver(earth_engine, s)


def complete_checkin(client, aid, answers=("Badly", "Low", "A lot", "None", "No"), lang="en"):
    auth = login(client, aid)
    for a in answers:
        r = client.post(f"/api/checkin/turn?lang={lang}", json={"answer": a}, headers=auth)
        assert r.status_code == 200, r.text
    return auth


def ship_events(app) -> list[OutboxEvent]:
    with Session(app.state.engine) as db:
        return list(db.exec(select(OutboxEvent).order_by(OutboxEvent.seq)).all())


def stream_text(client, since=0) -> str:
    r = client.get(f"/api/downlink/stream?since={since}&follow=false", headers=LINK)
    assert r.status_code == 200
    return r.text


def run(coro):
    return asyncio.run(coro)


class DroppingTransport(httpx.AsyncBaseTransport):
    """İlk stream isteğinde bağlantıyı `keep` olaydan sonra, bir olayın ORTASINDA koparır."""

    def __init__(self, inner: httpx.AsyncBaseTransport, keep: int) -> None:
        self.inner, self.keep, self.dropped = inner, keep, False

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        resp = await self.inner.handle_async_request(request)
        if self.dropped or not request.url.path.endswith("/downlink/stream"):
            return resp
        self.dropped = True
        body = await resp.aread()
        parts = body.split(b"\n\n")
        cut = b"\n\n".join(parts[: self.keep]) + b"\n\n" + parts[self.keep][: len(parts[self.keep]) // 2]
        return httpx.Response(resp.status_code, headers={"content-type": "text/event-stream"}, content=cut)


# ---------------------------------------------------------------- koruma
def test_downlink_disabled_without_token(ship_client) -> None:
    r = ship_client.get("/api/downlink/snapshot", headers={**LINK, "Accept-Language": "en"})
    assert r.status_code == 503 and r.json()["code"] == "downlink_disabled"


def test_downlink_requires_correct_token(ship) -> None:
    _, c = ship
    assert c.get("/api/downlink/snapshot", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert c.get("/api/downlink/stream?follow=false").status_code == 401
    astronaut = login(c, "A001")  # astronot token'ı downlink anahtarı değildir
    assert c.get("/api/downlink/snapshot", headers=astronaut).status_code == 401
    assert c.get("/api/downlink/snapshot", headers=LINK).status_code == 200


# ---------------------------------------------------------------- olaylar ve gizlilik
def test_events_for_checkin_share_and_actions(ship) -> None:
    app, c = ship
    before = len(ship_events(app))
    auth = complete_checkin(c, "A030")
    evs = ship_events(app)[before:]
    assert [e.type for e in evs] == ["checkin.completed"]
    day = evs[0].payload["day"]
    assert day["astronaut_id"] == "A030" and day["day_index"] == 29 and day["checkin"] == {"share": "private", "notes": []}
    assert not any(col in json.dumps(evs[0].payload) for col in PRIVATE)

    c.post("/api/checkin/share", json={"level": "scores"}, headers=auth)
    shared = ship_events(app)[-1]
    assert shared.type == "checkin.shared" and shared.payload["share"] == "scores"
    assert set(PRIVATE) <= shared.payload["day"]["readings"].keys()

    code = personal_data(app.state.engine).all(Session(app.state.engine))["A030"].days[-1].self_care[0]
    r = c.post("/api/actions/done", json={"code": code}, headers=auth)
    assert r.status_code == 200 and next(t for t in r.json()["day"]["todo"] if t["code"] == code)["done"]
    act = ship_events(app)[-1]
    assert act.type == "action.done" and act.payload["done"] is True
    assert c.post("/api/actions/done", json={"code": "NOT_TODAY"}, headers=auth).status_code == 400


def test_mood_and_stress_never_leave_ship_unshared(ship) -> None:
    """Paylaşılmamış ruh hali / stres outbox'a, snapshot'a ve stream'e hiç girmez."""
    app, c = ship
    complete_checkin(c, "A031")  # private kalır
    auth = complete_checkin(c, "A032")
    c.post("/api/checkin/share", json={"level": "scores"}, headers=auth)
    shared_days = set()
    for ev in ship_events(app):
        day = ev.payload["day"]
        if (day["checkin"] or {}).get("share") in ("scores", "full"):
            shared_days.add((day["astronaut_id"], day["day_index"]))
            continue
        assert not any(col in json.dumps(ev.payload) for col in PRIVATE), ev.seq
    snap = c.get("/api/downlink/snapshot", headers=LINK).json()
    for d in snap["days"]:
        if (d["astronaut_id"], d["day_index"]) not in shared_days:
            assert not set(PRIVATE) & d["readings"].keys(), d["astronaut_id"]
            assert "behavioral" not in d["area_scores"]
    for block in stream_text(c).split("\n\n"):
        if block.startswith("id:") and '"share":"scores"' not in block and '"share":"full"' not in block:
            assert not any(col in block for col in PRIVATE)


def test_d4_private_suggestion_never_enters_downlink(ship) -> None:
    """A139 23–24. gün: ruh haline bağlı veri seti önerisi (MOOD_CONNECT) snapshot'ta ve olaylarda kodsuz."""
    app, c = ship
    snap = c.get("/api/downlink/snapshot", headers=LINK).json()
    days = {d["day_index"]: d for d in snap["days"] if d["astronaut_id"] == "A139"}
    for i in (22, 23):
        assert "MOOD_CONNECT" not in json.dumps(days[i]) and days[i]["todo_masked_count"] == 1, i
    with Session(app.state.engine) as db:
        series = personal_data(app.state.engine).series(db, "A139")
        for i in (22, 23):  # o gün için olay üretilseydi taşıyacağı yük (day.snapshot)
            ev = outbox.emit_day_event(db, app.state.settings, "day.snapshot", series, i)
            assert "MOOD_CONNECT" not in json.dumps(ev.payload), i
        db.rollback()  # olayları yazma: diğer testlerin outbox'ı değişmesin


def test_cmo_record_never_enters_downlink(ship) -> None:
    app, c = ship
    secret = "sudden chest pain and dizzy XYZ"
    complete_checkin(c, "A033", answers=("Well", "Good", "No", secret, "No"))
    with Session(app.state.engine) as db:
        assert db.exec(select(CmoNotification).where(CmoNotification.astronaut_id == "A033")).one().text == secret
    blobs = [json.dumps(e.payload) for e in ship_events(app)]
    blobs += [c.get("/api/downlink/snapshot", headers=LINK).text, stream_text(c)]
    for blob in blobs:
        assert secret not in blob and "urgent" not in blob and "CmoNotification" not in blob
        assert "medical officer" not in blob


def test_wire_format_and_heartbeat(ship) -> None:
    app, c = ship
    text = stream_text(c)
    blocks = [b for b in text.split("\n\n") if b.strip()]
    first = blocks[0].splitlines()
    assert first[0].startswith("id: ") and first[1].startswith("event: ")
    ev = json.loads(first[2].removeprefix("data: "))
    assert {"seq", "type", "epoch", "ship_time", "publish_time", "simulated_light_delay_minutes", "payload"} <= ev.keys()
    assert ev["simulated_light_delay_minutes"] == 20.0
    hb = json.loads(blocks[-1].splitlines()[1].removeprefix("data: "))
    assert blocks[-1].startswith("event: link.heartbeat") and hb["last_seq"] == len(ship_events(app)) and hb["pending"] == 0
    seqs = [json.loads(b.splitlines()[2].removeprefix("data: "))["seq"] for b in blocks if b.startswith("id:")]
    assert seqs == list(range(1, len(seqs) + 1))  # sıralı, boşluksuz
    since = stream_text(c, since=seqs[-2])
    assert since.count("id: ") == 1  # since: sadece sonrası


def test_delay_holds_events_and_snapshot(tmp_path, monkeypatch) -> None:
    s = Settings(station_role="ship", data_source="astronaut_health", database_url=sqlite_url(tmp_path / "d.db"),
                 earth_link_token=TOKEN, downlink_delay_seconds=60)
    app = create_app(s)
    with TestClient(app) as c:
        complete_checkin(c, "A040")
        text = stream_text(c)
        assert "id: " not in text and '"pending":1' in text  # gemide bekliyor
        snap = c.get("/api/downlink/snapshot", headers=LINK).json()
        assert snap["seq"] == 0
        assert next(d for d in snap["days"] if d["astronaut_id"] == "A040" and d["day_index"] == 29)["checkin"] is None
        later = outbox.utcnow() + timedelta(seconds=61)
        monkeypatch.setattr(outbox, "utcnow", lambda: later)
        text = stream_text(c)
        assert text.count("id: ") == 1 and '"pending":0' in text
        ev = json.loads(text.split("\n\n")[0].splitlines()[2].removeprefix("data: "))
        ship_time = ev["ship_time"].replace("Z", "+00:00")
        from datetime import datetime

        assert (datetime.fromisoformat(ev["publish_time"]) - datetime.fromisoformat(ship_time)).total_seconds() == 60
        snap = c.get("/api/downlink/snapshot", headers=LINK).json()
        assert snap["seq"] == 1
        assert next(d for d in snap["days"] if d["astronaut_id"] == "A040" and d["day_index"] == 29)["checkin"]["share"] == "private"


# ---------------------------------------------------------------- alıcı (Dünya)
def _earth_matches_ship(app, earth_engine) -> None:
    with Session(app.state.engine) as sdb, Session(earth_engine) as edb:
        series_by_id = personal_data(app.state.engine).all(sdb)
        for ev in sdb.exec(select(OutboxEvent)).all():
            series = series_by_id[ev.astronaut_id]
            want = outbox.current_earth_day(sdb, series, ev.day_index)
            got = earth_store.earth_day_row(edb, ev.astronaut_id, ev.day_index)
            assert got is not None and got.data == want.model_dump(mode="json"), (ev.astronaut_id, ev.day_index)


def test_receiver_snapshot_then_stream(ship, receiver, earth_engine) -> None:
    app, c = ship
    transport = httpx.ASGITransport(app=app)

    async def go():
        async with receiver.client(transport) as client:
            await receiver.consume(client, follow=False)

    run(go())
    st = receiver.state()
    assert st["epoch"] is not None and st["last_seq"] == len(ship_events(app)) and st["connected"]
    with Session(earth_engine) as db:
        assert len(earth_store.earth_astronaut_ids(db)) == 200
        assert earth_store.events_count(db) == 0  # snapshot'taki durum olay olarak kopyalanmaz
        assert len(earth_store.earth_days(db, "A030")) == 30
    _earth_matches_ship(app, earth_engine)


def test_reconnect_resumes_without_duplicates_or_gaps(ship, receiver, earth_engine) -> None:
    app, c = ship
    start = receiver.state()["last_seq"]
    for aid in ("A050", "A051", "A052", "A053"):
        auth = complete_checkin(c, aid)
        c.post("/api/checkin/share", json={"level": "full"}, headers=auth)
    total = len(ship_events(app))
    assert total - start == 8

    async def go():
        dropping = DroppingTransport(httpx.ASGITransport(app=app), keep=3)
        async with receiver.client(dropping) as client:
            await receiver.consume(client, follow=False)  # 3 olaydan sonra, 4.'nün ortasında kopar
        assert receiver.state()["last_seq"] == start + 3
        async with receiver.client(httpx.ASGITransport(app=app)) as client:
            await receiver.consume(client, follow=False)  # kaldığı yerden
            await receiver.consume(client, follow=False)  # tekrar bağlan: yeni olay yok

    run(go())
    assert receiver.state()["last_seq"] == total
    with Session(earth_engine) as db:
        seqs = [e.seq for e in db.exec(select(EarthEvent).order_by(EarthEvent.seq)).all()]
        events = db.exec(select(EarthEvent).where(EarthEvent.seq > start)).all()
    assert seqs == list(range(start + 1, total + 1))  # eksik yok, tekrar yok
    assert all(e.ship_time and e.earth_received_time and e.publish_time for e in events)
    _earth_matches_ship(app, earth_engine)


def test_duplicate_event_is_ignored(ship, receiver, earth_engine) -> None:
    app, c = ship
    last = ship_events(app)[-1]
    with Session(app.state.engine) as db:
        wire = outbox.to_wire(last, outbox.ship_epoch(db), app.state.settings)
    with Session(earth_engine) as db:
        before = earth_store.events_count(db), receiver.state()["last_seq"]
        assert earth_store.apply_event(db, wire) is None  # seq <= last_seq → yok sayılır
        assert (earth_store.events_count(db), receiver.state()["last_seq"]) == before


def test_epoch_change_triggers_resync(ship, receiver, earth_engine) -> None:
    app, c = ship
    old = receiver.state()["epoch"]
    outbox.rebuild_outbox(app.state.engine, app.state.settings)  # gemi verisi yeniden yüklendi gibi

    async def go():
        async with receiver.client(httpx.ASGITransport(app=app)) as client:
            with pytest.raises(EpochChanged):
                await receiver.consume(client, follow=False)
            receiver._link(epoch=None)
            await receiver.consume(client, follow=False)

    run(go())
    st = receiver.state()
    assert st["epoch"] != old and st["last_seq"] == len(ship_events(app))
    _earth_matches_ship(app, earth_engine)


# ---------------------------------------------------------------- Dünya ekranı
def test_monitor_api_reads_earth_db(ship, receiver, earth_engine, tmp_path_factory) -> None:
    app, c = ship
    url = str(earth_engine.url)
    earth = create_app(Settings(station_role="earth", data_source="astronaut_health", database_url=url))
    with TestClient(earth) as e:
        assert e.get("/api/monitor/crew").status_code == 401
        auth = {**login(e, "EARTH"), "Accept-Language": "en"}
        crew = e.get("/api/monitor/crew", headers=auth).json()
        assert len(crew["astronauts"]) == 200 and crew["link"]["last_seq"] == len(ship_events(app))
        a50 = next(m for m in crew["astronauts"] if m["astronaut"]["id"] == "A050")
        assert a50["share"] == "full" and a50["checkin_text"] == "Shared by the astronaut: everything."
        day = e.get("/api/monitor/astronauts/A050/days/30", headers=auth).json()
        assert day["view"]["viewer"] == "earth" and day["checkin"]["share"] == "full"
        assert [n["topic"] for n in day["checkin"]["notes"]][:2] == ["Sleep", "Mood"]
        mood = next(r for r in day["view"]["readings"] if r["col"] == "beh_mood_score")
        assert not mood["hidden"]  # paylaşıldı
        other = e.get("/api/monitor/astronauts/A031/days/30", headers=auth).json()
        assert other["checkin"]["text"] == "Check-in completed. The astronaut kept it private."
        assert next(r for r in other["view"]["readings"] if r["col"] == "beh_mood_score")["value_text"] == "Not shared"
        assert e.get("/api/monitor/astronauts/A031", headers=auth).json()["today"] == 30
        assert e.get("/api/monitor/astronauts/A999", headers=auth).status_code == 404
        hint = e.post("/api/auth/login", json={"id": "A031", "password": "A031"}).json()
        assert hint["code"] == "wrong_station"
        token = auth["Authorization"].split(" ", 1)[1]
        r = e.get(f"/api/stream/monitor?follow=false&access_token={token}")
        assert r.status_code == 200 and r.text.startswith("event: link")
        status = e.get("/api/link/status", headers=auth).json()
        assert status["configured"] is False and status["epoch"] == receiver.state()["epoch"]
        assert e.get("/api/link/status").status_code == 401
        # astronot uçları Dünya'da yok; yazma 403
        assert e.get("/api/me", headers=auth).status_code == 404
        assert e.post("/api/checkin/share", json={"level": "full"}, headers=auth).status_code == 403


def test_monitor_events_list(ship, receiver, earth_engine) -> None:
    """Canlı akışın geçmişi: earth.db'deki olaylar yeniden eskiye; gün içeriği ve check-in metni taşımaz."""
    app, c = ship
    secret = "slept badly EVENTS-SECRET-17"
    auth = complete_checkin(c, "A060", answers=(secret, "Low", "A lot", "None", "No"))
    c.post("/api/checkin/share", json={"level": "scores"}, headers=auth)
    complete_checkin(c, "A061")  # private kalır

    async def go():
        async with receiver.client(httpx.ASGITransport(app=app)) as client:
            await receiver.consume(client, follow=False)

    run(go())
    earth = create_app(Settings(station_role="earth", data_source="astronaut_health", database_url=str(earth_engine.url)))
    with TestClient(earth) as e:
        assert e.get("/api/monitor/events").status_code == 401
        auth = login(e, "EARTH")
        r = e.get("/api/monitor/events?limit=3", headers=auth)
        assert r.status_code == 200, r.text
        body = r.json()
        assert secret not in r.text and "notes" not in r.text and "readings" not in r.text
        evs = body["events"]
        assert [(x["type"], x["astronaut_id"]) for x in evs] == [
            ("checkin.completed", "A061"),
            ("checkin.shared", "A060"),
            ("checkin.completed", "A060"),
        ]
        assert body["last_seq"] == receiver.state()["last_seq"] == evs[0]["seq"]
        assert body["total"] >= 3 and evs[0]["seq"] > evs[1]["seq"] > evs[2]["seq"]
        shared = evs[1]
        assert shared["share"] == "scores" and shared["day"] == 30 and shared["mission_day"]
        assert shared["simulated_light_delay_minutes"] == 20.0
        assert shared["ship_time"] <= shared["publish_time"] <= shared["earth_received_time"]
        assert shared["ship_time"].endswith(("Z", "+00:00"))
        # filtreler ve sayfalama
        only = e.get("/api/monitor/events?astronaut_id=a060&type=checkin.completed", headers=auth).json()
        assert [x["type"] for x in only["events"]] == ["checkin.completed"] and only["total"] == 1
        both = e.get("/api/monitor/events?astronaut_id=A060&type=checkin.completed&type=checkin.shared", headers=auth).json()
        assert both["total"] == 2
        older = e.get(f"/api/monitor/events?limit=1&before_seq={evs[1]['seq']}", headers=auth).json()
        assert older["events"][0]["seq"] == evs[2]["seq"]
        assert e.get("/api/monitor/events?type=link.heartbeat", headers=auth).status_code == 422
        assert e.get("/api/monitor/events?limit=0", headers=auth).status_code == 422
