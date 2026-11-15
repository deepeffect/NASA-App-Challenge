"""Gemi tarafı terminal varlığı: astronot ekranı (/me) açıkken gelen sinyaller → çevrimiçi / çevrimdışı.

- `beat`: /me her PRESENCE_HEARTBEAT_SECONDS'ta bir sinyal gönderir; son görülme zamanı ship.db'de tutulur.
  Terminal çevrimdışıyken (veya ilk kez) gelen sinyal → downlink'e `terminal.online`.
- `leave`: "Çıkış" → beklemeden `terminal.offline` (aynı terminalde hesap değişince önceki astronot çevrimiçi
  görünmesin).
- `sweep`: arka plan görevi (`sweep_forever`, sadece gemi) PRESENCE_SWEEP_SECONDS'ta bir bakar; son sinyali
  PRESENCE_TIMEOUT_SECONDS'tan eski olan çevrimiçi terminal → `terminal.offline` (son görülme = son sinyal).

Sinyalin kendisi downlink'e yazılmaz, sadece durum DEĞİŞİMİ (yük: privacy.earth_presence). Durum ship.db'de
olduğu için gemi yeniden başlayınca kaybolmaz; açılıştaki ilk denetim eskimiş terminalleri çevrimdışı yapar.
Zaman `outbox.utcnow` ile okunur (testler ileri alabilir).

Yarışlar: sinyal ve denetim aynı satıra aynı anda yazabilir. Geçişler koşullu UPDATE ile yapılır (durum ve
zaman WHERE'de); satır gerçekten değiştiyse olay yazılır. Böylece aynı geçiş iki kez yayınlanmaz ve denetim,
araya giren taze bir sinyali çevrimdışıya çeviremez.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from sqlalchemy import update
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

from app.config import Settings
from app.downlink import outbox
from app.models.tables import TerminalPresence

log = logging.getLogger(__name__)


def _transition(db: Session, astronaut_id: str, *, to: str, where_state: str, last_seen, now, stale_before=None) -> bool:  # noqa: ANN001
    """Koşullu geçiş: satır hâlâ `where_state` durumundaysa (ve gerekirse son sinyali `stale_before`'dan eskiyse)."""
    conds = [TerminalPresence.astronaut_id == astronaut_id, TerminalPresence.state == where_state]
    if stale_before is not None:
        conds.append(col(TerminalPresence.last_seen) < stale_before)
    res = db.exec(update(TerminalPresence).where(*conds).values(state=to, last_seen=last_seen, changed_at=now))  # type: ignore[call-overload]
    return bool(res.rowcount)


def _emit(db: Session, settings: Settings, astronaut_id: str) -> None:
    row = db.get(TerminalPresence, astronaut_id, populate_existing=True)
    assert row is not None
    outbox.emit_presence_event(db, settings, row)


def beat(db: Session, settings: Settings, astronaut_id: str) -> str:
    """Terminal sinyali. Durumu döner (her zaman "online"); geçişte terminal.online yazılır ve commit edilir."""
    for attempt in range(2):
        now = outbox.utcnow()
        # Zaten çevrimiçi: sadece son görülme (olay yok)
        res = db.exec(  # type: ignore[call-overload]
            update(TerminalPresence)
            .where(TerminalPresence.astronaut_id == astronaut_id, TerminalPresence.state == "online")
            .values(last_seen=now)
        )
        if res.rowcount:
            db.commit()
            return "online"
        try:
            if db.get(TerminalPresence, astronaut_id) is None:
                db.add(TerminalPresence(astronaut_id=astronaut_id, state="online", last_seen=now, changed_at=now))
                db.flush()
                outbox.emit_presence_event(db, settings, db.get(TerminalPresence, astronaut_id))  # type: ignore[arg-type]
            elif _transition(db, astronaut_id, to="online", where_state="offline", last_seen=now, now=now):
                _emit(db, settings, astronaut_id)
            db.commit()
            return "online"
        except IntegrityError:  # aynı astronotun iki sekmesi aynı anda ilk sinyali gönderdi: bir kez daha dene
            db.rollback()
            if attempt:
                raise
    return "online"


def leave(db: Session, settings: Settings, astronaut_id: str) -> str:
    """Çıkış: terminal beklemeden çevrimdışı (son görülme = şimdi). Zaten çevrimdışıysa / hiç yoksa olay yok."""
    now = outbox.utcnow()
    if _transition(db, astronaut_id, to="offline", where_state="online", last_seen=now, now=now):
        _emit(db, settings, astronaut_id)
    db.commit()
    return "offline"


def sweep(db: Session, settings: Settings) -> int:
    """Zaman aşımına uğrayan çevrimiçi terminalleri çevrimdışı yapar; yazılan olay sayısını döner."""
    now = outbox.utcnow()
    cutoff = now - timedelta(seconds=settings.presence_timeout_seconds)
    stale = db.exec(
        select(TerminalPresence).where(TerminalPresence.state == "online", col(TerminalPresence.last_seen) < cutoff)
    ).all()
    n = 0
    for row in stale:
        # Son görülme değişmez (son sinyalin zamanı); arada taze sinyal geldiyse koşul tutmaz, olay yazılmaz
        if _transition(db, row.astronaut_id, to="offline", where_state="online", last_seen=row.last_seen, now=now, stale_before=cutoff):
            _emit(db, settings, row.astronaut_id)
            n += 1
    db.commit()
    return n


async def sweep_forever(engine: Engine, settings: Settings) -> None:
    """Gemi açık kaldıkça denetim. İlk tur hemen (gemi yeniden başladıysa eskimiş terminaller)."""
    while True:
        try:
            with Session(engine) as db:
                n = sweep(db, settings)
            if n:
                log.info("Terminal varlığı: %s terminal çevrimdışı (zaman aşımı)", n)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 — denetim hatası uygulamayı durdurmasın; bir sonraki turda yeniden
            log.exception("Terminal varlığı denetimi başarısız")
        await asyncio.sleep(settings.presence_sweep_seconds)
