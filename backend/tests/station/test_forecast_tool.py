"""Gelecek hafta tahmini (ML) — "Asistana sor" tool'u: çağrılır, sayılar kaynaklı, gemiden çıkmaz,
ML yığını yoksa sohbet bozulmaz; model referans örnekleri (tolerans içinde) yeniden üretir."""

import json
import os
from pathlib import Path

import pytest
from sqlmodel import Session, func, select

from app.config import REPO_ROOT
from app.llm import forecast_tool
from app.models.tables import OutboxEvent

from .conftest import login
from .test_assistant import chat

pytest.importorskip("sklearn")
pytest.importorskip("joblib")

FUTURE_EN = "What will my health look like next week?"
FUTURE_TR = "Önümüzdeki hafta uykum nasıl olacak?"


def outbox_count(app) -> int:
    with Session(app.state.engine) as db:
        return db.exec(select(func.count()).select_from(OutboxEvent)).one()


def test_ml_stack_loads() -> None:
    assert forecast_tool.ml_available()


def test_future_question_calls_forecast_tool(ship_client, ship_app) -> None:
    auth = login(ship_client, "A003")
    before = outbox_count(ship_app)
    evs = chat(ship_client, auth, FUTURE_EN, lang="en")
    call = next(d for n, d in evs if n == "tool_call")
    assert call["name"] == "get_week_forecast"
    result = next(d for n, d in evs if n == "tool_result")
    assert result["ok"]
    done = next(d for n, d in evs if n == "done")
    assert "projection" in done["message"] and "reliability is low" in done["message"]
    assert done["ungrounded_numbers"] == []
    assert outbox_count(ship_app) == before  # tahmin Dünya'ya gitmez


def test_future_question_turkish(ship_client) -> None:
    auth = login(ship_client, "A003")
    evs = chat(ship_client, auth, FUTURE_TR, lang="tr")
    assert next(d for n, d in evs if n == "tool_call")["name"] == "get_week_forecast"
    msg = next(d for n, d in evs if n == "done")["message"]
    assert "Gelecek hafta tahmini" in msg and "güvenilirliği düşüktür" in msg


def test_forecast_tool_output(ship_app) -> None:
    from app.llm.personal_tools import personal_registry
    from app.llm.tools import ToolContext

    ctx = ToolContext(astronaut_id="A003", lang="en", session_factory=lambda: Session(ship_app.state.engine))
    res = personal_registry().execute(ctx, "get_week_forecast", {})
    assert res.ok, res.error
    d = res.data
    assert d["status"] == "ok" and d["reliability"] == "low" and d["forecasts"]
    for f in d["forecasts"]:
        lo, hi = f["forecast_range_80pct"]
        assert lo <= f["forecast_next_7_day_average"] <= hi
        assert f["risk_next_week"] in ("likely", "possible", "low")
        assert "_" not in f["reading"]  # iç kolon adı değil, katalog etiketi


def test_ml_unavailable_does_not_break_chat(ship_client, monkeypatch) -> None:
    def boom():
        raise forecast_tool.ForecastUnavailable("simulated: scikit-learn missing")

    monkeypatch.setattr(forecast_tool, "_ml", boom)
    auth = login(ship_client, "A003")
    evs = chat(ship_client, auth, FUTURE_EN, lang="en")
    result = next(d for n, d in evs if n == "tool_result")
    assert result["ok"]  # tool hata fırlatmaz; status: unavailable döner
    done = next(d for n, d in evs if n == "done")
    assert "No forecast is available" in done["message"]


def test_adapter_baseline_and_status() -> None:
    from app.personal.dataset import load_dataset_file

    ds = load_dataset_file(REPO_ROOT / "data" / "raw" / "astronaut_health.json")
    series = ds.by_id()["A003"]
    records, used = forecast_tool.series_to_payloads(series)
    assert len(records) == len(series.days) and len(used) >= 3
    for i, r in enumerate(records):
        for g in r["gostergeler"]:
            assert (g["z_skor"] is None) == (i < forecast_tool.BASELINE_DAYS)  # baseline döneminde z yok
            assert g["durum"] in ("YEŞİL", "SARI", "KIRMIZI")


def _payloads_file() -> Path | None:
    for p in (os.environ.get("AI_GAMBIT_PAYLOADS"), REPO_ROOT / "data" / "raw" / "ast" / "payloads_tr_mission_iss180.jsonl"):
        if p and Path(p).exists():
            return Path(p)
    return None


@pytest.mark.skipif(_payloads_file() is None, reason="payloads_tr_mission_iss180.jsonl yok (AI_GAMBIT_PAYLOADS ile verin)")
def test_model_reproduces_reference_examples() -> None:
    """Model bu ortamda (backend venv) referans çıktıları üretir. pandas/numpy eğitimdekinden yeni olduğu için
    0,01'lik yuvarlama farkı ve eşit sıralı göstergelerin yer değiştirmesi olabilir: gösterge adıyla, ±0,02 karşılaştır."""
    forecast_tool._ml()  # sys.path'e ai-gambit-ml eklenir
    from predict import forecast_from_records  # type: ignore[import-not-found]

    recs = [json.loads(line) for line in _payloads_file().open(encoding="utf-8")]
    ex = REPO_ROOT / "ai-gambit-ml" / "examples"
    for name, aid, day in (("AST-02_day156", "AST-02", 156), ("AST-02_day166", "AST-02", 166)):
        exp = json.loads((ex / f"{name}.json").read_text(encoding="utf-8"))
        out = forecast_from_records(recs, aid, day)
        got = {f["indicator"]: f for f in out["forecasts"]}
        assert set(got) == {f["indicator"] for f in exp["forecasts"]}
        for f in exp["forecasts"]:
            g = got[f["indicator"]]
            assert g["risk_next_week"] == f["risk_next_week"] and g["status_forecast"] == f["status_forecast"]
            for k in ("forecast_next_7_day_mean", "last_7_day_mean", "z_forecast"):
                assert g[k] == pytest.approx(f[k], abs=0.02), (name, f["indicator"], k)


def test_disclaimer_added_only_when_missing() -> None:
    assert forecast_tool.forecast_disclaimer("Sleep 6.3 h next week.", "en").strip().startswith("_This is a projection")
    assert "projeksiyonudur" in forecast_tool.forecast_disclaimer("Uyku 6,3 saat.", "tr")
    ok = "This is a projection, not a diagnosis; reliability is low."
    assert forecast_tool.forecast_disclaimer(ok, "en") == ""
