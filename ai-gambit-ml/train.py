"""
train.py  --  Gelecek hafta tahmin modelini train / validation / test ayrımıyla eğitir ve ölçer.

Çalıştırma:
    python train.py --data <payload klasörü>

Bölme (zamana göre, sızıntı olmasın diye boşluklu):
    TRAIN : Mars 860 (hedef günü <= 600) + üç ortam 84 (tamamı) + ISS görevi (hedef günü <= 125)
            + bu aralıkların veri artırılmış kopyaları (augment.py, seed 1)
    VAL   : Mars 860 (tahmin günü >= 615)  + ISS görevi (tahmin günü 126-133; CO2 olayı burada)
            + Mars 615-860 aralığının veri artırılmış kopyaları (augment.py, seed 2; farklı olaylar)
    TEST  : ISS görevi tahmin günü 140-173 (AST-02 uyku zinciri) + ISS kontrol ikizi aynı günler (yanlış alarm)
Hiperparametreler sadece VAL ile seçilir; TEST en sonda bir kez ölçülür.

Çıktılar: models/forecast_v1.joblib, reports/metrics.json, reports/val_test_predictions.csv
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

from augment import augment_tables
from forecast_core import (FEATURES, HORIZON, KEYS, SARI_Z, SIGN, WINDOW, build_rows, load_payloads,
                           series_tables)

ROOT = Path(__file__).resolve().parent
SCEN_FILES = {
    "iss": "payloads_tr_mission_iss180.jsonl",
    "control": "payloads_tr_control_iss180.jsonl",
    "mars": "payloads_tr_mission_mars860.jsonl",
    "env84": "payloads_tr_mission_three_env84.jsonl",
}
TEST_DAYS = range(140, 174)


def split_days(tables: dict) -> tuple[dict, dict, dict, dict]:
    train, val, test, ctrl = {}, {}, {}, {}
    for (scen, aid), tab in tables.items():
        last = int(tab["z"].index.max())
        key = (scen, aid)
        if scen == "mars":
            train[key] = range(1, 600 - HORIZON + 1)
            val[key] = range(615, last - HORIZON + 1)
        elif scen == "env84":
            train[key] = range(1, last - HORIZON + 1)
        elif scen == "iss":
            train[key] = range(1, 125 - HORIZON + 1)
            val[key] = range(126, 134)
            test[key] = TEST_DAYS
        elif scen == "control":
            ctrl[key] = TEST_DAYS
    return train, val, test, ctrl


# --------------------------------------------------------------------------- basit karşılaştırma yöntemleri
def baseline_preds(df: pd.DataFrame) -> dict[str, np.ndarray]:
    lags = df[[f"bu_lag{j}" for j in range(WINDOW)]].to_numpy(dtype=float)[:, ::-1]   # eski -> yeni
    x = np.arange(WINDOW, dtype=float)
    lin = np.full(len(df), np.nan)
    for i, y in enumerate(lags):
        ok = ~np.isnan(y)
        if ok.sum() >= 3:
            b, a = np.polyfit(x[ok], y[ok], 1)
            lin[i] = a + b * np.arange(WINDOW, WINDOW + HORIZON).mean()   # gelecek 7 günün ortalaması
        else:
            lin[i] = df["bz_lag0"].iloc[i]
    return {"zero (personal normal)": np.zeros(len(df)),
            "persistence (last 7-day mean)": df["bz_lag0"].to_numpy(dtype=float),
            "linear trend": lin}


def scores(df: pd.DataFrame, p: np.ndarray, p90: np.ndarray | None = None) -> dict:
    """Etiketler motorun kendi durum alanından (now_level, target_level); veri artırılmış satırlarda z eşiğinden."""
    y = df["target"].to_numpy(dtype=float)
    p = np.asarray(p, dtype=float)
    out = {"n": int(len(y)), "mae_z": round(float(np.mean(np.abs(y - p))), 3)}
    bad = df["target_level"].to_numpy() >= 1
    out["mae_z_when_target_yellow_or_red"] = round(float(np.mean(np.abs(y[bad] - p[bad]))), 3) if bad.any() else None
    # "yeni sorun" tespiti: şu an yeşilken (motor), gelecek hafta sarı/kırmızı (motor) olacak mı?
    green_now = df["now_level"].to_numpy() == 0
    actual = bad & green_now
    pred = (p >= SARI_Z) & green_now
    tp, fp, fn = int((actual & pred).sum()), int((~actual & pred).sum()), int((actual & ~pred).sum())
    out["onset"] = {"true_new_problems": int(actual.sum()), "flagged": int(pred.sum()), "hit": tp, "false_alarm": fp,
                    "missed": fn,
                    "precision": round(tp / (tp + fp), 3) if tp + fp else None,
                    "recall": round(tp / (tp + fn), 3) if tp + fn else None}
    if p90 is not None:   # "olası" uyarı: üst tahmin sınırı (p90) eşiği geçiyor
        pp = (np.asarray(p90) >= SARI_Z) & green_now
        tp2, fp2, fn2 = int((actual & pp).sum()), int((~actual & pp).sum()), int((actual & ~pp).sum())
        out["onset_possible_p90"] = {"flagged": int(pp.sum()), "hit": tp2, "false_alarm": fp2, "missed": fn2,
                                     "precision": round(tp2 / (tp2 + fp2), 3) if tp2 + fp2 else None,
                                     "recall": round(tp2 / (tp2 + fn2), 3) if tp2 + fn2 else None}
    return out


def fit_models(Xtr, ytr, params) -> dict:
    def mk(q: float) -> HistGradientBoostingRegressor:
        return HistGradientBoostingRegressor(loss="quantile", quantile=q, random_state=0, **params)
    return {"p50": mk(0.5).fit(Xtr, ytr), "p10": mk(0.1).fit(Xtr, ytr), "p90": mk(0.9).fit(Xtr, ytr)}


def lead_times(test: pd.DataFrame, pred: np.ndarray, tables: dict) -> list[dict]:
    """Motorun (durum alanı) TEST aralığındaki ilk sarı/kırmızı günü vs modelin kendi 7 günlük ufkunda DOĞRU çıkan ilk uyarısı.

    Gün t'deki uyarı gün t+7 için bir iddiadır; t+7'de motor hâlâ yeşilse o uyarı yanlış alarmdır, öncü uyarı değil.
    Bu yüzden öncülük süresi en fazla 7 gün olabilir."""
    df = test.assign(pred=pred)
    out = []
    for (scen, aid), tab in tables.items():
        if scen != "iss":
            continue
        for k in KEYS:
            lev = tab["level"][k]
            if lev.isna().all():
                continue
            nz = lev[(lev >= 1) & (lev.index >= TEST_DAYS.start)]
            if nz.empty:
                continue
            first_bad = int(nz.index[0])
            if not (lev.loc[first_bad - 7: first_bad - 1].fillna(0) == 0).all():
                continue
            sub = df[(df.aid == aid) & (df.key == k) & (df.now_level == 0) & (df.day < first_bad)]
            flagged = sub[sub.pred >= SARI_Z]
            correct = flagged[flagged.target_level >= 1]
            first_ok = int(correct.day.min()) if len(correct) else None
            out.append({"astronaut": aid, "indicator": k, "engine_first_yellow_day": first_bad,
                        "model_first_correct_warning_day": first_ok,
                        "lead_days": (first_bad - first_ok) if first_ok else None,
                        "earlier_wrong_flags": int((flagged.target_level == 0).sum())})
    return out


def flag_list(df: pd.DataFrame, pred: np.ndarray) -> list[dict]:
    """Şu an yeşilken 'gelecek hafta sarı/kırmızı' denen her durum ve doğru çıkıp çıkmadığı."""
    d = df.assign(pred=pred)
    f = d[(d.now_level == 0) & (d.pred >= SARI_Z)]
    return [{"astronaut": r.aid, "indicator": r.key, "day": int(r.day), "target_day": int(r.day) + HORIZON,
             "correct": bool(r.target_level >= 1)} for r in f.itertuples()]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True, help="payloads_tr_*.jsonl dosyalarının klasörü")
    args = ap.parse_args()
    data = Path(args.data)
    (ROOT / "reports").mkdir(exist_ok=True)
    (ROOT / "models").mkdir(exist_ok=True)

    long = pd.concat([load_payloads(data / f, s) for s, f in SCEN_FILES.items()], ignore_index=True)
    tables = series_tables(long)
    tr_days, va_days, te_days, ct_days = split_days(tables)
    # --- veri artırma (sadece train ve val aralıkları; test serisine dokunulmaz)
    aids = sorted({aid for (_, aid) in tables})
    plan_tr = {("mars", a): {"days": (1, 600), "copies": 12, "episodes": 3} for a in aids}
    plan_tr |= {("env84", a): {"days": (1, 84), "copies": 6, "episodes": 1} for a in aids}
    plan_tr |= {("iss", a): {"days": (1, 125), "copies": 4, "episodes": 1} for a in aids}
    plan_va = {("mars", a): {"days": (615, 860), "copies": 6, "episodes": 2} for a in aids}
    aug_tr, aug_tr_days, log_tr = augment_tables(tables, plan_tr, seed=1)
    aug_va, aug_va_days, log_va = augment_tables(tables, plan_va, seed=2)
    aug_tr_days = {k: [d for d in v if d + HORIZON <= plan_tr[(k[0].split("_aug")[0], k[1])]["days"][1]] for k, v in aug_tr_days.items()}
    aug_va_days = {k: [d for d in v if d >= 615 and d + HORIZON <= 860] for k, v in aug_va_days.items()}
    print(f"veri artırma: train {len(log_tr)} olay / {len(aug_tr)} kopya, val {len(log_va)} olay / {len(aug_va)} kopya")

    train = pd.concat([build_rows(tables, tr_days), build_rows(aug_tr, aug_tr_days)], ignore_index=True)
    val_real, val_aug = build_rows(tables, va_days), build_rows(aug_va, aug_va_days)
    val = pd.concat([val_real, val_aug], ignore_index=True)
    test, ctrl = build_rows(tables, te_days), build_rows(tables, ct_days)
    print(f"satır sayısı  train {len(train)}  val {len(val)} (gerçek {len(val_real)})  test {len(test)}  kontrol {len(ctrl)}")
    n_on = int(((train.now_level == 0) & (train.target_level >= 1)).sum())
    print(f"train'de 'yeşilken gelecek hafta sarı/kırmızı' örneği: {n_on}")

    Xtr, ytr = train[FEATURES].astype(float), train["target"].to_numpy()
    Xva, yva = val[FEATURES].astype(float), val["target"].to_numpy()

    # --- hiperparametre seçimi (sadece VAL)
    grid = [dict(max_iter=it, learning_rate=lr, max_leaf_nodes=lf, l2_regularization=1.0, min_samples_leaf=40)
            for it in (200, 400) for lr in (0.03, 0.08) for lf in (15, 31)]
    best = None
    for params in grid:
        m = HistGradientBoostingRegressor(loss="quantile", quantile=0.5, random_state=0, **params).fit(Xtr, ytr)
        mae = float(np.mean(np.abs(yva - m.predict(Xva))))
        if best is None or mae < best[0]:
            best = (mae, params)
    print("seçilen parametreler:", best[1], "val MAE", round(best[0], 3))
    models = fit_models(Xtr, ytr, best[1])

    report = {"generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"), "horizon_days": HORIZON,
              "input_window_days": WINDOW, "params": best[1],
              "rows": {"train": len(train), "val": len(val), "val_real": len(val_real), "test": len(test), "control": len(ctrl)},
              "augmentation": {"train_episodes": len(log_tr), "train_copies": len(aug_tr), "val_episodes": len(log_va),
                               "val_copies": len(aug_va),
                               "train_onset_examples": n_on},
              "split": {"train": "Mars t+7<=600, env84 all, ISS t+7<=125",
                        "val": "Mars t>=615, ISS t in 126..133",
                        "test": "ISS mission t in 140..173 (AST-02 cascade), touched once",
                        "control": "ISS control twin t in 140..173 (no planted events)"}}
    for name, df in (("val", val), ("val_real_only", val_real), ("test", test), ("control", ctrl)):
        X = df[FEATURES].astype(float)
        y = df["target"].to_numpy()
        res = {"model": scores(df, models["p50"].predict(X), models["p90"].predict(X))}
        for bname, bp in baseline_preds(df).items():
            res[bname] = scores(df, bp)
        lo, hi = models["p10"].predict(X), models["p90"].predict(X)
        res["model"]["interval_80_coverage"] = round(float(np.mean((y >= lo) & (y <= hi))), 3)
        report[name] = res

    p_test = models["p50"].predict(test[FEATURES].astype(float))
    report["test_lead_times"] = lead_times(test, p_test, tables)
    p90_test = models["p90"].predict(test[FEATURES].astype(float))
    report["test_lead_times_possible_p90"] = lead_times(test, p90_test, tables)
    report["test_flags_possible_p90"] = flag_list(test, p90_test)
    p_ctrl = models["p50"].predict(ctrl[FEATURES].astype(float))
    fa = ctrl[(p_ctrl >= SARI_Z) & (ctrl["now_level"] == 0) & (ctrl["target_level"] == 0)]
    report["control_false_alarms_by_indicator"] = fa.groupby(["aid", "key"]).size().rename("n").reset_index().to_dict("records")
    p90_ctrl = models["p90"].predict(ctrl[FEATURES].astype(float))
    fa2 = ctrl[(p90_ctrl >= SARI_Z) & (ctrl["now_level"] == 0) & (ctrl["target_level"] == 0)]
    report["control_false_alarms_possible_p90"] = fa2.groupby(["aid", "key"]).size().rename("n").reset_index().to_dict("records")
    pd.DataFrame(log_tr + log_va).to_csv(ROOT / "reports" / "augmentation_log.csv", index=False)

    keep = ["scen", "aid", "day", "key", "bz_lag0", "now_level", "target", "target_level"]
    pd.concat([val[keep].assign(split="val", pred=models["p50"].predict(Xva)),
               test[keep].assign(split="test", pred=p_test),
               ctrl[keep].assign(split="control", pred=p_ctrl)]).round(3).to_csv(ROOT / "reports" / "val_test_predictions.csv", index=False)

    models.update({"version": "forecast_v1", "features": FEATURES, "val_mae_z": report["val"]["model"]["mae_z"],
                   "trained_at": report["generated_at"]})
    joblib.dump(models, ROOT / "models" / "forecast_v1.joblib")
    (ROOT / "reports" / "metrics.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("val", "val_real_only", "test", "control", "test_lead_times",
                                             "test_lead_times_possible_p90", "test_flags_possible_p90",
                                             "control_false_alarms_by_indicator",
                                             "control_false_alarms_possible_p90")},
                     indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
