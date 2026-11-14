"""Sentetik veriyi DB'ye yükle: `python -m app.cli seed`."""

from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel

from pathlib import Path

import pandas as pd

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
    label = f"synthetic(seed={cfg.seed}, days={cfg.days}, spe_day={cfg.spe_day})"
    inserted = _write(engine, data.astronauts, data.measurements, data.checkins, label, "synthetic")

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


def _write(engine: Engine, astronauts: list[dict], measurements: pd.DataFrame, checkins: list[dict],
           label: str, adapter: str, warnings: list[str] | None = None) -> int:
    """Astronotları, ölçümleri ve check-in'leri tek batch olarak yaz. Eklenen ölçüm sayısını döner."""
    with Session(engine) as s:
        ensure_astronauts(s, [a["id"] for a in astronauts], {a["id"]: a for a in astronauts})
        batch = IngestBatch(filename=label, adapter=adapter, rows_total=len(measurements), warnings=warnings or [])
        s.add(batch)
        s.flush()
        inserted = insert_measurements(s, measurements, batch.id)
        batch.rows_accepted = inserted
        batch.rows_duplicate = len(measurements) - inserted
        s.add_all(Checkin(**{**c, "timestamp": as_utc(c["timestamp"])}) for c in checkins)
        s.commit()
    return inserted


def seed_final_dataset(path: str | Path, part: str = "mission_iss180", reset: bool = True,
                       engine: Engine | None = None) -> dict:
    """AI Gambit final dataset v1'in bir senaryosunu DB'ye yükle: `python -m app.cli seed --final-dataset`."""
    from app.ingest.final_dataset import load_final_dataset

    data = load_final_dataset(path, part)  # önce oku: dosya yoksa DB'ye dokunmadan hata ver
    engine = engine or get_engine()
    if reset:
        SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)

    label = f"final_dataset_v1:{part}"
    inserted = _write(engine, data.astronauts, data.measurements, data.checkins, label, "final_dataset_long", data.warnings)
    ts = data.measurements["timestamp"]
    return {
        "part": part,
        "root": str(data.root),
        "astronauts": len(data.astronauts),
        "measurements": inserted,
        "checkins": len(data.checkins),
        "emergency_checkins": sum(1 for c in data.checkins if c["emergency"]),
        "start": ts.min().date().isoformat() if len(ts) else None,
        "end": ts.max().date().isoformat() if len(ts) else None,
        "missing_rows_dropped": data.stats.missing_rows_dropped,
        "habitat_rows_shared": data.stats.habitat_rows_shared,
        "rows_rejected": data.rejected,
        "unknown_metrics": data.unknown_metrics,
        "warnings": data.warnings,
    }
