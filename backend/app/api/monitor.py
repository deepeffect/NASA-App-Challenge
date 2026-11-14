"""Dünya üssü (salt okunur): /api/monitor/*, /api/stream/monitor, /api/link/status.

Her şey earth.db'den okunur: gemiden downlink ile gelen, gizlilik filtresinden geçmiş veri.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Path, Query, Request
from fastapi.responses import StreamingResponse
from sqlmodel import Session

from app.auth import EarthDep
from app.downlink import earth_store
from app.downlink.broadcast import Broadcaster
from app.errors import ApiError
from app.i18n import Lang, LangDep, t
from app.models.schemas import (
    ErrorResponse,
    LinkStatus,
    MonitorCrewMember,
    MonitorCrewResponse,
    MonitorDay,
    MonitorEvent,
    MonitorEventsResponse,
    MonitorEventType,
    PersonalOverview,
)
from app.models.tables import as_utc, utcnow
from app.personal.catalog import load_personal_catalog
from app.personal.dataset import AstronautMeta
from app.personal.earth_view import earth_checkin_view, earth_day_view, earth_strip
from app.services.personal import crew_info, day_index
from app.station import DBSession, station_settings

router = APIRouter(tags=["monitor"])
ERRORS = {401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}}
Day = Annotated[int, Path(ge=1, description="1'den başlar")]


def _dt(v: Any) -> datetime | None:
    return as_utc(datetime.fromisoformat(v)) if isinstance(v, str) else v


def link_status(request: Request, db: Session) -> LinkStatus:
    s = station_settings(request)
    st = earth_store.link_state(db)
    last_contact = _dt(st["last_contact"])
    fresh = last_contact is not None and utcnow() - last_contact < timedelta(seconds=max(15.0, 3 * s.downlink_heartbeat_seconds))
    ship_last = st["ship_last_seq"]
    return LinkStatus(
        configured=bool(s.ship_url and s.earth_link_token),
        connected=bool(st["connected"]) and fresh,
        ship_url=s.ship_url,
        epoch=st["epoch"],
        last_contact=last_contact,
        last_event_at=_dt(st["last_event_at"]),
        last_seq=int(st["last_seq"] or 0),
        ship_last_seq=ship_last,
        pending_on_ship=st["pending_on_ship"],
        behind=None if ship_last is None else max(0, int(ship_last) - int(st["last_seq"] or 0)),
        events_received=int(st["events_received"] or 0),
        snapshot_at=_dt(st["snapshot_at"]),
        last_error=st["last_error"],
        delay_seconds=st["delay_seconds"],
        simulated_light_delay_minutes=st["simulated_light_delay_minutes"],
    )


def _meta(db: Session, astronaut_id: str, lang: Lang):  # noqa: ANN202
    a = earth_store.earth_astronaut(db, astronaut_id.strip().upper())
    if a is None:
        raise ApiError(404, "unknown_astronaut", t("unknown_astronaut", lang, id=astronaut_id))
    meta = AstronautMeta(id=a.id, age=a.age, sex=a.sex, bmi=a.bmi, mission=a.mission, profile=a.profile)
    return a, crew_info(load_personal_catalog(), meta, a.first_mission_day, a.last_mission_day, a.n_days, lang)


@router.get("/link/status", response_model=LinkStatus, responses=ERRORS, summary="Gemi bağlantısı: bağlı mı, son temas, kuyruk")
def get_link_status(_p: EarthDep, request: Request, db: DBSession) -> LinkStatus:
    return link_status(request, db)


@router.get("/monitor/crew", response_model=MonitorCrewResponse, responses=ERRORS, summary="Bütün astronotların bugünü (Dünya görünümü)")
def get_crew(_p: EarthDep, request: Request, db: DBSession, lang: LangDep) -> MonitorCrewResponse:
    cat = load_personal_catalog()
    today = earth_store.today_rows(db)
    members = []
    for a in earth_store.earth_astronauts(db):
        rec = today.get(a.id)
        if rec is None:
            continue
        view = earth_day_view(cat, rec, lang)
        meta = AstronautMeta(id=a.id, age=a.age, sex=a.sex, bmi=a.bmi, mission=a.mission, profile=a.profile)
        members.append(
            MonitorCrewMember(
                astronaut=crew_info(cat, meta, a.first_mission_day, a.last_mission_day, a.n_days, lang),
                today=rec.day_index + 1,
                mission_day=rec.mission_day,
                status=view.status,
                status_label=view.status_label,
                subtitle=view.subtitle,
                score=view.score,
                score_text=view.score_text,
                ground=view.ground,
                share=view.share,
                checkin_text=earth_checkin_view(rec.checkin, lang).text,
            )
        )
    return MonitorCrewResponse(link=link_status(request, db), astronauts=members)


@router.get("/monitor/astronauts/{astronaut_id}", response_model=PersonalOverview, responses=ERRORS, summary="Astronotun 30 günlük şeridi (Dünya)")
def get_overview(astronaut_id: str, _p: EarthDep, db: DBSession, lang: LangDep) -> PersonalOverview:
    a, info = _meta(db, astronaut_id, lang)
    cat = load_personal_catalog()
    return PersonalOverview(
        astronaut=info, today=a.n_days, n_days=a.n_days, strip=earth_strip(cat, earth_store.earth_days(db, a.id), lang),
        threshold_note=cat.threshold_note.get(lang),
    )


@router.get("/monitor/astronauts/{astronaut_id}/days/{day}", response_model=MonitorDay, responses=ERRORS, summary="Bir gün (Dünya görünümü + check-in)")
def get_day(astronaut_id: str, day: Day, _p: EarthDep, db: DBSession, lang: LangDep) -> MonitorDay:
    a, _info = _meta(db, astronaut_id, lang)
    i = day_index(a.n_days, day, lang)
    row = earth_store.earth_day_row(db, a.id, i)
    if row is None:
        raise ApiError(404, "no_ship_data", t("no_ship_data", lang))
    from app.models.schemas import EarthDay

    rec = EarthDay.model_validate(row.data)
    cat = load_personal_catalog()
    return MonitorDay(
        view=earth_day_view(cat, rec, lang),
        checkin=earth_checkin_view(rec.checkin, lang),
        updated_seq=row.updated_seq,
        received_at=as_utc(row.received_at) if row.received_at else None,
    )


@router.get("/monitor/events", response_model=MonitorEventsResponse, responses=ERRORS, summary="Alınan olaylar (canlı akışın geçmişi), yeniden eskiye")
def get_events(
    _p: EarthDep,
    db: DBSession,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    astronaut_id: Annotated[str | None, Query(description="Sadece bu astronotun olayları")] = None,
    type: Annotated[  # noqa: A002 — sorgu parametresinin adı
        list[MonitorEventType] | None, Query(description="Tekrarlanabilir: type=checkin.completed&type=checkin.shared")
    ] = None,
    before_seq: Annotated[int | None, Query(ge=1, description="Sayfalama: bu seq'ten ÖNCEKİ olaylar")] = None,
) -> MonitorEventsResponse:
    aid = astronaut_id.strip().upper() if astronaut_id else None
    rows, total = earth_store.list_events(db, limit=limit, astronaut_id=aid, types=list(type or []), before_seq=before_seq)
    events = []
    for r in rows:
        p = r.payload or {}
        events.append(
            MonitorEvent(
                seq=r.seq,
                type=r.type,  # type: ignore[arg-type]
                astronaut_id=r.astronaut_id,
                day=None if r.day_index is None else r.day_index + 1,
                mission_day=(p.get("day") or {}).get("mission_day"),
                ship_time=as_utc(r.ship_time),
                publish_time=as_utc(r.publish_time),
                earth_received_time=as_utc(r.earth_received_time),
                simulated_light_delay_minutes=r.simulated_light_delay_minutes,
                share=p.get("share"),
                code=p.get("code"),
                masked=bool(p.get("masked", False)),
                done=p.get("done"),
                last_seen=_dt((p.get("presence") or {}).get("last_seen")),
            )
        )
    return MonitorEventsResponse(events=events, total=total, last_seq=int(earth_store.link_state(db)["last_seq"] or 0))


def broadcaster_of(request: Request) -> Broadcaster:
    b = getattr(request.app.state, "broadcaster", None)
    if b is None:
        b = request.app.state.broadcaster = Broadcaster()
    return b


@router.get(
    "/stream/monitor",
    responses={**ERRORS, 200: {"content": {"text/event-stream": {}}}},
    summary="Dünya ekranı için yerel SSE: yeni olaylar ve bağlantı durumu (EventSource: ?access_token=)",
)
async def stream_monitor(
    _p: EarthDep,
    request: Request,
    follow: Annotated[bool, Query(description="false → anlık bağlantı durumunu verip kapan")] = True,
) -> StreamingResponse:
    engine = request.app.state.engine
    s = station_settings(request)
    b = broadcaster_of(request)

    def link_event() -> str:
        with Session(engine) as db:
            status = link_status(request, db)
        return f"event: link\ndata: {json.dumps({'kind': 'link', 'link': status.model_dump(mode='json')})}\n\n"

    async def gen() -> AsyncIterator[str]:
        q = b.subscribe()
        try:
            yield link_event()
            if not follow:
                return
            while True:
                try:
                    item = await asyncio.wait_for(q.get(), timeout=s.downlink_heartbeat_seconds)
                except TimeoutError:
                    if await request.is_disconnected():
                        return
                    yield link_event()
                    continue
                if item.get("kind") == "event":
                    yield f"event: event\ndata: {json.dumps(item)}\n\n"
                else:
                    yield link_event()
        finally:
            b.unsubscribe(q)

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
