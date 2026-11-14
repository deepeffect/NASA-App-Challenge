"""
augment.py  --  Sakin serilere rastgele kötüleşme olayları ekleyerek eğitim verisini artırır.

Neden: payload verisinde "şu an yeşil, gelecek hafta sarı/kırmızı" örneği çok az (29.633 satırda 13).
Model böyle bir geçişi hiç görmezse "böyle giderse..." diyemez.

Nasıl:
  1. Bir serinin kopyası alınır (ör. Mars'ta AST-02, gün 1-600).
  2. Rastgele bir gösterge seçilir (uyku, stres, nabız, ateş, egzersiz...). Kişisel std cinsinden rastgele
     büyüklükte (0.8-4.5 std), rastgele hızda (1-14 gün rampa), rastgele süreyle kötüleşme eklenir.
  3. Olasılıkla zincirleme etkiler eklenir (ör. uyku -> birkaç gün sonra stres/HRV/nabız). Gecikme ve
     büyüklükler rastgeledir; takımın AST-02 senaryosunun parametreleri KOPYALANMAZ.
  4. Bazı olaylar iyileşme yönündedir, bazı kopyalarda hiç olay yoktur (yanlış alarmı öğrenmesin diye).
  5. Değer değişimi Δ ise, motorun z'si z + (Δ'nın 7 günlük ortalaması)/kişisel_std olarak güncellenir.

UYARI: Model, buradaki varsayımsal bağlantıları da öğrenir. Bu yüzden test, hiç artırılmamış ISS görevinde
(takımın AST-02 zinciri) ve kontrol ikizinde yapılır.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from forecast_core import KEYS, SELF_REPORT, SIGN, baseline_stats

# birincil gösterge -> [(ikincil gösterge, gecikme aralığı (gün), büyüklük oranı aralığı)]
COUPLING: dict[str, list[tuple[str, tuple[int, int], tuple[float, float]]]] = {
    "sleep_duration": [("sleep_quality", (0, 2), (0.4, 1.0)), ("stress", (1, 7), (0.3, 1.0)), ("mood", (1, 7), (0.3, 0.9)),
                       ("hrv", (1, 7), (0.2, 0.9)), ("resting_hr", (2, 10), (0.3, 1.0)), ("reaction_time", (0, 5), (0.3, 0.9))],
    "stress": [("sleep_duration", (1, 6), (0.2, 0.8)), ("mood", (0, 3), (0.4, 1.0)), ("hrv", (1, 6), (0.3, 0.9)),
               ("resting_hr", (2, 9), (0.3, 0.9))],
    "body_temp": [("resting_hr", (0, 2), (0.5, 1.1)), ("hrv", (0, 2), (0.4, 1.0)), ("sleep_quality", (0, 3), (0.3, 0.9)),
                  ("exercise", (0, 2), (0.5, 1.2))],
    "exercise": [("body_mass", (4, 14), (0.3, 0.8)), ("mood", (2, 8), (0.2, 0.6))],
    "resting_hr": [("hrv", (0, 3), (0.3, 0.9))],
    "hrv": [("resting_hr", (0, 4), (0.2, 0.7))],
    "mood": [("stress", (0, 3), (0.3, 0.9)), ("sleep_quality", (1, 5), (0.2, 0.7))],
    "sleep_quality": [("mood", (1, 5), (0.2, 0.7))],
    "reaction_time": [], "spo2": [("resting_hr", (0, 2), (0.3, 0.8))], "blood_pressure": [], "body_mass": [],
}
PRIMARY_WEIGHTS = {"sleep_duration": 3, "stress": 2, "body_temp": 2, "exercise": 2, "resting_hr": 1.5, "hrv": 1.5,
                   "mood": 1.5, "sleep_quality": 1, "reaction_time": 1, "spo2": 0.7, "blood_pressure": 1, "body_mass": 0.7}
CLIP = {"sleep_duration": (2.0, 11.0), "exercise": (0.0, 300.0), "spo2": (85.0, 100.0)}


def _shape(n_days: int, onset: int, ramp: int, plateau: int, decay: int) -> np.ndarray:
    """0 -> 1 rampa, plato, sonra 0'a dönüş; dizi indeksi = gün - ilk gün."""
    d = np.arange(n_days)
    up = np.clip((d - onset + 1) / max(ramp, 1), 0, 1)
    end = onset + ramp + plateau
    down = np.clip(1 - (d - end) / max(decay, 1), 0, 1)
    return np.where(d < end, up, down)


