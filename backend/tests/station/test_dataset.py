"""Veri seti adaptörleri, katalog ve gemi DB'sine yükleme."""

import copy

import pytest
from sqlmodel import Session, func, select

from app.models.tables import CrewProfile, DayRecord
from app.personal.dataset import DatasetError, parse_dataset
from app.personal.store import ensure_dataset_loaded, personal_data

from .prototype import embedded_data


def test_catalog_matches_prototype_verbatim(catalog) -> None:
    """Sayılar ve İngilizce metinler prototipten birebir (sıra dahil)."""
    emb = embedded_data()
    assert [i.col for i in catalog.indicators] == [i["col"] for i in emb["indicators"]]
    for ours, ref in zip(catalog.indicators, emb["indicators"], strict=True):
        assert (ours.domain, ours.label.en, ours.unit.en, ours.dec, ours.action, ours.trig) == (
            ref["domain"], ref["label"], ref["unit"], ref["dec"], ref["action"], ref["trig"]), ref["col"]
        assert (ours.healthy.min, ours.healthy.max, ours.warning.min, ours.warning.max) == (
            ref["hmin"], ref["hmax"], ref["cmin"], ref["cmax"]), ref["col"]
    assert [s.code for s in catalog.solutions] == [s["code"] for s in emb["solutions"]]
    for ours, ref in zip(catalog.solutions, emb["solutions"], strict=True):
        assert ours.domain == ref["domain"]
        assert ours.title.en == ref["title"] and ours.when.en == ref["when"]
        assert ours.do_yourself.en == ref["do_yourself"]
        assert ours.contact_ground_if.en == ref["contact_ground_if"]
        assert ours.basis.en == ref["basis"]
        assert len(ours.do_yourself.tr) == len(ref["do_yourself"]), f"{ours.code}: TR adım sayısı farklı"


def test_catalog_flags(catalog) -> None:
    assert catalog.threshold_source == "dataset" and catalog.verified is False
    assert catalog.private_columns == {"beh_mood_score", "beh_stress_score"}
    assert [s.en for s in catalog.statuses] == ["Normal", "Needs attention", "Unwell"]
    assert [s.tr for s in catalog.statuses] == ["Normal", "Dikkat", "Rahatsız"]


def test_reconstructed_file_equals_prototype_embedded(dataset, catalog) -> None:
    """İki format aynı sonucu verir (orijinal gelince aynı test onun adaptörü için yazılır)."""
    from_embedded = parse_dataset(embedded_data(), cat=catalog)
    assert dataset.adapter == "reconstructed" and from_embedded.adapter == "prototype_embedded"
    assert from_embedded.astronauts == dataset.astronauts


def test_dataset_shape(dataset) -> None:
    by_id = dataset.by_id()
    assert len(by_id) == 200 and min(by_id) == "A000" and max(by_id) == "A199"
    a = by_id["A000"]
    assert len(a.days) == 30 and a.today_index == 29
    assert [d.mission_day for d in a.days] == list(range(126, 156))  # görev günleri korunur
    assert a.days[0].self_care == ["STOP_AND_RECORD_HEART", "HEART_RECOVERY_DAY"]  # act [2, 7]


def test_unknown_self_care_code_is_rejected(catalog) -> None:
    raw = copy.deepcopy(embedded_data())
    raw["solutions"][0]["code"] = "NOT_A_CODE"
    with pytest.raises(DatasetError, match="NOT_A_CODE"):
        parse_dataset(raw, cat=catalog)


def test_unknown_format_is_rejected(catalog) -> None:
    with pytest.raises(DatasetError, match="tanınmadı"):
        parse_dataset({"foo": []}, cat=catalog)


def test_ship_startup_loads_dataset(ship_client, ship_app) -> None:
    engine = ship_app.state.engine
    with Session(engine) as s:
        assert s.exec(select(func.count()).select_from(CrewProfile)).one() == 200
        assert s.exec(select(func.count()).select_from(DayRecord)).one() == 6000
        series = personal_data(engine).series(s, "A003")
    assert series is not None and series.days[-1].mission_day == 30 and series.meta.profile == "acute_episode"


def test_dataset_load_is_idempotent(ship_client, ship_app, ship_settings) -> None:
    assert ensure_dataset_loaded(ship_app.state.engine, ship_settings) is None  # parmak izi aynı
    stats = ensure_dataset_loaded(ship_app.state.engine, ship_settings, force=True)
    assert stats == {"astronauts": 200, "days": 6000, "adapter": "reconstructed"}


def test_astronaut_health_mode_closes_legacy_api(ship_client) -> None:
    info = ship_client.get("/api/station").json()
    assert info["data_source"] == "astronaut_health" and info["legacy_enabled"] is False
    for path in ["/api/crew", "/api/alerts", "/api/ground-report", "/api/metrics/catalog"]:
        assert ship_client.get(path).status_code == 404, path
    assert ship_client.put("/api/alerts/x/share", json={"share_with_ground": True}).status_code in (404, 405)
