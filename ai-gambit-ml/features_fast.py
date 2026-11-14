"""
features_fast.py  --  forecast_core.build_rows ile AYNI özellikleri vektörel (hızlı) hesaplar.

Neden: hastalikli_v1 veri seti 640 koşu (2,2 GB). build_rows gün gün döngüyle çalışır, bu boyutta saatler sürer.
Tahmin (predict.py / forecast_json) hâlâ forecast_core.window_features kullanır; bu dosya sadece eğitim ve ölçüm içindir.
Eşitlik kontrolü: python features_fast.py --check <payloads_tr_*.jsonl>
"""
from __future__ import annotations

import argparse
import warnings

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view

from forecast_core import CROSS, FEATURES, HORIZON, KEYS, SELF_REPORT, SIGN, WINDOW, baseline_stats

_SIGNS = np.array([SIGN[k] for k in KEYS], dtype=float)
_X = np.arange(WINDOW, dtype=float)


def _win_slope(w: np.ndarray) -> np.ndarray:
    """Son eksende 7 günlük pencere; NaN'ları atlayan en küçük kareler eğimi (np.polyfit ile aynı). <3 nokta -> NaN."""
    ok = ~np.isnan(w)
    n = ok.sum(-1).astype(float)
    y = np.where(ok, w, 0.0)
    x = np.where(ok, _X, 0.0)
    sx, sy = x.sum(-1), y.sum(-1)
    sxx, sxy = (x * x).sum(-1), (x * y).sum(-1)
    den = n * sxx - sx * sx
    with np.errstate(invalid="ignore", divide="ignore"):
        s = (n * sxy - sx * sy) / den
    return np.where(n >= 3, s, np.nan)


def _levels(tab: dict, bad_z: np.ndarray) -> np.ndarray:
    """forecast_core.level_at ile aynı: motorun durumu varsa o, yoksa z eşiği."""
    with np.errstate(invalid="ignore"):
        fb = np.where(bad_z >= 3.0, 2, np.where(bad_z >= 2.0, 1, 0)).astype(float)
    lev = tab.get("level")
    if lev is None:
        return fb
    L = lev.to_numpy(dtype=float)
    return np.where(np.isnan(L), fb, L)


def series_rows(tab: dict, days=None, with_target: bool = True) -> pd.DataFrame:
    """Bir (koşu, astronot) serisi için build_rows çıktısının aynısı (scen/aid sütunları hariç), float32."""
    base = baseline_stats(tab)
    Zdf, Vdf = tab["z"], tab["value"]
    idx = Zdf.index.to_numpy()
    d0, D = int(idx[0]), len(idx)
    if D < WINDOW:
        return pd.DataFrame()
    BZ = Zdf.to_numpy(dtype=float) * _SIGNS                   # kötü yönlü z
    lev_all = _levels(tab, BZ)
    M = np.array([base[k][0] if k in base else np.nan for k in KEYS])
    S = np.array([base[k][1] if k in base else np.nan for k in KEYS])
    BU = (Vdf.to_numpy(dtype=float) - M) / S * _SIGNS

    wz = sliding_window_view(BZ, WINDOW, axis=0)               # (D-6, 12, 7), son eksen eski -> yeni
    wu = sliding_window_view(BU, WINDOW, axis=0)
    t_days = idx[WINDOW - 1:]                                  # pencerenin son günü = t
    sel = np.ones(len(t_days), bool)
    if days is not None:
        sel &= np.isin(t_days, np.asarray(list(days)))
    if with_target:
        sel &= t_days + HORIZON <= idx[-1]
    if not sel.any():
        return pd.DataFrame()
    wz, wu, t_days = wz[sel], wu[sel], t_days[sel]
    pos = t_days - d0                                          # t'nin satır numarası

    bz_slope, bu_slope = _win_slope(wz), _win_slope(wu)       # (n, 12)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        bu_std = np.nanstd(wu, axis=-1)
    n_missing = np.isnan(wu).sum(-1)
    ci = [KEYS.index(c) for c in CROSS]

    parts = []
    for i, k in enumerate(KEYS):
        if k not in base:
            continue
        keep = ~np.isnan(wz[:, i, -1])
        if with_target:
            tgt = BZ[pos + HORIZON, i]
            keep &= ~np.isnan(tgt)
        if not keep.any():
            continue
        n = int(keep.sum())
        cols = {"sign": np.full(n, SIGN[k], float), "self_report": np.full(n, float(k in SELF_REPORT))}
        for j in range(WINDOW):
            cols[f"bz_lag{j}"] = wz[keep, i, -1 - j]
        for j in range(WINDOW):
            cols[f"bu_lag{j}"] = wu[keep, i, -1 - j]
        cols["bu_slope"], cols["bu_std"] = bu_slope[keep, i], bu_std[keep, i]
        cols["bz_slope"], cols["n_missing"] = bz_slope[keep, i], n_missing[keep, i].astype(float)
        for c, cj in zip(CROSS, ci):
            cols[f"x_{c}_bz"] = wz[keep, cj, -1]
        for c, cj in zip(CROSS, ci):
            cols[f"x_{c}_slope"] = bz_slope[keep, cj]
        cols["ind_id"] = np.full(n, float(i))
        df = pd.DataFrame(cols)[FEATURES].astype(np.float32)
        df["key"] = k
        df["day"] = t_days[keep].astype(np.int32)
        if with_target:
            df["target"] = tgt[keep].astype(np.float32)
            df["target_level"] = lev_all[pos[keep] + HORIZON, i].astype(np.int8)
        df["now_level"] = lev_all[pos[keep], i].astype(np.int8)
        parts.append(df)
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def _check(path: str) -> None:
    from forecast_core import build_rows, load_payloads, series_tables
    tables = series_tables(load_payloads(path, "x"))
    worst = 0.0
    for key, tab in list(tables.items())[:2]:
        slow = build_rows({key: tab}).sort_values(["day", "key"]).reset_index(drop=True)
        fast = series_rows(tab).sort_values(["day", "key"]).reset_index(drop=True)
        assert len(slow) == len(fast), (key, len(slow), len(fast))
        assert (slow["key"].to_numpy() == fast["key"].to_numpy()).all()
        assert (slow["day"].to_numpy() == fast["day"].to_numpy()).all()
        for c in FEATURES + ["target"]:
            a, b = slow[c].to_numpy(float), fast[c].to_numpy(float)
            assert (np.isnan(a) == np.isnan(b)).all(), (key, c, "NaN farkı")
            if (~np.isnan(a)).any():
                worst = max(worst, float(np.nanmax(np.abs(a - b) / np.maximum(1.0, np.abs(a)))))
        for c in ("target_level", "now_level"):
            assert (slow[c].to_numpy(int) == fast[c].to_numpy(int)).all(), (key, c)
        print(f"{key}: {len(fast)} satır, bütün sütunlar aynı")
    print(f"en büyük göreli fark (float32 yuvarlaması): {worst:.2e}")
    assert worst < 1e-5


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", required=True)
    _check(ap.parse_args().check)
