from datetime import date

import pandas as pd
import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine, select

from app.data.seed import seed_database
from app.data.synthetic import SyntheticConfig, generate
from app.models.tables import Astronaut, Checkin, Measurement
from app.safety.emergency import detect_emergency


@pytest.fixture(scope="module")
def data():
    return generate(SyntheticConfig(seed=42))


def _daily_mean(df: pd.DataFrame, aid: str, metric: str, start: str, end: str) -> float:
    m = df[(df.astronaut_id == aid) & (df.metric == metric) & (df.timestamp >= start) & (df.timestamp < end)]
    return float(m.value.mean())


def test_deterministic():
    a = generate(SyntheticConfig(seed=7)).measurements
    b = generate(SyntheticConfig(seed=7)).measurements
    pd.testing.assert_frame_equal(a, b)
    c = generate(SyntheticConfig(seed=8)).measurements
    assert not a["value"].equals(c["value"])


def test_shape(data):
    df = data.measurements
    assert {a["id"] for a in data.astronauts} == {"AST-01", "AST-02", "AST-03", "AST-04"}
    assert df.timestamp.min().date() == date(2026, 5, 19)
    assert df.timestamp.max().date() == date(2026, 11, 14)
    assert set(df.columns) == {"astronaut_id", "timestamp", "metric", "value", "unit", "source"}
    hourly = df[df.metric == "heart_rate"].groupby("astronaut_id").size()
    assert (hourly > 180 * 20).all(), "saatlik nabız ~24/gün olmalı"
    assert not df.duplicated(["astronaut_id", "metric", "timestamp", "source"]).any()


def test_units_match_catalog(data):
    from app.analysis.catalog import load_catalog

    cat = load_catalog()
    units = data.measurements.groupby("metric")["unit"].first().to_dict()
    for metric, unit in units.items():
        assert cat.metrics[metric].unit == unit, metric


def test_demo_scenario(data):
    df = data.measurements
    before, after = ("2026-06-02", "2026-10-14"), ("2026-10-28", "2026-11-15")
    # AST-02: uyku ↓, stres ↑, HRV ↓, nabız ↑
    assert _daily_mean(df, "AST-02", "sleep_duration", *after) < _daily_mean(df, "AST-02", "sleep_duration", *before) - 1.5
    assert _daily_mean(df, "AST-02", "stress", *after) > _daily_mean(df, "AST-02", "stress", *before) + 1.2
    assert _daily_mean(df, "AST-02", "hrv_rmssd", *after) < _daily_mean(df, "AST-02", "hrv_rmssd", *before) - 10
    assert _daily_mean(df, "AST-02", "resting_hr", *after) > _daily_mean(df, "AST-02", "resting_hr", *before) + 7
    # diğerleri stabil
    for aid in ("AST-01", "AST-03", "AST-04"):
        for metric, tol in (("sleep_duration", 0.4), ("resting_hr", 2.0), ("hrv_rmssd", 4.0), ("stress", 0.5)):
            diff = abs(_daily_mean(df, aid, metric, *after) - _daily_mean(df, aid, metric, *before))
            assert diff < tol, (aid, metric, diff)


def test_cascade_order(data):
    """Uyku düşüşü, stres artışından ve nabız artışından önce başlar."""
    df = data.measurements
    sleep_drop = _daily_mean(df, "AST-02", "sleep_duration", "2026-10-15", "2026-10-18")
    sleep_base = _daily_mean(df, "AST-02", "sleep_duration", "2026-06-02", "2026-10-14")
    rhr_early = _daily_mean(df, "AST-02", "resting_hr", "2026-10-15", "2026-10-20")
    rhr_base = _daily_mean(df, "AST-02", "resting_hr", "2026-06-02", "2026-10-14")
    assert sleep_drop < sleep_base - 0.4
    assert abs(rhr_early - rhr_base) < 2.5


def test_spe_scenario():
    base = generate(SyntheticConfig(seed=42)).measurements
    spe = generate(SyntheticConfig(seed=42, spe_day=120)).measurements
    sel = lambda df: df[(df.metric == "radiation_daily_dose") & (df.timestamp.dt.date == date(2026, 9, 16))]  # noqa: E731
    assert (sel(spe).value.to_numpy() > sel(base).value.to_numpy() + 30).all()


def test_notes_do_not_trigger_emergency(data):
    for c in data.checkins:
        assert detect_emergency(c["note"]) is None, c["note"]


def test_scenario_notes_are_consistent(data):
    from app.data.synthetic import NORMAL_NOTES, SCENARIO_NOTES

    late = [c["note"] for c in data.checkins
            if c["astronaut_id"] == "AST-02" and c["timestamp"] >= pd.Timestamp("2026-10-16") and c["note"]]
    assert late and all(n in SCENARIO_NOTES for n in late)
    others = {c["note"] for c in data.checkins if c["astronaut_id"] != "AST-02" and c["note"]}
    assert others <= set(NORMAL_NOTES)


def test_seed_database_roundtrip():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    stats = seed_database(SyntheticConfig(seed=1, days=30), engine=engine)
    with Session(engine) as s:
        assert len(s.exec(select(Astronaut)).all()) == 4
        assert len(s.exec(select(Measurement)).all()) == stats["measurements"] > 0
        assert len(s.exec(select(Checkin)).all()) == stats["checkins"] > 0
    # tekrar seed (reset) → aynı sayı
    stats2 = seed_database(SyntheticConfig(seed=1, days=30), engine=engine)
    assert stats2["measurements"] == stats["measurements"]
