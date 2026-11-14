"""
forecast_core.py  --  Gelecek hafta tahmin modeli: veri okuma, özellik çıkarma, tahmin ve LLM JSON'u.

Fikir
-----
Astronotun SON 7 GÜNÜNE bakıp her sağlık göstergesi için ÖNÜMÜZDEKİ 7 GÜNÜN ORTALAMASINI tahmin eder.
Tahmin, kural motorunun kullandığı ölçekte (z-skor: 7 günlük ortalamanın kişisel baseline'dan
standart sapma cinsinden uzaklığı) yapılır; sonra motorun kendi kuralıyla durum etiketine çevrilir:
    kötü yönde z >= 2  -> SARI,   kötü yönde z >= 3  -> KIRMIZI
Bu sayede "böyle giderse önümüzdeki hafta istirahat nabzın kırmızıya girebilir" denebilir.

Hesaplamayı model yapar, LLM sadece bu JSON'u cümleye döker (sayı uydurmaz).

Veri: Egemen'in payload dosyaları (payloads_tr_*.jsonl). `payloads_ground_*` dosyaları KULLANILMAZ
(aynı seriler, öz bildirimler çıkarılmış).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

HORIZON = 7    # kaç gün sonrası (gelecek haftanın ortalaması)
WINDOW = 7     # model kaç günlük geçmişe bakar
SARI_Z, KIRMIZI_Z = 2.0, 3.0   # payload durum kuralına yakın eşikler (z yuvarlandığı için sınırda farklılaşabilir).
#                                Gerçek veride şimdiki/gelecek durum için motorun kendi `durum` alanı kullanılır;
#                                bu eşikler sadece tahmin etikete çevrilirken ve veri artırılmış kopyalarda kullanılır.
LEVEL = {"YEŞİL": 0, "SARI": 1, "KIRMIZI": 2}
LEVEL_NAME = {0: "GREEN", 1: "YELLOW", 2: "RED"}

# gösterge (payload adı) -> (kısa ad, kötüleşme yönü: +1 = artış kötü, -1 = azalış kötü, İngilizce ad, öz bildirim mi)
INDICATORS: dict[str, tuple[str, int, str, bool]] = {
    "Dinlenik nabız": ("resting_hr", +1, "resting heart rate", False),
    "Uyku süresi": ("sleep_duration", -1, "sleep duration", False),
    "Kalp hızı değişkenliği (HRV)": ("hrv", -1, "heart rate variability (HRV)", False),
    "Stres": ("stress", +1, "stress (self-report)", True),
    "Egzersiz süresi": ("exercise", -1, "exercise time", False),
    "Tepki süresi": ("reaction_time", +1, "reaction time", False),
    "Ruh hali": ("mood", -1, "mood (self-report)", True),
    "Uyku kalitesi": ("sleep_quality", -1, "sleep quality (self-report)", True),
    "Kan oksijen satürasyonu (SpO2)": ("spo2", -1, "blood oxygen (SpO2)", False),
    "Vücut sıcaklığı": ("body_temp", +1, "body temperature", False),
    "Kan basıncı": ("blood_pressure", +1, "blood pressure (systolic)", False),
    "Vücut kütlesi": ("body_mass", -1, "body mass", False),
}
KEYS = [v[0] for v in INDICATORS.values()]
SIGN = {v[0]: v[1] for v in INDICATORS.values()}
EN_NAME = {v[0]: v[2] for v in INDICATORS.values()}
SELF_REPORT = {v[0] for v in INDICATORS.values() if v[3]}
TR_NAME = {v[0]: k for k, v in INDICATORS.items()}
CROSS = ["sleep_duration", "stress", "hrv", "resting_hr", "exercise", "sleep_quality", "body_temp"]
_TREND = re.compile(r"(rising|falling|stable) for the last (\d+) day")


# --------------------------------------------------------------------------- veri okuma
def load_payloads(path: str | Path, scenario: str = "") -> pd.DataFrame:
    """jsonl payload dosyası -> uzun tablo: scen, aid, day, key, value, unit, z, durum, trend_days."""
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            for g in r["gostergeler"]:
                if g["ad"] not in INDICATORS:
                    continue
                v = g["deger"]
                if isinstance(v, str) and "/" in v:          # "128/82" -> sistolik
                    v = v.split("/")[0]
                try:
                    v = float(v)
                except (TypeError, ValueError):
                    v = np.nan
                m = _TREND.search(g.get("trend") or "")
                td = 0 if not m else (int(m.group(2)) * {"rising": 1, "falling": -1, "stable": 0}[m.group(1)])
                rows.append((scenario, r["astronot_id"], int(r["gorev_gunu"]), INDICATORS[g["ad"]][0], v, g["birim"],
                             g["z_skor"], g["durum"], td))
    return pd.DataFrame(rows, columns=["scen", "aid", "day", "key", "value", "unit", "z", "durum", "trend_days"])


def series_tables(long: pd.DataFrame) -> dict[tuple[str, str], dict]:
    """(senaryo, astronot) -> {"z": gün x gösterge, "value": ..., "trend": ..., "unit": {...}}"""
    out = {}
    for (scen, aid), g in long.groupby(["scen", "aid"]):
        days = pd.RangeIndex(g.day.min(), g.day.max() + 1, name="day")

        def piv(col: str) -> pd.DataFrame:
            p = g.pivot_table(index="day", columns="key", values=col, aggfunc="first")
            return p.reindex(days).reindex(columns=KEYS).astype(float)

        units = g.groupby("key").unit.first().to_dict()
        z_engine = piv("z")
        lev = g.assign(level=g["durum"].map(LEVEL)).pivot_table(index="day", columns="key", values="level", aggfunc="first")
        lev = lev.reindex(days).reindex(columns=KEYS).astype(float)
        lev = lev.where(z_engine.notna())          # z yokken (baseline dönemi) durum bilgisi kullanılmaz
        # "z": modelin kullandığı z. Gerçek veride motorun kendi z'si; veri artırmada augment.py üzerine olay etkisini ekler.
        # "level": motorun kendi durum etiketi (0 yeşil, 1 sarı, 2 kırmızı); veri artırılmış kopyalarda None.
        out[(scen, aid)] = {"z_engine": z_engine, "z": z_engine.copy(), "value": piv("value"), "unit": units,
                            "level": lev}
    return out


# --------------------------------------------------------------------------- özellikler
FEATURES = (["sign", "self_report"] + [f"bz_lag{i}" for i in range(WINDOW)] + [f"bu_lag{i}" for i in range(WINDOW)]
            + ["bu_slope", "bu_std", "bz_slope", "n_missing"]
            + [f"x_{c}_bz" for c in CROSS] + [f"x_{c}_slope" for c in CROSS] + ["ind_id"])


def _slope(y: np.ndarray) -> float:
    ok = ~np.isnan(y)
    if ok.sum() < 3:
        return np.nan
    x = np.arange(len(y))[ok]
    return float(np.polyfit(x, y[ok], 1)[0])


def baseline_stats(tab: dict) -> dict[str, tuple[float, float]]:
    """Kişisel baseline (ortalama, std): göstergenin z'si başlamadan önceki günler (payload kuralı)."""
    out = {}
    for k in KEYS:
        z, v = tab["z_engine"][k], tab["value"][k]
        first = z.first_valid_index()
        if first is None:
            continue
        b = v.loc[: first - 1].dropna()
        if len(b) >= 5 and b.std(ddof=1) > 0:
            out[k] = (float(b.mean()), float(b.std(ddof=1)))
    return out


