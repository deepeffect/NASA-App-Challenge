"""AI Gambit final dataset v1 adaptörü ve seed yükleyicisi."""

import os
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.data.seed import seed_final_dataset
from app.ingest.final_dataset import load_final_dataset, map_crew_id, resolve_root
from app.ingest.pipeline import ingest_bytes
from app.models import tables  # noqa: F401
from app.models.tables import Astronaut, Checkin, Measurement

MINI = Path(__file__).parent / "fixtures" / "final_dataset_mini"
REPO_ROOT = Path(__file__).resolve().parents[2]
REAL = Path(os.environ.get("FINAL_DATASET_DIR", REPO_ROOT / "data" / "raw" / "ai_gambit_final_dataset_v1"))


def _engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("A1", "AST-01"), ("M4", "AST-04"), (" a2 ", "AST-02"), ("AST-03", "AST-03"), ("habitat", "habitat")],
)
def test_map_crew_id(raw, expected):
    assert map_crew_id(raw) == expected


def test_ingest_upload_picks_final_adapter():
    content = (MINI / "mission_iss180" / "daily_long.csv").read_bytes()
    with Session(_engine()) as s:
        r = ingest_bytes(s, "daily_long.csv", content)
        rows = list(s.exec(select(Measurement)).all())
        ids = set(s.exec(select(Astronaut.id)).all())
    assert r.adapter == "final_dataset_long"
    assert r.rows_rejected == 0 and r.unknown_metrics == []
    assert ids == {"AST-01", "AST-02"}  # 'habitat' astronot olarak oluşturulmaz
    by = {(m.astronaut_id, m.metric): m for m in rows}
    # alias'lar katalog adlarına çözülür
    assert by[("AST-01", "resting_hr")].value == 60.5
    assert ("AST-01", "bp_systolic") in by and ("AST-01", "body_temp") in by
    assert ("AST-02", "il6") in by and ("AST-02", "sleep_medication") in by
    # habitat radyasyonu her mürettebat üyesine kopyalanır, kaynak etiketi korunur; mSv/day → mSv
    for aid in ("AST-01", "AST-02"):
        dose = by[(aid, "radiation_daily_dose")]
        assert (dose.value, dose.unit, dose.source) == (0.61, "mSv", "derived:radlab:DosTel2")
        assert (aid, "radiation_cumulative") in by
    # boşluk satırı ve ortam bağlamı yüklenmez
    assert not any(m.metric == "resting_hr" and m.timestamp.day == 2 for m in rows)
    assert len(rows) == 3 + 3 + 2 * 2


def test_load_reports_skipped_context():
    data = load_final_dataset(MINI, "mission_iss180")
    assert data.stats.missing_rows_dropped == 1
    assert data.stats.habitat_rows_shared == 4
    assert data.stats.habitat_metrics_skipped == {"cabin_co2": 1, "daily_absorbed_dose": 1}
    assert any("cabin_co2" in w for w in data.warnings)
    assert [a["name"] for a in data.astronauts] == ["Test Kisi Bir", "Test Kisi Iki"]


def test_seed_checkins_privacy_and_emergency():
    engine = _engine()
    stats = seed_final_dataset(MINI, "mission_iss180", engine=engine)
    assert (stats["astronauts"], stats["checkins"], stats["emergency_checkins"]) == (2, 3, 1)
    with Session(engine) as s:
        rows = list(s.exec(select(Checkin).order_by(Checkin.id)).all())
    red = next(c for c in rows if c.emergency)
    assert red.astronaut_id == "AST-02" and red.share_with_ground is False and "racing" in red.note
    assert rows[0].share_with_ground is True
    assert next(c for c in rows if c.note is None).astronaut_id == "AST-02"  # boş not → None


def test_resolve_root_nested_and_missing(tmp_path):
    assert resolve_root(MINI) == MINI
    with pytest.raises(FileNotFoundError):
        resolve_root(tmp_path)
    with pytest.raises(FileNotFoundError):
        seed_final_dataset(tmp_path, engine=_engine())  # DB'ye dokunmadan hata


# --------------------------------------------------------------------------- gerçek dataset (varsa)
needs_real = pytest.mark.skipif(
    not (REAL / "mission_iss180" / "daily_long.csv").is_file(),
    reason="final dataset yok (data/raw/ai_gambit_final_dataset_v1 veya FINAL_DATASET_DIR)",
)


@needs_real
@pytest.mark.parametrize("part", ["mission_iss180", "control_iss180", "mission_mars860"])
def test_real_dataset_loads_cleanly(part):
    data = load_final_dataset(REAL, part)
    assert data.rejected == 0 and data.unknown_metrics == {}
    assert [a["id"] for a in data.astronauts] == ["AST-01", "AST-02", "AST-03", "AST-04"]


@needs_real
def test_real_iss_scenario_and_red_flag():
    from app.analysis.engine import AnalysisEngine
    from app.models.schemas import AstronautInfo

    data = load_final_dataset(REAL, "mission_iss180")
    # gerçek RadLab satırları kaynak etiketiyle her astronota kopyalanmış
    rad = data.measurements[data.measurements["metric"] == "radiation_daily_dose"]
    assert set(rad["source"]) == {"derived:radlab:DosTel2"} and rad["astronaut_id"].nunique() == 4
    # kırmızı bayrak notu: A2, gün 168 (2026-06-17), yer ekibiyle paylaşılmamış, kural tabanlı acil
    flagged = [c for c in data.checkins if c["emergency"]]
    assert len(flagged) == 1
    assert flagged[0]["astronaut_id"] == "AST-02" and flagged[0]["share_with_ground"] is False
    assert flagged[0]["timestamp"].date() == date(2026, 6, 17)
    # A2 zinciri: görev sonunda uyku, davranışsal ve kardiyovasküler metriklerde olay var
    astros = [AstronautInfo(id=a["id"], name=a["name"]) for a in data.astronauts]
    res = AnalysisEngine().run(data.measurements, astros)
    a2 = res.astronauts["AST-02"]
    assert a2.overall.status == "red"
    metrics = {e.contributors[0].metric for e in a2.active_events if e.contributors and e.severity != "info"}
    assert {"sleep_duration", "stress", "hrv_rmssd", "resting_hr"} <= metrics
