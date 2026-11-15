"""Gelecek hafta tahmini — "Asistana sor" tool'u (ai-gambit-ml, forecast_v2).

Model (ai-gambit-ml/predict.py) payload kayıtlarıyla eğitildi: her gün için değer + kural motorunun z'si
+ durumu. Yeni veri setinde (astronaut_health) z ve durum yok; burada aynı tanımla üretilir:
  - kişisel baseline = astronotun ilk BASELINE_DAYS günü (ortalama, std)
  - z = son 7 günün ortalamasının baseline'a göre z'si (payload z'sine en yakın tanım)
  - durum: kötü yönde z ≥ 2 → SARI, ≥ 3 → KIRMIZI (forecast_core.SARI_Z / KIRMIZI_Z ile aynı)
Bu veri setinde model eğitim dışıdır: geriye dönük ölçümde hata (z) 0,54 (kendi verisinde 0,33; "son hafta
aynen devam" 0,57). Tool bu yüzden `reliability: "low"` döndürür; LLM bunu söylemek zorundadır.

Sayılar modelden (Python) gelir, LLM aynen aktarır (CLAUDE.md kural 1). ML yığını (scikit-learn, joblib,
model dosyası) yoksa ya da hata verirse tool `status: "unavailable"` döner; sohbet ve check-in etkilenmez (kural 2).
Sadece giriş yapan astronotun verisi kullanılır; sonuç gemiden çıkmaz (downlink'e yazılmaz).
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from functools import lru_cache
from typing import Any

import numpy as np
from pydantic import BaseModel, ConfigDict
from sqlmodel import Session

from app.config import REPO_ROOT
from app.llm.tools import ToolContext, ToolSpec
from app.personal.catalog import load_personal_catalog
from app.personal.dataset import AstronautSeries
from app.personal.store import personal_data

ML_DIR = REPO_ROOT / "ai-gambit-ml"
BASELINE_DAYS = 14
WINDOW = 7
# Geriye dönük ölçüm (astronaut_health, 200 astronot, gün 22'deki tahmin → 23-29. günler): ortalama hata (z)
MEASURED_MAE_Z = 0.54
PERSISTENCE_MAE_Z = 0.57

# astronaut_health kolonu -> (payload gösterge adı, kötüleşme yönü: +1 artış kötü, -1 azalış kötü)
COLUMNS: dict[str, tuple[str, int]] = {
    "cv_resting_hr_bpm": ("Dinlenik nabız", +1),
    "beh_sleep_h": ("Uyku süresi", -1),
    "cv_hrv_ms": ("Kalp hızı değişkenliği (HRV)", -1),
    "beh_stress_score": ("Stres", +1),
    "bone_exercise_min": ("Egzersiz süresi", -1),
    "beh_mood_score": ("Ruh hali", -1),
    "imm_body_temp_C": ("Vücut sıcaklığı", +1),
    "cv_systolic_bp_mmHg": ("Kan basıncı", +1),
}
_TR_TO_COL = {v[0]: c for c, v in COLUMNS.items()}


class ForecastUnavailable(RuntimeError):
    """ML yığını yüklenemedi (paket, model dosyası veya ai-gambit-ml klasörü yok)."""


@lru_cache(maxsize=1)
def _ml() -> tuple[Any, Any]:
    """ai-gambit-ml modüllerini ve modeli bir kez yükler. Klasör adı tireli (paket değil) → sys.path'in SONUNA eklenir."""
    if not (ML_DIR / "predict.py").exists():
        raise ForecastUnavailable(f"ai-gambit-ml not found at {ML_DIR}")
    if str(ML_DIR) not in sys.path:
        sys.path.append(str(ML_DIR))
    try:
        import forecast_core  # type: ignore[import-not-found]
        import predict  # type: ignore[import-not-found]

        model = predict.load_model()
    except Exception as e:  # noqa: BLE001 — paket/model yoksa sohbet düşmemeli
        raise ForecastUnavailable(f"{type(e).__name__}: {e}") from e
    return forecast_core, model


def ml_available() -> bool:
    try:
        _ml()
        return True
    except ForecastUnavailable:
        return False


# --------------------------------------------------------------------------- veri dönüştürücü
def series_to_payloads(series: AstronautSeries) -> tuple[list[dict], list[str]]:
    """AstronautSeries -> payload kayıtları (forecast_core.load_payloads biçimi). İkinci değer: kullanılan kolonlar.

    Baseline döneminde 5'ten az ölçümü olan ya da sabit (std 0) kolon atlanır; o gün ölçülmeyen değer kayda girmez.
    """
    days = series.days
    used: list[str] = []
    stats: dict[str, tuple[np.ndarray, float, float]] = {}
    for col in COLUMNS:
        v = np.array([d.values.get(col, np.nan) for d in days], dtype=float)
        base = v[:BASELINE_DAYS]
        base = base[~np.isnan(base)]
        if len(base) < 5:
            continue
        sd = float(base.std(ddof=1))
        if not sd > 0:
            continue
        stats[col] = (v, float(base.mean()), sd)
        used.append(col)

    records = []
    for i in range(len(days)):
        inds = []
        for col in used:
            v, mu, sd = stats[col]
            if np.isnan(v[i]):
                continue
            ad, sign = COLUMNS[col]
            z = None
            durum = "YEŞİL"
            if i >= BASELINE_DAYS:
                win = v[max(0, i - WINDOW + 1): i + 1]
                win = win[~np.isnan(win)]
                if len(win):
                    z = round(float((win.mean() - mu) / sd), 1)
                    bz = z * sign
                    durum = "KIRMIZI" if bz >= 3 else ("SARI" if bz >= 2 else "YEŞİL")
            inds.append({"ad": ad, "deger": float(v[i]), "birim": col, "z_skor": z, "durum": durum, "trend": None})
        records.append({"astronot_id": series.meta.id, "gorev_gunu": i + 1, "gostergeler": inds})
    return records, used


