"""Dünya üssünün veritabanı: downlink ile gelen (gemide filtrelenmiş) veri ve bağlantı durumu.

Tekrar ve eksik olay olmaması için: olaylar gemideki `seq` ile tutulur, `seq <= last_seq` olan olay
yok sayılır; bağlantı koparsa alıcı `since=last_seq` ile kaldığı yerden devam eder. Gemi dönemi
(epoch) değişirse (gemi DB'si sıfırlandı) Dünya snapshot'la baştan senkronize olur.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import delete
from sqlmodel import Session, col, select

from app.models.schemas import DownlinkEvent, DownlinkHeartbeat, DownlinkSnapshot, EarthAstronaut, EarthDay
from app.models.tables import EarthAstronautRow, EarthDayRow, EarthEvent, as_utc, utcnow
from app.personal.store import kv_get, kv_set

KV_LINK = "link.state"
LINK_DEFAULTS: dict[str, Any] = {
    "epoch": None,
    "last_seq": 0,
    "connected": False,
    "last_contact": None,
    "last_event_at": None,
    "ship_last_seq": None,
    "pending_on_ship": None,
    "events_received": 0,
    "snapshot_at": None,
    "last_error": None,
    "delay_seconds": None,
    "simulated_light_delay_minutes": None,
}


def _iso(t: datetime | None) -> str | None:
    return as_utc(t).isoformat() if t else None


def link_state(db: Session) -> dict[str, Any]:
    return {**LINK_DEFAULTS, **(kv_get(db, KV_LINK) or {})}


def update_link(db: Session, **changes: Any) -> dict[str, Any]:
    state = link_state(db)
    for k, v in changes.items():
        state[k] = _iso(v) if isinstance(v, datetime) else v
    kv_set(db, KV_LINK, state)
    return state


# ---------------------------------------------------------------- yazma (alıcı)
def apply_snapshot(db: Session, snap: DownlinkSnapshot) -> None:
    """Bütün Dünya verisini snapshot ile değiştirir (ilk açılış veya gemi dönemi değişti)."""
    same_epoch = link_state(db)["epoch"] == snap.epoch
    db.exec(delete(EarthAstronautRow))  # type: ignore[call-overload]
    db.exec(delete(EarthDayRow))  # type: ignore[call-overload]
    if not same_epoch:
        db.exec(delete(EarthEvent))  # type: ignore[call-overload]
    now = utcnow()
    for a in snap.astronauts:
        db.add(EarthAstronautRow(id=a.id, data=a.model_dump(mode="json")))
    for d in snap.days:
        db.add(EarthDayRow(astronaut_id=d.astronaut_id, day_index=d.day_index, data=d.model_dump(mode="json"), updated_seq=0, received_at=now))
    update_link(
        db,
        epoch=snap.epoch,
        last_seq=snap.seq,
        snapshot_at=now,
        last_contact=now,
        simulated_light_delay_minutes=snap.simulated_light_delay_minutes,
        **({} if same_epoch else {"events_received": 0}),
    )
    db.commit()


def apply_event(db: Session, ev: DownlinkEvent) -> EarthEvent | None:
    """Olayı işler; tekrar gelen (seq <= last_seq) olay için None. Yükteki gün aynen saklanır."""
    state = link_state(db)
    if ev.seq <= int(state["last_seq"] or 0):
        return None
    now = utcnow()
    day = ev.payload.day
    if day is not None:  # gün olayı (terminal.* olayları gün taşımaz)
        row = db.get(EarthDayRow, (day.astronaut_id, day.day_index))
        if row is None:
            row = EarthDayRow(astronaut_id=day.astronaut_id, day_index=day.day_index)
        row.data = day.model_dump(mode="json")
        row.updated_seq = ev.seq
        row.received_at = now
        db.add(row)
    stored = EarthEvent(
        seq=ev.seq,
        epoch=ev.epoch,
        type=ev.type,
        astronaut_id=ev.astronaut_id,
        day_index=ev.day_index,
        payload=ev.payload.model_dump(mode="json"),
        ship_time=ev.ship_time,
        publish_time=ev.publish_time,
        earth_received_time=now,
        simulated_light_delay_minutes=ev.simulated_light_delay_minutes,
    )
    db.add(stored)
    update_link(
        db,
        last_seq=ev.seq,
        ship_last_seq=max(int(state["ship_last_seq"] or 0), ev.seq),
        last_event_at=now,
        last_contact=now,
        events_received=int(state["events_received"] or 0) + 1,
        simulated_light_delay_minutes=ev.simulated_light_delay_minutes,
    )
    db.commit()
    db.refresh(stored)  # oturum kapandıktan sonra da okunabilsin
    return stored


def apply_heartbeat(db: Session, hb: DownlinkHeartbeat) -> None:
    update_link(
        db,
        last_contact=utcnow(),
        ship_last_seq=hb.last_seq,
        pending_on_ship=hb.pending,
        delay_seconds=hb.delay_seconds,
        simulated_light_delay_minutes=hb.simulated_light_delay_minutes,
    )
    db.commit()


# ---------------------------------------------------------------- okuma (monitor)
def earth_astronaut_ids(session: Session) -> list[str]:
    return list(session.exec(select(EarthAstronautRow.id).order_by(col(EarthAstronautRow.id))).all())


def earth_astronauts(db: Session) -> list[EarthAstronaut]:
    rows = db.exec(select(EarthAstronautRow).order_by(col(EarthAstronautRow.id))).all()
    return [EarthAstronaut.model_validate(r.data) for r in rows]


def earth_astronaut(db: Session, astronaut_id: str) -> EarthAstronaut | None:
    row = db.get(EarthAstronautRow, astronaut_id)
    return EarthAstronaut.model_validate(row.data) if row else None


def earth_days(db: Session, astronaut_id: str) -> list[EarthDay]:
    rows = db.exec(select(EarthDayRow).where(EarthDayRow.astronaut_id == astronaut_id).order_by(col(EarthDayRow.day_index))).all()
    return [EarthDay.model_validate(r.data) for r in rows]


def earth_day_row(db: Session, astronaut_id: str, day_index: int) -> EarthDayRow | None:
    return db.get(EarthDayRow, (astronaut_id, day_index))


def today_rows(db: Session) -> dict[str, EarthDay]:
    """Her astronotun son günü."""
    out: dict[str, EarthDay] = {}
    for r in db.exec(select(EarthDayRow).order_by(col(EarthDayRow.astronaut_id), col(EarthDayRow.day_index))).all():
        out[r.astronaut_id] = EarthDay.model_validate(r.data)
    return out


def events_count(db: Session) -> int:
    from sqlalchemy import func

    return db.exec(select(func.count()).select_from(EarthEvent)).one()


def list_events(
    db: Session,
    *,
    limit: int = 100,
    astronaut_id: str | None = None,
    types: list[str] | None = None,
    before_seq: int | None = None,
) -> tuple[list[EarthEvent], int]:
    """Alınan olaylar, yeniden eskiye. (sayfa, filtreye uyan toplam) döner."""
    from sqlalchemy import func

    conds = []
    if astronaut_id:
        conds.append(EarthEvent.astronaut_id == astronaut_id)
    if types:
        conds.append(col(EarthEvent.type).in_(types))
    total = db.exec(select(func.count()).select_from(EarthEvent).where(*conds)).one()
    if before_seq is not None:
        conds.append(col(EarthEvent.seq) < before_seq)
    rows = db.exec(select(EarthEvent).where(*conds).order_by(col(EarthEvent.seq).desc()).limit(limit)).all()
    return list(rows), int(total)