def inject(tab: dict, rng: np.random.Generator, day_range: tuple[int, int], n_episodes: int) -> tuple[dict, list[dict]]:
    """tab'ın kopyasına olay ekler. Dönüş: (yeni tab, olay listesi)."""
    value = tab["value"].copy()
    z = tab["z"].copy()
    base = baseline_stats(tab)
    days = value.index
    n = len(days)
    delta = pd.DataFrame(0.0, index=days, columns=KEYS)   # birim cinsinden değişim (işaretli)
    cands = [k for k in KEYS if k in base and z[k].notna().any()]
    w = np.array([PRIMARY_WEIGHTS[k] for k in cands], dtype=float)
    episodes = []
    lo, hi = day_range
    for _ in range(n_episodes):
        k = str(rng.choice(cands, p=w / w.sum()))
        first_z = int(z[k].first_valid_index())
        o_lo = max(lo, first_z + 7)
        if o_lo >= hi:
            continue
        onset_day = int(rng.integers(o_lo, hi))
        onset = onset_day - int(days[0])
        recovery = rng.random() < 0.15                  # %15: iyileşme yönünde olay
        mag = float(rng.uniform(0.8, 4.5)) * (-0.6 if recovery else 1.0)
        ramp, plateau, decay = int(rng.integers(1, 15)), int(rng.integers(5, 40)), int(rng.integers(3, 15))
        targets = [(k, 0, 1.0)]
        if rng.random() < 0.6 and COUPLING[k]:
            for k2, (d0, d1), (f0, f1) in COUPLING[k]:
                if rng.random() < 0.6 and k2 in base:
                    targets.append((k2, int(rng.integers(d0, d1 + 1)), float(rng.uniform(f0, f1))))
        for kk, lag, frac in targets:
            m, s = base[kk]
            delta[kk] += SIGN[kk] * mag * frac * s * _shape(n, onset + lag, ramp, plateau, decay)
        episodes.append({"indicator": k, "onset_day": onset_day, "magnitude_sd": round(mag, 2), "ramp": ramp,
                         "plateau": plateau, "secondary": [t[0] for t in targets[1:]]})
    new_val = value + delta
    for k in KEYS:
        if k in SELF_REPORT:
            new_val[k] = new_val[k].round().clip(1, 5)
        elif k in CLIP:
            new_val[k] = new_val[k].clip(*CLIP[k])
    real_delta = (new_val - value).fillna(0.0)
    for k in KEYS:
        if k in base:
            z[k] = z[k] + real_delta[k].rolling(7, min_periods=1).mean() / base[k][1]
    out = dict(tab)
    out.update({"value": new_val, "z": z, "level": None})   # motor etiketi artık geçersiz; z eşiği kullanılır
    return out, episodes


def augment_tables(tables: dict, plan: dict[tuple[str, str], dict], seed: int) -> tuple[dict, dict, list[dict]]:
    """plan: (senaryo, astronot) -> {"days": (ilk, son), "copies": int, "episodes": int, "null_frac": float}

    Dönüş: (yeni tablolar, her tablo için kullanılacak günler, olay kaydı).
    Olay çevresindeki tüm günler + sakin günlerin %15'i örneklenir (veri boyutunu makul tutmak için)."""
    rng = np.random.default_rng(seed)
    new_tables, days_by, log = {}, {}, []
    for (scen, aid), p in plan.items():
        tab = tables[(scen, aid)]
        lo, hi = p["days"]
        for c in range(p["copies"]):
            n_ep = 0 if rng.random() < p.get("null_frac", 0.1) else p["episodes"]
            aug, eps = inject(tab, rng, (lo, hi - 21), n_ep)
            key = (f"{scen}_aug{c:02d}", aid)
            new_tables[key] = aug
            keep = set()
            for e in eps:
                keep.update(range(e["onset_day"] - 14, e["onset_day"] + 60))
            calm = [d for d in range(lo, hi + 1) if d not in keep and rng.random() < 0.15]
            days_by[key] = sorted(d for d in keep.union(calm) if lo <= d <= hi)
            log += [dict(e, series=f"{key[0]}/{aid}") for e in eps]
    return new_tables, days_by, log
