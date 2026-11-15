"""Gemi tarafı downlink: outbox, yayın ve snapshot.

- Her olay gizlilik filtresinden geçmiş güncel günü (`EarthDay`) taşır; filtre outbox'a yazmadan
  ÖNCE uygulanır (`emit_day_event` sadece privacy.earth_day çıktısı kabul eder).
- DOWNLINK_DELAY_SECONDS: olay `publish_at = ship_time + gecikme` anında yayınlanır. Yayın hep bir ön
  ektir: henüz yayınlanmamış ilk olaydan sonraki hiçbir olay gönderilmez (sıra atlanmaz).
- Snapshot sadece YAYINLANMIŞ durumu verir: bir gün için son yayınlanmış olayın günü, yoksa veri
  setinden temel gün (check-in/aksiyon yok). Böylece gecikme snapshot'la delinmez. Terminal varlığı da
  aynı kuralla: her astronot için son yayınlanmış terminal.* olayı.
- Terminal olayları (`emit_presence_event`) gün taşımaz; yük sadece privacy.earth_presence çıktısıdır.
- Dönem (epoch): gemi DB'sine özgü rastgele kimlik; DB sıfırlanınca veya veri seti yeniden
  yüklenince değişir → Dünya baştan senkronize olur.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta

from sqlalchemy import func
from sqlmodel import Session, col, select

from app.config import Settings
from app.models.schemas import DownlinkEvent, DownlinkHeartbeat, DownlinkPayload, DownlinkSnapshot, EarthDay, EarthPresence
from app.models.tables import ActionDone, OutboxEvent, TerminalPresence, as_utc
from app.models.tables import utcnow as _utcnow
from app.personal.catalog import load_personal_catalog
from app.personal.dataset import AstronautSeries
from app.personal.privacy import earth_astronaut, earth_day, earth_presence
from app.personal.store import kv_get, kv_set, personal_data

KV_EPOCH = "downlink.epoch"
TERMINAL_EVENTS = ("terminal.online", "terminal.offline")


def utcnow() -> datetime:
    """Testlerde zamanı ileri almak için ayrı (monkeypatch)."""
    return _utcnow()


def ship_epoch(db: Session) -> str:
    epoch = kv_get(db, KV_EPOCH)
    if not epoch:
        epoch = secrets.token_hex(8)
        kv_set(db, KV_EPOCH, epoch)
        db.commit()
    return str(epoch)


def new_epoch(db: Session) -> None:
    kv_set(db, KV_EPOCH, secrets.token_hex(8))


# ---------------------------------------------------------------- olay üretimi
def done_codes(db: Session, astronaut_id: str, day_index: int) -> frozenset[str]:
    rows = db.exec(select(ActionDone).where(ActionDone.astronaut_id == astronaut_id, ActionDone.day_index == day_index)).all()
    return frozenset(r.code for r in rows)


def current_earth_day(db: Session, series: AstronautSeries, day_index: int) -> EarthDay:
    """Bir günün şu anki hali, Dünya'nın göreceği şekilde (gizlilik filtresi burada)."""
    from app.models.tables import CheckinSession

    row = db.get(CheckinSession, (series.meta.id, day_index))
    return earth_day(load_personal_catalog(), series, day_index, row, done_codes(db, series.meta.id, day_index))


def emit_day_event(
    db: Session,
    settings: Settings,
    event_type: str,
    series: AstronautSeries,
    day_index: int,
    **extra: object,
) -> OutboxEvent:
    """Gün olayı yazar (commit çağırana aittir). Payload = filtrelenmiş gün + küçük ek alanlar."""
    payload = DownlinkPayload(day=current_earth_day(db, series, day_index), **extra)  # type: ignore[arg-type]
    now = utcnow()
    ev = OutboxEvent(
        type=event_type,
        astronaut_id=series.meta.id,
        day_index=day_index,
        payload=payload.model_dump(mode="json"),
        ship_time=now,
        publish_at=now + timedelta(seconds=settings.downlink_delay_seconds),
    )
    db.add(ev)
    db.flush()
    return ev


def emit_presence_event(db: Session, settings: Settings, row: TerminalPresence) -> OutboxEvent:
    """Terminal durum değişimi (commit çağırana aittir): terminal.online / terminal.offline.

    Yük sadece varlıktır (kimlik, durum, son sinyal); gün, check-in veya ekranda yapılan hiçbir şey taşınmaz.
    """
    now = utcnow()
    presence = earth_presence(row.astronaut_id, row.state, as_utc(row.last_seen))
    ev = OutboxEvent(
        type=f"terminal.{row.state}",
        astronaut_id=row.astronaut_id,
        day_index=None,
        payload=DownlinkPayload(presence=presence).model_dump(mode="json"),
        ship_time=now,
        publish_at=now + timedelta(seconds=settings.downlink_delay_seconds),
    )
    db.add(ev)
    db.flush()
    return ev


# ---------------------------------------------------------------- yayın
def _first_pending_seq(db: Session, now: datetime) -> int | None:
    return db.exec(select(func.min(OutboxEvent.seq)).where(OutboxEvent.publish_at > now)).one()


def published_bound(db: Session, now: datetime | None = None) -> int:
    """Yayınlanmış son seq (ön ek kuralı)."""
    now = now or utcnow()
    pending = _first_pending_seq(db, now)
    if pending is not None:
        return pending - 1
    return db.exec(select(func.max(OutboxEvent.seq))).one() or 0