def window_features(tab: dict, base: dict, t: int) -> pd.DataFrame:
    """Gün t'de (t dahil son 7 gün) her gösterge için bir özellik satırı. Kötüleşme yönüne çevrilmiş ("bad" z)."""
    z, v = tab["z"], tab["value"]
    if t - WINDOW + 1 < z.index.min() or t > z.index.max():
        return pd.DataFrame(columns=FEATURES + ["key", "day"])
    win = slice(t - WINDOW + 1, t)
    cross = {}
    for c in CROSS:
        bz = z.loc[win, c].to_numpy(dtype=float) * SIGN[c]
        cross[f"x_{c}_bz"] = bz[-1]
        cross[f"x_{c}_slope"] = _slope(bz)
    rows = []
    for i, k in enumerate(KEYS):
        if k not in base or np.isnan(z.at[t, k]):
            continue
        m, s = base[k]
        s_ = SIGN[k]
        bz = z.loc[win, k].to_numpy(dtype=float) * s_
        bu = (v.loc[win, k].to_numpy(dtype=float) - m) / s * s_
        row = {"sign": s_, "self_report": int(k in SELF_REPORT), "ind_id": i,
               "bu_slope": _slope(bu), "bu_std": float(np.nanstd(bu)), "bz_slope": _slope(bz),
               "n_missing": int(np.isnan(bu).sum()), "key": k, "day": t}
        for j in range(WINDOW):  # lag0 = bugün
            row[f"bz_lag{j}"] = bz[-1 - j]
            row[f"bu_lag{j}"] = bu[-1 - j]
        row.update(cross)
        rows.append(row)
    return pd.DataFrame(rows)


def build_rows(tables: dict, days_by_series: dict | None = None, with_target: bool = True) -> pd.DataFrame:
    """Tüm (senaryo, astronot, gün, gösterge) satırları + hedef: gün t+7'deki kötü-yönlü z (gelecek haftanın ortalaması)."""
    parts = []
    for key, tab in tables.items():
        base = baseline_stats(tab)
        z = tab["z"]
        days = days_by_series.get(key, range(0)) if days_by_series is not None else z.index
        for t in days:
            f = window_features(tab, base, t)
            if f.empty:
                continue
            if with_target:
                if t + HORIZON > z.index.max():
                    continue
                f["target"] = [z.at[t + HORIZON, k] * SIGN[k] for k in f["key"]]
                f = f[f["target"].notna()].copy()
                f["target_level"] = [level_at(tab, t + HORIZON, k) for k in f["key"]]
            f["now_level"] = [level_at(tab, t, k) for k in f["key"]]
            f["scen"], f["aid"] = key
            parts.append(f)
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def level_from_bad_z(bz: float) -> int:
    return 2 if bz >= KIRMIZI_Z else (1 if bz >= SARI_Z else 0)


