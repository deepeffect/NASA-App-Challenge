"""Sentetik veriyi DB'ye yükle: `python -m app.cli seed`."""

from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel

from app.data.synthetic import SyntheticConfig, generate
from app.db import get_engine
from app.ingest.store import ensure_astronauts, insert_measurements
from app.models import tables  # noqa: F401  (tabloları metadata'ya kaydeder)
from app.models.tables import Checkin, IngestBatch, as_utc


def seed_database(cfg: SyntheticConfig | None = None, reset: bool = True, engine: Engine | None = None) -> dict:
    cfg = cfg or SyntheticConfig()
    engine = engine or get_engine()
    if reset:
        SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)

    data = generate(cfg)
    with Session(engine) as s:
        ensure_astronauts(s, [a["id"] for a in data.astronauts], {a["id"]: a for a in data.astronauts})
        label = f"synthetic(seed={cfg.seed}, days={cfg.days}, spe_day={cfg.spe_day})"
        batch = IngestBatch(filename=label, adapter="synthetic", rows_total=len(data.measurements))
        s.add(batch)
        s.flush()
        inserted = insert_measurements(s, data.measurements, batch.id)
        batch.rows_accepted = inserted
        batch.rows_duplicate = len(data.measurements) - inserted
        s.add_all(Checkin(**{**c, "timestamp": as_utc(c["timestamp"])}) for c in data.checkins)
        s.commit()

    return {
        "astronauts": len(data.astronauts),
        "measurements": inserted,
        "checkins": len(data.checkins),
        "start": cfg.start.isoformat(),
        "days": cfg.days,
        "scenario_astronaut": cfg.scenario_astronaut,
        "scenario_day": cfg.scenario_day,
        "spe_day": cfg.spe_day,
    }
