"""Veri setinin gemi DB'sine yazılması ve okunması.

Veri seti küçük (200 × 30 gün): DB'den bir kez okunup bellekte tutulur; parmak izi değişince
(yeni `git pull` + yeniden başlatma veya `reset`) önbellek kendiliğinden yenilenir.
"""

from __future__ import annotations

import logging
import threading

from sqlalchemy import delete, insert
from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from app.config import Settings
from app.models.tables import CrewProfile, DayExtra, DayRecord, StationKV, utcnow
from app.personal.dataset import (
    AstronautMeta,
    AstronautSeries,
    Dataset,
    DatasetInfo,
    DayData,
    file_fingerprint,
    load_dataset_file,
)

log = logging.getLogger(__name__)

KV_FINGERPRINT = "dataset.fingerprint"
KV_ADAPTER = "dataset.adapter"
KV_INFO = "dataset.info"  # DatasetInfo (veri setine özgü kurallar); yoksa varsayılan


def kv_get(session: Session, key: str, default: object = None) -> object:
    row = session.get(StationKV, key)
    return default if row is None else row.value


def kv_set(session: Session, key: str, value: object) -> None:
    row = session.get(StationKV, key)
    if row is None:
        session.add(StationKV(key=key, value=value))
    else:
        row.value = value
        row.updated_at = utcnow()
        session.add(row)


def store_dataset(session: Session, ds: Dataset) -> dict:
    """Astronotları upsert eder, günlük kayıtları baştan yazar (check-in vb. kayıtlara dokunmaz)."""
    for a in ds.astronauts:
        m = a.meta
        session.merge(
            CrewProfile(
                id=m.id, age=m.age, sex=m.sex, bmi=m.bmi, mission=m.mission, profile=m.profile,
                first_mission_day=a.days[0].mission_day, last_mission_day=a.days[-1].mission_day, n_days=len(a.days),
            )
        )
    session.flush()
    session.exec(delete(DayRecord))  # type: ignore[call-overload]
    rows = [
        {
            "astronaut_id": a.meta.id,
            "day_index": i,
            "mission_day": d.mission_day,
            "values": d.values,
            "area_scores": d.area_scores,
            "daily_score": d.daily_score,
            "cumulative_score": d.cumulative_score,
            "health_status": d.health_status,
            "main_concern": d.main_concern,
            "self_care": d.self_care,
            "needs_ground_support": d.needs_ground_support,
        }
        for a in ds.astronauts
        for i, d in enumerate(a.days)
    ]
    session.exec(insert(DayRecord), params=rows)  # type: ignore[call-overload]
    session.exec(delete(DayExtra))  # type: ignore[call-overload]
    extras = [
        {"astronaut_id": a.meta.id, "day_index": i, "levels": d.levels, "normal": d.normal, "display": d.display}
        for a in ds.astronauts
        for i, d in enumerate(a.days)
        if d.levels is not None or d.normal is not None or d.display is not None
    ]
    if extras:
        session.exec(insert(DayExtra), params=extras)  # type: ignore[call-overload]
    kv_set(session, KV_FINGERPRINT, ds.fingerprint)
    kv_set(session, KV_ADAPTER, ds.adapter)
    kv_set(session, KV_INFO, ds.info.model_dump(mode="json"))
    session.commit()
    return {"astronauts": len(ds.astronauts), "days": len(rows), "adapter": ds.adapter}


def ensure_dataset_loaded(engine: Engine, settings: Settings, force: bool = False) -> dict | None:
    """Gemi açılışı: DB boşsa veya dosya değiştiyse veri setini yükler. Yüklendiyse istatistik döner."""
    path = settings.dataset_path
    with Session(engine) as s:
        if not force and path.exists() and kv_get(s, KV_FINGERPRINT) == file_fingerprint(path):
            return None
        ds = load_dataset_file(path)
        stats = store_dataset(s, ds)
    from app.downlink.outbox import rebuild_outbox

    rebuild_outbox(engine, settings)
    log.info("Veri seti yüklendi: %s (%s)", path, stats)
    return stats


# ============================================================================ okuma
class PersonalData:
    """Bir engine'in veri seti görünümü (bellekte, parmak iziyle önbellekli)."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self._lock = threading.Lock()
        self._version: object = object()
        self._series: dict[str, AstronautSeries] = {}

    def _load(self, session: Session) -> None:
        version = kv_get(session, KV_FINGERPRINT)
        if version == self._version:
            return
        with self._lock:
            crew = session.exec(select(CrewProfile).order_by(CrewProfile.id)).all()
            recs = session.exec(select(DayRecord).order_by(DayRecord.astronaut_id, DayRecord.day_index)).all()
            extra = {(x.astronaut_id, x.day_index): x for x in session.exec(select(DayExtra)).all()}
            info = DatasetInfo.model_validate(kv_get(session, KV_INFO) or {})
            by_id: dict[str, list[DayData]] = {}
            for r in recs:
                x = extra.get((r.astronaut_id, r.day_index))
                by_id.setdefault(r.astronaut_id, []).append(
                    DayData(
                        mission_day=r.mission_day, values=r.values, area_scores=r.area_scores,
                        daily_score=r.daily_score, cumulative_score=r.cumulative_score,
                        health_status=r.health_status, main_concern=r.main_concern,
                        self_care=r.self_care, needs_ground_support=r.needs_ground_support,
                        levels=x.levels if x else None, normal=x.normal if x else None, display=x.display if x else None,
                    )
                )
            self._series = {
                c.id: AstronautSeries(
                    meta=AstronautMeta(id=c.id, age=c.age, sex=c.sex, bmi=c.bmi, mission=c.mission, profile=c.profile),
                    days=by_id[c.id],
                    info=info,
                )
                for c in crew
                if by_id.get(c.id)
            }
            self._version = version

    def all(self, session: Session) -> dict[str, AstronautSeries]:
        self._load(session)
        return self._series

    def ids(self, session: Session) -> list[str]:
        return list(self.all(session))

    def series(self, session: Session, astronaut_id: str) -> AstronautSeries | None:
        return self.all(session).get(astronaut_id)


_DATA: dict[int, PersonalData] = {}


def personal_data(engine: Engine) -> PersonalData:
    pd = _DATA.get(id(engine))
    if pd is None or pd.engine is not engine:
        pd = _DATA[id(engine)] = PersonalData(engine)
    return pd
