"""
train_v2.py  --  Gelecek hafta tahmin modeli v2: takımın hastalıklı veri seti (hastalikli_v1) ile eğitim.

    python train_v2.py --data <hastalikli_v1 klasörü> --old <egemen payload klasörü>

Fark (v1'e göre):
  - v1 Egemen'in 4 senaryosu + bizim rastgele veri artırmamızla eğitildi (gerçek kötüleşme örneği azdı).
  - v2 takımın veri setindeki 320 seed x (olaylı + kontrol ikizi) koşudan eğitilir. Veri artırma YOK.
  - Bölme: veri setinin sabit seed ayrımı (splits.json). Bir seed'in olaylı ve kontrol koşusu aynı kümede.
  - Olaylı + kontrol koşuları birlikte eğitime girer: veri setinde olaylar bilerek ~1,5-2 kat sık; kontrol koşuları
    bu zenginleştirmeyi kısmen dengeler (bilinçli seçim).
  - Eğitim satırları gün atlayarak (stride) seyreltilir; etikete göre seçim YAPILMAZ. labels/ ve ground_truth/
    sadece ölçümde kullanılır, model girdisi değildir.
  - Hiperparametreler sadece val seed'leriyle seçilir. Test seed'leri en sonda bir kez ölçülür.
  - Ek test: Egemen'in v3.1 ISS görevi (AST-02 zinciri, gün 140-173) + kontrol ikizi. Bu görev v2 eğitiminde yok.

Çıktılar: models/forecast_v2.joblib, reports_v2/metrics_v2.json, reports_v2/test_predictions_v2.csv.gz, reports_v2/train_log_v2.txt
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

from features_fast import series_rows
from forecast_core import FEATURES, SARI_Z, build_rows, load_payloads, series_tables
from train import lead_times, scores

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "reports_v2"
ALARM_TYPES = ("uri_fever", "stress_sleep", "exercise_lapse")   # should_alarm = yes olan mürettebat olayları
STRIDE = {("iss180", "event"): 4, ("iss180", "control"): 8, ("mars860", "event"): 6, ("mars860", "control"): 12}
LOG: list[str] = []


def log(msg: str) -> None:
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    LOG.append(line)


def run_tables(data: Path, mission: str, seed: int, variant: str) -> dict:
    name = f"{mission}_s{seed}_{variant}"
    return series_tables(load_payloads(data / "payloads_tr" / f"{name}.jsonl", name))


def collect(data: Path, plan: list[tuple[str, int, str]], stride_mult: float, rng: np.random.Generator) -> pd.DataFrame:
    """Koşulardan seyreltilmiş özellik satırları (gün atlayarak; başlangıç günü rastgele, etikete bakılmaz)."""
    parts = []
    for n, (mission, seed, variant) in enumerate(plan):
        st = max(1, int(round(STRIDE[(mission, variant)] * stride_mult)))
        for (_, aid), tab in run_tables(data, mission, seed, variant).items():
            idx = tab["z"].index
            off = int(rng.integers(st))
            df = series_rows(tab, days=range(int(idx[0]) + off, int(idx[-1]) + 1, st))
            if len(df):
                parts.append(df.drop(columns=["key"]))
        if (n + 1) % 50 == 0:
            log(f"  {n + 1}/{len(plan)} koşu okundu")
    return pd.concat(parts, ignore_index=True)


def plan_for(splits: dict, split: str) -> list[tuple[str, int, str]]:
    return [(m, s, v) for m in ("iss180", "mars860") for s in splits[m][split] for v in ("event", "control")]


def mae(y, p) -> float:
    return round(float(np.mean(np.abs(np.asarray(y, float) - np.asarray(p, float)))), 3)


def onset_counts(df: pd.DataFrame, pred: np.ndarray) -> dict:
    """Gösterge düzeyi: şu an yeşil (motor) -> 7 gün sonra sarı/kırmızı (motor)."""
    green = df["now_level"].to_numpy() == 0
    actual = green & (df["target_level"].to_numpy() >= 1)
    flag = green & (np.asarray(pred) >= SARI_Z)
    tp, fp, fn = int((actual & flag).sum()), int((~actual & flag).sum()), int((actual & ~flag).sum())
    return {"true_new_problems": int(actual.sum()), "hit": tp, "false_alarm": fp, "missed": fn,
            "precision": round(tp / (tp + fp), 3) if tp + fp else None,
            "recall": round(tp / (tp + fn), 3) if tp + fn else None}


def alarm_days(pred_df: pd.DataFrame, col: str) -> pd.DataFrame:
    """Astronot-gün düzeyi alarm: herhangi bir gösterge şu an yeşilken tahmin sarı/kırmızı eşiğini geçiyor."""
    a = pred_df.assign(flag=(pred_df["now_level"] == 0) & (pred_df[col] >= SARI_Z))
    return a.groupby(["run_id", "variant", "aid", "day"], as_index=False)["flag"].any()


def event_early_warning(pred_df: pd.DataFrame, events: pd.DataFrame, cols: dict[str, str]) -> dict:
    """Alarm beklenen her olay için: başlangıçtan önceki 7 günde (onset-7 .. onset-1) alarm var mı?
    Şans karşılaştırması: AYNI seed'in kontrol ikizinde, aynı astronot ve aynı günlerde alarm var mı?
    Motor referansı: aynı pencerede motorun herhangi bir göstergesi sarı/kırmızı mı (now_level >= 1)?"""
    out = {}
    eng = (pred_df.assign(flag=pred_df["now_level"] >= 1)
           .groupby(["run_id", "variant", "aid", "day"], as_index=False)["flag"].any())
    sources = {name: alarm_days(pred_df, c) for name, c in cols.items()} | {"engine (any indicator yellow/red)": eng}
    for name, ad in sources.items():
        s = ad.set_index(["run_id", "variant", "aid", "day"])["flag"]
        res = {}
        for typ in ALARM_TYPES + ("all",):
            ev = events if typ == "all" else events[events.type == typ]
            hit_e = hit_c = 0
            for e in ev.itertuples():
                days = range(e.onset_day - 7, e.onset_day)
                fe = s.reindex([(e.run_id, "event", e.astronaut_id, d) for d in days]).fillna(False).to_numpy(bool)
                fc = s.reindex([(e.run_id, "control", e.astronaut_id, d) for d in days]).fillna(False).to_numpy(bool)
                hit_e += int(fe.any())
                hit_c += int(fc.any())
            n = len(ev)
            res[typ] = {"events": n, "warned_before_onset": hit_e, "same_window_in_control_twin": hit_c,
                        "rate": round(hit_e / n, 3) if n else None,
                        "control_rate": round(hit_c / n, 3) if n else None}
        ctrl = ad[ad.variant == "control"]
        res["control_alarm_days_per_100"] = round(100 * float(ctrl["flag"].mean()), 2)
        g = ctrl.groupby(["run_id", "aid"])["flag"].any()
        res["control_astronauts_with_any_alarm"] = f"{int(g.sum())}/{len(g)}"
        out[name] = res
    return out


def main() -> None:
    global OUT
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True, help="hastalikli_v1 klasörü")
    ap.add_argument("--old", required=True, help="Egemen'in payload klasörü (payloads_tr_mission_iss180.jsonl)")
    ap.add_argument("--stride-mult", type=float, default=1.0, help="eğitim seyreltmesi çarpanı (bellek için)")
    ap.add_argument("--limit", type=int, default=0, help="hızlı deneme: her kümeden ilk N seed (model kaydedilmez)")
    args = ap.parse_args()
    data, old = Path(args.data), Path(args.old)
    OUT.mkdir(exist_ok=True)
    (ROOT / "models").mkdir(exist_ok=True)
    splits = json.loads((data / "splits.json").read_text(encoding="utf-8"))
    if args.limit:   # sadece hızlı deneme için: her kümeden ilk N seed; sonuçlar raporlanmaz
        splits = {m: {k: (v[: args.limit] if isinstance(v, list) and k in ("train", "val", "test") else v)
                      for k, v in s.items()} for m, s in splits.items()}
        OUT = ROOT / "reports_v2_smoke"
        OUT.mkdir(exist_ok=True)
    rng = np.random.default_rng(7)
    t0 = time.time()

    # ---------------------------------------------------------------- train / val
    log("train koşuları okunuyor")
    train = collect(data, plan_for(splits, "train"), args.stride_mult, rng)
    n_on = int(((train.now_level == 0) & (train.target_level >= 1)).sum())
    log(f"train satırı: {len(train)}  (yeşilken gelecek hafta sarı/kırmızı: {n_on})")
    log("val koşuları okunuyor")
    val = collect(data, plan_for(splits, "val"), 0.5, rng)
    log(f"val satırı: {len(val)}")
    Xtr, ytr = train[FEATURES].astype(np.float32), train["target"].to_numpy(np.float32)
    Xva, yva = val[FEATURES].astype(np.float32), val["target"].to_numpy(np.float32)
    rows = {"train": int(len(train)), "val": int(len(val)), "train_onset_examples": n_on}
    del train

    grid = [dict(max_iter=300, learning_rate=0.05, max_leaf_nodes=31),
            dict(max_iter=300, learning_rate=0.05, max_leaf_nodes=63),
            dict(max_iter=300, learning_rate=0.1, max_leaf_nodes=31),
            dict(max_iter=600, learning_rate=0.05, max_leaf_nodes=63)]
    best = None
    for g in grid:
        params = g | dict(l2_regularization=1.0, min_samples_leaf=100)
        ts = time.time()
        m = HistGradientBoostingRegressor(loss="quantile", quantile=0.5, random_state=0, **params).fit(Xtr, ytr)
        v = mae(yva, m.predict(Xva))
        log(f"grid {g}: val MAE {v} ({time.time() - ts:.0f} sn)")
        if best is None or v < best[0]:
            best = (v, params)
    log(f"seçilen: {best[1]}  val MAE {best[0]}")

    def mk(q):
        return HistGradientBoostingRegressor(loss="quantile", quantile=q, random_state=0, **best[1]).fit(Xtr, ytr)
    models = {"p50": mk(0.5), "p10": mk(0.1), "p90": mk(0.9)}
    del Xtr, ytr
    lo, hi = models["p10"].predict(Xva), models["p90"].predict(Xva)
    val_cov = round(float(np.mean((yva >= lo) & (yva <= hi))), 3)
    val_onset = {"likely": onset_counts(val, models["p50"].predict(Xva)), "possible": onset_counts(val, hi)}
    log(f"val %80 aralık kapsaması {val_cov}; val onset {val_onset}")
    val_mae = best[0]
    del val, Xva, yva
    models.update({"version": "forecast_v2", "features": FEATURES, "val_mae_z": val_mae,
                   "trained_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                   "trained_on": "hastalikli_v1 train seeds (ISS 210, Mars 14; event + control runs)"})
    if not args.limit:
        joblib.dump(models, ROOT / "models" / "forecast_v2.joblib")
        log("model kaydedildi: models/forecast_v2.joblib")

    # ---------------------------------------------------------------- test (bir kez)
    v1 = joblib.load(ROOT / "models" / "forecast_v1.joblib")
    preds, events = [], []
    plan = plan_for(splits, "test")
    for n, (mission, seed, variant) in enumerate(plan):
        run_id = f"{mission}_s{seed}"
        for (_, aid), tab in run_tables(data, mission, seed, variant).items():
            df = series_rows(tab)
            if not len(df):
                continue
            X = df[FEATURES].astype(np.float32)   # isimli sütunlar: predict.py de DataFrame veriyor
            preds.append(pd.DataFrame({
                "run_id": run_id, "mission": mission, "variant": variant, "aid": aid, "key": df["key"].to_numpy(),
                "day": df["day"].to_numpy(), "now_level": df["now_level"].to_numpy(),
                "target_level": df["target_level"].to_numpy(), "target": df["target"].to_numpy(),
                "persist": df["bz_lag0"].to_numpy(),
                "v2_p50": models["p50"].predict(X).astype(np.float32),
                "v2_p10": models["p10"].predict(X).astype(np.float32),
                "v2_p90": models["p90"].predict(X).astype(np.float32),
                "v1_p50": v1["p50"].predict(X).astype(np.float32),
                "v1_p90": v1["p90"].predict(X).astype(np.float32)}))
        if variant == "event":
            gt = json.loads((data / "ground_truth" / f"{run_id}_event.json").read_text(encoding="utf-8"))
            for e in gt["events"]:
                if e["type"] in ALARM_TYPES and e["astronaut_id"].startswith("AST"):
                    events.append({"run_id": run_id, "astronaut_id": e["astronaut_id"], "type": e["type"],
                                   "onset_day": int(e["onset_day"]), "severity": e.get("severity")})
        if (n + 1) % 30 == 0:
            log(f"  test {n + 1}/{len(plan)} koşu")
    P = pd.concat(preds, ignore_index=True)
    E = pd.DataFrame(events)
    # başlangıçtan önceki 7 gün tahmin edilebilir olmalı (z başlamış olmalı): çok erken olaylar sayılmaz
    first = P.groupby(["run_id", "aid"])["day"].min().rename("first").reset_index()
    E = E.merge(first, left_on=["run_id", "astronaut_id"], right_on=["run_id", "aid"], how="left")
    E_scored = E[E.onset_day - 7 >= E["first"]].drop(columns=["aid", "first"])
    log(f"test tahmin satırı {len(P)}; alarm beklenen olay {len(E)} (penceresi tahmin edilebilir: {len(E_scored)})")

    rep = {"generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"), "params": best[1], "rows": rows,
           "val": {"mae_z": val_mae, "interval_80_coverage": val_cov, "onset": val_onset},
           "split": "hastalikli_v1 splits.json (seed level); train rows thinned by day stride "
                    + json.dumps({f"{k[0]}/{k[1]}": v for k, v in STRIDE.items()})}
    for variant in ("event", "control"):
        d = P[P.variant == variant]
        y = d["target"].to_numpy()
        rep[f"test_{variant}"] = {
            "n": int(len(d)),
            "mae_z": {"v2": mae(y, d.v2_p50), "v1": mae(y, d.v1_p50), "zero (personal normal)": mae(y, np.zeros(len(d))),
                      "persistence (last 7-day mean)": mae(y, d.persist)},
            "interval_80_coverage_v2": round(float(np.mean((y >= d.v2_p10) & (y <= d.v2_p90))), 3),
            "onset": {"v2 likely": onset_counts(d, d.v2_p50.to_numpy()), "v2 possible": onset_counts(d, d.v2_p90.to_numpy()),
                      "v1 likely": onset_counts(d, d.v1_p50.to_numpy()), "v1 possible": onset_counts(d, d.v1_p90.to_numpy()),
                      "persistence": onset_counts(d, d.persist.to_numpy())}}
    rep["test_event_early_warning"] = event_early_warning(
        P, E_scored, {"v2 possible": "v2_p90", "v2 likely": "v2_p50", "v1 possible": "v1_p90", "v1 likely": "v1_p50"})
    rep["test_events_by_type"] = E_scored.type.value_counts().to_dict()
    ev_rows = P[P.variant == "event"]
    rep["test_event_onset_by_indicator_v2_possible"] = {k: onset_counts(g, g.v2_p90.to_numpy())
                                                         for k, g in ev_rows.groupby("key")}
    P.round(3).to_csv(OUT / "test_predictions_v2.csv.gz", index=False, compression="gzip")
    del P, ev_rows

    # ---------------------------------------------------------------- Egemen'in v3.1 demosu (AST-02 zinciri)
    long = pd.concat([load_payloads(old / "payloads_tr_mission_iss180.jsonl", "iss"),
                      load_payloads(old / "payloads_tr_control_iss180.jsonl", "control")], ignore_index=True)
    tabs = series_tables(long)
    iss_tabs = {k: v for k, v in tabs.items() if k[0] == "iss"}
    demo = build_rows(iss_tabs, {k: range(140, 174) for k in iss_tabs})
    ctrl_tabs = {k: v for k, v in tabs.items() if k[0] == "control"}
    ctrl = build_rows(ctrl_tabs, {k: range(140, 174) for k in ctrl_tabs})
    rep["demo_v31"] = {}
    for name, m in (("v1", v1), ("v2", models)):
        Xd, Xc = demo[FEATURES].astype(float), ctrl[FEATURES].astype(float)
        p50, p90 = m["p50"].predict(Xd), m["p90"].predict(Xd)
        c50, c90 = m["p50"].predict(Xc), m["p90"].predict(Xc)
        green_c = ctrl.now_level.to_numpy() == 0
        rep["demo_v31"][name] = {
            "test": scores(demo, p50, p90),
            "lead_times_possible": lead_times(demo, p90, iss_tabs),
            "control_flags_likely": int(((c50 >= SARI_Z) & green_c).sum()),
            "control_flags_possible": int(((c90 >= SARI_Z) & green_c).sum()),
            "control_flags_possible_AST02": int(((c90 >= SARI_Z) & green_c & (ctrl.aid.to_numpy() == "AST-02")).sum()),
        }
    d1, d2 = rep["demo_v31"]["v1"], rep["demo_v31"]["v2"]
    ship = (d2["test"]["onset_possible_p90"]["hit"] >= d1["test"]["onset_possible_p90"]["hit"]
            and d2["control_flags_possible_AST02"] == 0 and d2["control_flags_likely"] == 0)
    rep["ship_rule"] = {"rule": "v2 default only if on the v3.1 AST-02 demo (days 140-173) it catches >= v1's onsets at "
                                "'possible' and has 0 'likely' flags on the control twin and 0 'possible' flags on control AST-02",
                        "v2_becomes_default": bool(ship)}
    rep["minutes"] = round((time.time() - t0) / 60, 1)
    (OUT / "metrics_v2.json").write_text(json.dumps(rep, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    log(f"bitti ({rep['minutes']} dk). ship rule: v2 varsayılan olsun mu? {ship}")
    (OUT / "train_log_v2.txt").write_text("\n".join(LOG), encoding="utf-8")


if __name__ == "__main__":
    main()