def forecast_for_series(series: AstronautSeries) -> dict[str, Any]:
    """Modelin ham tahmin JSON'u (forecast_core.forecast_json) — bugün (son kayıt) itibarıyla."""
    core, model = _ml()
    records, used = series_to_payloads(series)
    if len(series.days) < BASELINE_DAYS + WINDOW or len(used) < 3:
        return {"status": "insufficient_data", "days_available": len(series.days),
                "days_needed": BASELINE_DAYS + WINDOW}
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        tmp = fh.name
    try:
        long = core.load_payloads(tmp, "live")
    finally:
        os.unlink(tmp)
    tab = core.series_tables(long)[("live", series.meta.id)]
    return core.forecast_json(model, tab, series.meta.id, len(series.days), audience="astronaut")


# --------------------------------------------------------------------------- tool
_RISK_TEXT = {
    "likely": "the central forecast reaches the caution level next week",
    "possible": "only the worst case of the 80% range reaches the caution level",
    "low": "expected to stay within the personal normal",
}


class ForecastArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")  # model astronaut_id gönderse bile yok sayılır


def _fmt(x: float | None, dec: int) -> float | None:
    return None if x is None else round(float(x), dec)


def get_week_forecast(ctx: ToolContext, session: Session, _args: ForecastArgs) -> dict[str, Any]:
    series = personal_data(session.get_bind()).series(session, ctx.astronaut_id)  # type: ignore[arg-type]
    if series is None:
        raise ValueError("no data for the logged-in astronaut")
    base = {"astronaut_id": series.meta.id, "horizon": "next 7 days (average)", "based_on": "last 7 days"}
    try:
        raw = forecast_for_series(series)
    except ForecastUnavailable as e:
        return {**base, "status": "unavailable",
                "note": "The forecast model is not available on this ship computer; do not guess a forecast.",
                "detail": str(e)[:200]}
    if raw.get("status") == "insufficient_data":
        return {**base, **raw, "note": "Not enough days yet for a forecast; do not guess one."}
    if raw.get("status") == "no_data" or not raw.get("forecasts"):
        return {**base, "status": "no_data", "note": "No forecast could be made; do not guess one."}

    cat = load_personal_catalog()
    by_col = {i.col: i for i in cat.indicators}
    items = []
    for f in raw["forecasts"]:
        col = _TR_TO_COL.get(f.get("indicator_tr", ""))
        if col is None:
            continue
        ind = by_col.get(col)
        dec = ind.dec if ind else 1
        lo, hi = (f.get("forecast_range_80pct") or [None, None])[:2]
        items.append({
            "reading": ind.label.get(ctx.lang) if ind else col,
            "unit": ind.unit.get(ctx.lang) if ind else "",
            "personal_baseline": _fmt(f.get("personal_baseline"), dec),
            "last_7_day_average": _fmt(f.get("last_7_day_mean"), dec),
            "forecast_next_7_day_average": _fmt(f.get("forecast_next_7_day_mean"), dec),
            "forecast_range_80pct": [_fmt(lo, dec), _fmt(hi, dec)],
            "worse_when": f.get("worse_when"),
            "status_now": f.get("status_now"),
            "status_forecast": f.get("status_forecast"),
            "risk_next_week": f.get("risk_next_week"),
            "risk_meaning": _RISK_TEXT.get(f.get("risk_next_week", ""), ""),
        })
    order = {"likely": 0, "possible": 1, "low": 2}
    items.sort(key=lambda x: order.get(x["risk_next_week"] or "low", 3))
    return {
        **base,
        "status": "ok",
        "model": raw.get("model_version"),
        "range_coverage_percent": 80,
        "forecasts": items,
        "reliability": "low",
        "reliability_note": (
            "Projection from an ML model trained on a different (synthetic mission) dataset. On this dataset its "
            f"average error is {MEASURED_MAE_Z} personal standard deviations, only slightly better than assuming "
            f"last week repeats ({PERSISTENCE_MAE_Z}). Personal baseline = the first {BASELINE_DAYS} days in the data."
        ),
        "must_say": "This is a projection, not a diagnosis, and its reliability is low.",
    }


_DISCLAIMER = {
    "en": "\n\n_This is a projection from the onboard ML model, not a diagnosis; its reliability is low._",
    "tr": "\n\n_Bu, gemideki ML modelinin bir projeksiyonudur, teşhis değildir; güvenilirliği düşüktür._",
}
_HAS_PROJECTION = re.compile(r"projection|projeksiyon", re.I)
_HAS_RELIABILITY = re.compile(r"reliab|güvenilir", re.I)


def forecast_disclaimer(message: str, lang: str) -> str:
    """Cevapta "projeksiyon" ve "güvenilirlik düşük" ifadeleri yoksa eklenecek dipnot (yoksa boş)."""
    if _HAS_PROJECTION.search(message or "") and _HAS_RELIABILITY.search(message or ""):
        return ""
    return _DISCLAIMER.get(lang, _DISCLAIMER["en"])


FORECAST_TOOL = ToolSpec(
    "get_week_forecast",
    "Next-week health forecast for the logged-in astronaut from the onboard ML model: for each reading, the "
    "forecast 7-day average, an 80% range and the risk of reaching the caution level. Use it for questions about "
    "next week / the coming days / whether a reading will get worse. Reliability is low; say so.",
    ForecastArgs,
    get_week_forecast,
)
