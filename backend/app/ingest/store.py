"""Ortak long tabloyu DB'ye yazma (ingest ve seed ortak kullanır)."""

from collections.abc import Iterable

import pandas as pd
from sqlalchemy import func, insert, select
from sqlmodel import Session

from app.models.tables import Astronaut, Measurement, as_utc

_CHUNK = 5000
_COLS = ["astronaut_id", "timestamp", "metric", "value", "unit", "source"]


def ensure_astronauts(session: Session, ids: Iterable[str], info: dict[str, dict] | None = None) -> list[str]:
    """Olmayan astronotları oluştur; oluşturulanların ID'lerini döndür."""
    info = info or {}
    existing = set(session.execute(select(Astronaut.id)).scalars().all())
    created = []
    for aid in sorted(set(ids)):
        if aid not in existing:
            meta = info.get(aid, {})
            session.add(Astronaut(id=aid, name=meta.get("name", aid), role=meta.get("role")))
            created.append(aid)
    session.flush()
    return created


def measurement_count(session: Session) -> int:
    return session.execute(select(func.count()).select_from(Measurement)).scalar_one()


def insert_measurements(session: Session, df: pd.DataFrame, batch_id: int | None) -> int:
    """(astronaut_id, metric, timestamp, source) tekrarlarını sessizce atlar. Eklenen satır sayısını döner.

    `timestamp` naive ise UTC kabul edilir.
    """
    if df.empty:
        return 0
    before = measurement_count(session)
    rows = [
        {
            "astronaut_id": str(r.astronaut_id),
            "timestamp": as_utc(r.timestamp),
            "metric": str(r.metric),
            "value": float(r.value),
            "unit": str(r.unit),
            "source": str(r.source),
            "batch_id": batch_id,
        }
        for r in df[_COLS].itertuples(index=False)
    ]
    stmt = insert(Measurement).prefix_with("OR IGNORE")
    for i in range(0, len(rows), _CHUNK):
        session.execute(stmt, rows[i : i + _CHUNK])
    session.flush()
    return measurement_count(session) - before