def level_at(tab: dict, day: int, k: str) -> int:
    """Motorun durum etiketi varsa onu, yoksa (veri artırılmış kopya) z eşiğini kullan."""
    lev = tab.get("level")
    if lev is not None and day in lev.index and not np.isnan(lev.at[day, k]):
        return int(lev.at[day, k])
    return level_from_bad_z(float(tab["z"].at[day, k]) * SIGN[k])


def status_from_bad_z(bz: float) -> str:
    if bz is None or np.isnan(bz):
        return "UNKNOWN"
    return "RED" if bz >= KIRMIZI_Z else ("YELLOW" if bz >= SARI_Z else "GREEN")


# --------------------------------------------------------------------------- tahmin -> LLM JSON
_ORDER = {"GREEN": 0, "YELLOW": 1, "RED": 2, "UNKNOWN": -1}


def forecast_json(model: dict, tab: dict, aid: str, t: int, audience: str = "astronaut") -> dict:
    """Bir astronotun gün t itibarıyla gelecek hafta tahmini (LLM'e verilecek JSON).

    audience="ground" ise öz bildirim göstergeleri (stres, ruh hali, uyku kalitesi) çıkarılır.
    """
    base = baseline_stats(tab)
    f = window_features(tab, base, t)
    out = {
        "type": "health_forecast",
        "astronaut_id": aid,
        "as_of_mission_day": int(t),
        "horizon_days": HORIZON,
        "input_window_days": WINDOW,
        "method": "gradient-boosted forecast of next week's 7-day mean, on the rule engine's personal z-score scale",
        "model_version": model["version"],
        "disclaimer": "Projection from a model trained on synthetic mission data. Decision support, not a diagnosis.",
        "validation_mae_z": model["val_mae_z"],
        "risk_levels": {"likely": "central forecast reaches the yellow/red rule threshold next week",
                        "possible": "only the worst-case end of the 80% forecast band reaches the yellow/red threshold",
                        "low": "forecast stays inside the personal normal"},
        "forecasts": [],
    }
    if f.empty:
        out["status"] = "insufficient_data"
        return out
    X = f[FEATURES].astype(float)
    p50, lo, hi = (model[q].predict(X) for q in ("p50", "p10", "p90"))
    vals = tab["value"]
    items = []
    for i, k in enumerate(f["key"]):
        if audience == "ground" and k in SELF_REPORT:
            continue
        m, s = base[k]
        sg = SIGN[k]
        now_bz = float(f["bz_lag0"].iloc[i])
        cur7 = float(np.nanmean(vals.loc[t - WINDOW + 1: t, k]))

        def to_value(bz: float) -> float:
            # Son 7 günün ortalamasına göre çapalanır: z'deki değişim kadar (kişisel std ile) birim değişimi.
            # Böylece birimdeki yön her zaman z'deki yönle aynıdır.
            return cur7 + sg * (bz - now_bz) * s

        worst_bz = max(float(hi[i]), float(lo[i]))
        a, b = sorted((to_value(float(lo[i])), to_value(float(hi[i]))))
        now_status = LEVEL_NAME[level_at(tab, t, k)]
        next_status = status_from_bad_z(float(p50[i]))
        upper_status = status_from_bad_z(worst_bz)
        risk = "likely" if next_status != "GREEN" else ("possible" if upper_status != "GREEN" else "low")
        items.append({
            "indicator": EN_NAME[k],
            "indicator_tr": TR_NAME[k],
            "unit": tab["unit"].get(k),
            "personal_baseline": round(m, 2),
            "last_7_day_mean": round(cur7, 2),
            "forecast_next_7_day_mean": round(to_value(float(p50[i])), 2),
            "forecast_range_80pct": [round(a, 2), round(b, 2)],
            "worse_when": "higher" if sg > 0 else "lower",
            "worst_case_value": round(to_value(worst_bz), 2),
            "z_now": round(now_bz * sg, 2),
            "z_forecast": round(float(p50[i]) * sg, 2),
            "status_now": now_status,
            "status_forecast": next_status,
            "worst_case_status": upper_status,
            "risk_next_week": risk,
            "self_report": k in SELF_REPORT,
        })
    rank = {"likely": 2, "possible": 1, "low": 0}
    items.sort(key=lambda d: (-rank[d["risk_next_week"]], -_ORDER.get(d["status_now"], 0), -abs(d["z_forecast"])))
    out["forecasts"] = items
    out["watch_list"] = [d["indicator"] for d in items if d["risk_next_week"] != "low" or d["status_now"] != "GREEN"]
    out["status"] = "ok"
    return out