def pending_count(db: Session, now: datetime | None = None) -> int:
    now = now or utcnow()
    return db.exec(select(func.count()).select_from(OutboxEvent).where(OutboxEvent.publish_at > now)).one()


def published_events(db: Session, since: int, limit: int = 500, now: datetime | None = None) -> list[OutboxEvent]:
    bound = published_bound(db, now)
    return list(
        db.exec(
            select(OutboxEvent).where(OutboxEvent.seq > since, OutboxEvent.seq <= bound).order_by(col(OutboxEvent.seq)).limit(limit)
        ).all()
    )


def to_wire(ev: OutboxEvent, epoch: str, settings: Settings) -> DownlinkEvent:
    return DownlinkEvent(
        seq=ev.seq or 0,
        type=ev.type,  # type: ignore[arg-type]
        epoch=epoch,
        astronaut_id=ev.astronaut_id,
        day_index=ev.day_index,
        ship_time=as_utc(ev.ship_time),
        publish_time=as_utc(ev.publish_at),
        simulated_light_delay_minutes=settings.downlink_simulated_light_delay_minutes,
        payload=DownlinkPayload.model_validate(ev.payload),
    )


def heartbeat(db: Session, settings: Settings) -> DownlinkHeartbeat:
    now = utcnow()
    return DownlinkHeartbeat(
        epoch=ship_epoch(db),
        ship_time=now,
        last_seq=published_bound(db, now),
        pending=pending_count(db, now),
        delay_seconds=settings.downlink_delay_seconds,
        simulated_light_delay_minutes=settings.downlink_simulated_light_delay_minutes,
    )


# ---------------------------------------------------------------- snapshot
_BASELINE: dict[tuple[int, str], dict[tuple[str, int], EarthDay]] = {}


def _baseline(engine_id: int, fingerprint: str, series_by_id: dict[str, AstronautSeries]) -> dict[tuple[str, int], EarthDay]:
    """Veri setinden temel günler (check-in ve aksiyon yok); parmak izi başına bir kez."""
    key = (engine_id, fingerprint)
    if key not in _BASELINE:
        cat = load_personal_catalog()
        _BASELINE.clear()
        _BASELINE[key] = {(a.meta.id, i): earth_day(cat, a, i) for a in series_by_id.values() for i in range(len(a.days))}
    return _BASELINE[key]


def snapshot(db: Session, settings: Settings) -> DownlinkSnapshot:
    from app.personal.store import KV_FINGERPRINT

    now = utcnow()
    engine = db.get_bind()
    series_by_id = personal_data(engine).all(db)  # type: ignore[arg-type]
    days = dict(_baseline(id(engine), str(kv_get(db, KV_FINGERPRINT)), series_by_id))
    bound = published_bound(db, now)
    latest = db.exec(
        select(OutboxEvent.astronaut_id, OutboxEvent.day_index, func.max(OutboxEvent.seq))
        .where(OutboxEvent.seq <= bound, col(OutboxEvent.day_index).is_not(None))
        .group_by(OutboxEvent.astronaut_id, OutboxEvent.day_index)
    ).all()
    if latest:
        seqs = [s for _, _, s in latest]
        for ev in db.exec(select(OutboxEvent).where(col(OutboxEvent.seq).in_(seqs))).all():
            days[(ev.astronaut_id, ev.day_index)] = DownlinkPayload.model_validate(ev.payload).day  # type: ignore[index]
    return DownlinkSnapshot(
        epoch=ship_epoch(db),
        seq=bound,
        generated_at=now,
        simulated_light_delay_minutes=settings.downlink_simulated_light_delay_minutes,
        astronauts=[earth_astronaut(a) for a in series_by_id.values()],
        days=list(days.values()),
        presence=published_presence(db, bound),
    )


def published_presence(db: Session, bound: int) -> list[EarthPresence]:
    """Her astronot için yayınlanmış (seq <= bound) son terminal.* olayının durumu."""
    latest = db.exec(
        select(func.max(OutboxEvent.seq))
        .where(OutboxEvent.seq <= bound, col(OutboxEvent.type).in_(TERMINAL_EVENTS))
        .group_by(OutboxEvent.astronaut_id)
    ).all()
    if not latest:
        return []
    rows = db.exec(select(OutboxEvent).where(col(OutboxEvent.seq).in_(latest)).order_by(col(OutboxEvent.astronaut_id))).all()
    return [p for p in (DownlinkPayload.model_validate(ev.payload).presence for ev in rows) if p is not None]


def rebuild_outbox(engine, settings: Settings) -> None:  # noqa: ANN001
    """Veri seti değişti: yeni dönem; check-in / aksiyonu olan günler yeniden yayınlanır."""
    from sqlalchemy import delete

    from app.models.tables import CheckinSession

    with Session(engine) as db:
        db.exec(delete(OutboxEvent))  # type: ignore[call-overload]
        new_epoch(db)
        series_by_id = personal_data(engine).all(db)
        keys = {(r.astronaut_id, r.day_index) for r in db.exec(select(CheckinSession)).all()}
        keys |= {(r.astronaut_id, r.day_index) for r in db.exec(select(ActionDone)).all()}
        for aid, i in sorted(keys):
            series = series_by_id.get(aid)
            if series is not None and i < len(series.days):
                emit_day_event(db, settings, "day.snapshot", series, i)
        # Terminallerin bilinen durumu da yeni dönemde yeniden yayınlanır (Dünya "henüz bağlanmadı" demesin)
        for row in db.exec(select(TerminalPresence).order_by(col(TerminalPresence.astronaut_id))).all():
            emit_presence_event(db, settings, row)
        db.commit()
