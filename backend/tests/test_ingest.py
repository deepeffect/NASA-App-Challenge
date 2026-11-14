import json

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.ingest.pipeline import IngestError, ingest_bytes
from app.models import tables  # noqa: F401
from app.models.tables import Astronaut, Measurement


@pytest.fixture
def session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _rows(session: Session) -> list[Measurement]:
    return list(session.exec(select(Measurement).order_by(Measurement.id)).all())


def test_long_csv(session):
    csv = (
        "astronaut_id,timestamp,metric,value,unit,source\n"
        "AST-01,2026-11-14T08:00:00Z,resting_hr,61,bpm,wearable\n"
        "AST-01,2026-11-14T08:00:00Z,RHR,62,bpm,other\n"          # alias
        "AST-01,2026-11-14T08:00:00Z,cortisol,12,ug/dL,lab\n"      # bilinmeyen metrik
        "AST-01,not-a-date,resting_hr,60,bpm,wearable\n"           # bozuk zaman
        "AST-01,2026-11-14T09:00:00Z,resting_hr,abc,bpm,wearable\n"  # bozuk değer
    )
    r = ingest_bytes(session, "x.csv", csv.encode())
    assert r.adapter == "long_csv"
    assert (r.rows_total, r.rows_accepted, r.rows_rejected) == (5, 2, 3)
    assert r.unknown_metrics == ["cortisol"]
    reasons = {e.reason for e in r.errors_sample}
    assert reasons == {"unknown_metric", "invalid_timestamp", "invalid_value"}
    assert {e.row for e in r.errors_sample} == {4, 5, 6}
    assert {m.metric for m in _rows(session)} == {"resting_hr"}
    assert session.get(Astronaut, "AST-01") is not None  # otomatik oluşturuldu


def test_duplicates_are_idempotent(session):
    csv = "astronaut_id,timestamp,metric,value\nAST-01,2026-11-14T08:00:00Z,spo2,97\n"
    first = ingest_bytes(session, "a.csv", csv.encode())
    second = ingest_bytes(session, "a.csv", csv.encode())
    assert first.rows_accepted == 1
    assert (second.rows_accepted, second.rows_duplicate) == (0, 1)
    assert len(_rows(session)) == 1


def test_wide_csv_semicolon_aliases_and_units(session):
    csv = (
        "Subject;Time;rhr;hrv;temperature;weight;unit_ignored\n"
        "AST-03;2026-11-14 07:00;58;55;37.1;;x\n"
    )
    r = ingest_bytes(session, "wide.csv", csv.encode())
    assert r.adapter == "wide_csv"
    by_metric = {m.metric: m for m in _rows(session)}
    assert set(by_metric) == {"resting_hr", "hrv_rmssd", "body_temp"}  # boş 'weight' atlanır
    # wide formatta birim kolonu yok → katalog birimi varsayılır
    assert by_metric["body_temp"].unit == "degC"
    assert by_metric["body_temp"].value == pytest.approx(37.1)
    assert r.unknown_metrics == ["unit_ignored"]


def test_unit_conversion_long(session):
    csv = (
        "astronaut_id,timestamp,metric,value,unit\n"
        "AST-01,2026-11-14T07:00:00Z,body_temp,98.6,°F\n"
        "AST-01,2026-11-14T07:00:00Z,body_mass,165,lb\n"
        "AST-01,2026-11-14T07:00:00Z,sleep_duration,420,min\n"
        "AST-01,2026-11-14T07:00:00Z,resting_hr,60,furlongs\n"
    )
    r = ingest_bytes(session, "u.csv", csv.encode())
    assert r.rows_accepted == 3 and r.rows_rejected == 1
    assert r.errors_sample[0].reason == "unit_mismatch"
    v = {m.metric: m.value for m in _rows(session)}
    assert v["body_temp"] == pytest.approx(37.0)
    assert v["body_mass"] == pytest.approx(74.84, abs=0.01)
    assert v["sleep_duration"] == pytest.approx(7.0)


def test_default_astronaut_and_epoch(session):
    csv = "timestamp,metric,value\n1794643200,resting_hr,60\n1794643200000,spo2,98\n"
    r = ingest_bytes(session, "e.csv", csv.encode(), default_astronaut="AST-04")
    assert r.rows_accepted == 2
    assert r.astronauts == ["AST-04"]
    assert r.date_range is not None and r.date_range.start.year == 2026


def test_missing_astronaut_rejected(session):
    csv = "timestamp,metric,value\n2026-11-14T07:00:00Z,resting_hr,60\n"
    r = ingest_bytes(session, "m.csv", csv.encode())
    assert r.rows_accepted == 0 and r.errors_sample[0].reason == "missing_astronaut"


def test_json_long_and_wide(session):
    long = [{"astronaut_id": "AST-02", "timestamp": "2026-11-14T07:00:00Z", "metric": "stress", "value": 4}]
    r = ingest_bytes(session, "l.json", json.dumps(long).encode())
    assert (r.adapter, r.rows_accepted) == ("json_records", 1)

    wide = {"astronaut_id": "AST-02", "measurements": [{"timestamp": "2026-11-13T07:00:00Z", "resting_hr": 70, "mood": 2}]}
    r = ingest_bytes(session, "w.json", json.dumps(wide).encode())
    assert r.rows_accepted == 2
    assert {m.metric for m in _rows(session)} == {"stress", "resting_hr", "mood"}


def test_unrecognized_format(session):
    with pytest.raises(IngestError):
        ingest_bytes(session, "x.txt", b"hello world\nfoo bar\n")
    with pytest.raises(IngestError):
        ingest_bytes(session, "x.csv", b"a,b\n1,2\n", adapter_name="nope")
