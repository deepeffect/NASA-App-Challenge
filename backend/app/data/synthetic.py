"""Sentetik veri üreticisi (NASA verisi gelene kadar).

- 4 astronot × 180 gün; günlük metrikler + saatlik nabız ve SpO2; gerçekçi gürültü ve %2 eksik veri.
- Kişisel profiller (baseline'lar) astronota göre farklıdır.
- Seed ile tekrarlanabilir.

DEMO SENARYOSU (AST-02, görev günü S=150'den itibaren):
  S+0  uyku süresi ve uyku kalitesi düşer
  S+2  reaksiyon süresi uzar
  S+3  stres öz bildirimi artar, ruh hali düşer, HRV düşer
  S+6  istirahat nabzı (ve saatlik nabız) yükselir
  S+7  sistolik kan basıncı hafif yükselir
  S+10 egzersiz süresi azalır (hafif)
Diğer astronotlar normal kalır.

SPE (opsiyonel, --spe-day): tüm mürettebatta 3 gün süren güneş parçacık olayı doz artışı.

Not: Değerler gerçekçi görünmesi için seçilmiş sentetik değerlerdir, klinik referans DEĞİLDİR.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

import numpy as np
import pandas as pd

ASTRONAUTS: list[tuple[str, str, str]] = [
    ("AST-01", "Astronot 1", "Komutan"),
    ("AST-02", "Astronot 2", "Uçuş mühendisi"),
    ("AST-03", "Astronot 3", "Mürettebat sağlık sorumlusu (CMO)"),
    ("AST-04", "Astronot 4", "Görev uzmanı"),
]

NORMAL_NOTES = [
    "Verimli bir gündü.",
    "Deney planına uyduk.",
    "Biraz yorgunum ama iyiyim.",
    "Egzersiz iyi geçti.",
    "Aileyle mesajlaştım, moralim iyi.",
    "Gürültü yüzünden uykum biraz bölündü.",
]
SCENARIO_NOTES = [
    "Uyuyamıyorum, kafam çok dolu.",
    "Gece birkaç kez uyandım.",
    "İş yükü çok arttı, yetişemiyorum.",
    "Kendimi gergin hissediyorum.",
    "Odaklanmakta zorlanıyorum.",
]

# metrik → (ölçüm saati, birim, kaynak)
_DAILY_META: dict[str, tuple[time, str, str]] = {
    "sleep_duration": (time(7, 0), "h", "synthetic:wearable"),
    "resting_hr": (time(7, 5), "bpm", "synthetic:wearable"),
    "hrv_rmssd": (time(7, 5), "ms", "synthetic:wearable"),
    "bp_systolic": (time(7, 30), "mmHg", "synthetic:medical"),
    "bp_diastolic": (time(7, 30), "mmHg", "synthetic:medical"),
    "body_temp": (time(7, 30), "degC", "synthetic:medical"),
    "body_mass": (time(7, 45), "kg", "synthetic:medical"),
    "reaction_time": (time(8, 0), "ms", "synthetic:pvt"),
    "exercise_minutes": (time(20, 0), "min", "synthetic:wearable"),
    "mood": (time(21, 0), "score_1_5", "synthetic:checkin"),
    "stress": (time(21, 0), "score_1_5", "synthetic:checkin"),
    "sleep_quality": (time(21, 0), "score_1_5", "synthetic:checkin"),
    "radiation_daily_dose": (time(23, 55), "mSv", "synthetic:dosimeter"),
    "radiation_cumulative": (time(23, 55), "mSv", "synthetic:dosimeter"),
}
_NO_MISSING = {"radiation_daily_dose", "radiation_cumulative", "mood", "stress", "sleep_quality"}
_DECIMALS = {"resting_hr": 0, "hrv_rmssd": 0, "bp_systolic": 0, "bp_diastolic": 0, "body_temp": 2, "body_mass": 2,
             "reaction_time": 0, "exercise_minutes": 0, "sleep_duration": 2, "radiation_daily_dose": 3,
             "radiation_cumulative": 2}


@dataclass
class SyntheticConfig:
    seed: int = 42
    days: int = 180
    start: date = date(2026, 5, 19)
    n_astronauts: int = 4
    scenario_astronaut: str | None = "AST-02"
    scenario_day: int = 150
    spe_day: int | None = None
    missing_rate: float = 0.02
    # Derin uzay transfer profili: GCR ~1.8 mSv/gün (Curiosity RAD ölçümü). TODO: görev profiliyle doğrula
    gcr_msv_per_day: float = 1.8


@dataclass
class SyntheticData:
    astronauts: list[dict]
    measurements: pd.DataFrame  # astronaut_id, timestamp, metric, value, unit, source
    checkins: list[dict]


def _ramp(d: np.ndarray, start: int, ramp_days: int) -> np.ndarray:
    """start gününden itibaren ramp_days içinde 0→1 doğrusal artış."""
    return np.clip((d - start + 1) / ramp_days, 0.0, 1.0)


def generate(cfg: SyntheticConfig | None = None) -> SyntheticData:
    cfg = cfg or SyntheticConfig()
    rng = np.random.default_rng(cfg.seed)
    days = np.arange(1, cfg.days + 1)
    n = len(days)
    dates = [cfg.start + timedelta(days=int(d) - 1) for d in days]
    S = cfg.scenario_day

    frames: list[pd.DataFrame] = []
    checkins: list[dict] = []
    astronauts: list[dict] = []

    for i in range(cfg.n_astronauts):
        aid, name, role = ASTRONAUTS[i] if i < len(ASTRONAUTS) else (f"AST-{i + 1:02d}", f"Astronot {i + 1}", "Görev uzmanı")
        astronauts.append({"id": aid, "name": name, "role": role})
        sc = aid == cfg.scenario_astronaut

        def eff(delta: float, offset: int, ramp_days: int) -> np.ndarray:
            return delta * _ramp(days, S + offset, ramp_days) if sc else np.zeros(n)

        def noise(sd: float) -> np.ndarray:
            return rng.normal(0.0, sd, n)

        # --- kişisel profil
        p = {
            "rhr": rng.uniform(56, 64), "hrv": rng.uniform(48, 68), "sbp": rng.uniform(110, 122),
            "dbp": rng.uniform(70, 78), "temp": rng.uniform(36.7, 37.0), "mass": rng.uniform(62, 86),
            "ex": rng.uniform(120, 140), "sleep": rng.uniform(7.15, 7.5), "rt": rng.uniform(250, 290),
            "shield": rng.uniform(0.95, 1.05), "prior_dose": rng.uniform(0, 40),
        }

        rhr_true = p["rhr"] + eff(11, 6, 6)
        values: dict[str, np.ndarray] = {
            "sleep_duration": np.clip(p["sleep"] + noise(0.33) + eff(-2.2, 0, 5), 2.5, 11),
            "resting_hr": rhr_true + noise(1.8),
            "hrv_rmssd": np.clip(p["hrv"] + noise(4.5) + eff(-16, 3, 7), 8, 150),
            "bp_systolic": p["sbp"] + noise(4.0) + eff(6, 7, 6),
            "bp_diastolic": p["dbp"] + noise(3.0),
            "body_temp": p["temp"] + noise(0.12),
            "body_mass": p["mass"] + noise(0.25),
            "reaction_time": p["rt"] + noise(10) + eff(45, 2, 6),
            "exercise_minutes": np.clip(p["ex"] + noise(12) + eff(-20, 10, 6), 0, 300),
            "mood": np.clip(np.rint(3.9 + noise(0.55) + eff(-1.6, 3, 5)), 1, 5),
            "stress": np.clip(np.rint(2.0 + noise(0.55) + eff(2.0, 3, 5)), 1, 5),
            "sleep_quality": np.clip(np.rint(3.9 + noise(0.55) + eff(-1.7, 0, 5)), 1, 5),
        }

        daily_dose = p["shield"] * cfg.gcr_msv_per_day + noise(0.06)
        if cfg.spe_day:
            for k, extra in enumerate((25.0, 40.0, 15.0)):
                j = cfg.spe_day - 1 + k
                if 0 <= j < n:
                    daily_dose[j] += extra * p["shield"]
        values["radiation_daily_dose"] = np.clip(daily_dose, 0, None)
        values["radiation_cumulative"] = p["prior_dose"] + np.cumsum(values["radiation_daily_dose"])

        checkin_day = rng.random(n) >= 0.03  # %3 gün check-in atlanır
        for metric, arr in values.items():
            t, unit, source = _DAILY_META[metric]
            mask = np.ones(n, dtype=bool)
            if metric in {"mood", "stress", "sleep_quality"}:
                mask &= checkin_day
            elif metric not in _NO_MISSING:
                mask &= rng.random(n) >= cfg.missing_rate
            ts = [datetime.combine(dates[j], t) for j in range(n) if mask[j]]
            v = arr[mask]
            if metric in _DECIMALS:
                v = np.round(v, _DECIMALS[metric])
            frames.append(pd.DataFrame({
                "astronaut_id": aid, "timestamp": ts, "metric": metric, "value": v.astype(float),
                "unit": unit, "source": source,
            }))

        # --- saatlik nabız ve SpO2
        hours = np.arange(24)
        circadian = 6 * np.sin(2 * np.pi * (hours - 15) / 24)
        night = np.isin(hours, [23, 0, 1, 2, 3, 4, 5, 6]) * -8.0
        exercise = np.where(hours == 9, 35.0, 0.0) + np.where(hours == 17, 25.0, 0.0)
        hr = rhr_true[:, None] + 10 + circadian + night + exercise + rng.normal(0, 4, (n, 24))
        spo2 = np.clip(97.6 + rng.normal(0, 0.5, (n, 24)), 85, 100)
        for metric, mat, decimals in (("heart_rate", hr, 0), ("spo2", spo2, 1)):
            keep = rng.random((n, 24)) >= cfg.missing_rate
            jj, hh = np.nonzero(keep)
            ts = [datetime.combine(dates[j], time(int(h))) for j, h in zip(jj, hh, strict=True)]
            frames.append(pd.DataFrame({
                "astronaut_id": aid, "timestamp": ts, "metric": metric,
                "value": np.round(mat[jj, hh], decimals).astype(float),
                "unit": "bpm" if metric == "heart_rate" else "%", "source": "synthetic:wearable",
            }))

        # --- check-in kayıtları (öz bildirim formu)
        for j in range(n):
            if not checkin_day[j]:
                continue
            in_scenario = sc and days[j] >= S + 1
            note = None
            if in_scenario and rng.random() < 0.6:
                note = str(rng.choice(SCENARIO_NOTES))
            elif rng.random() < 0.25:
                picked = str(rng.choice(NORMAL_NOTES))  # çekim sayısı sabit kalsın (seed tekrarlanabilirliği)
                note = None if in_scenario else picked
            checkins.append({
                "astronaut_id": aid,
                "timestamp": datetime.combine(dates[j], time(21, 0)),
                "mood": int(values["mood"][j]),
                "stress": int(values["stress"][j]),
                "sleep_quality": int(values["sleep_quality"][j]),
                "note": note,
                "share_with_ground": bool(rng.random() < 0.2),
                "emergency": False,
            })

    df = pd.concat(frames, ignore_index=True)
    df = df.sort_values(["astronaut_id", "metric", "timestamp"], ignore_index=True)
    return SyntheticData(astronauts=astronauts, measurements=df, checkins=checkins)
