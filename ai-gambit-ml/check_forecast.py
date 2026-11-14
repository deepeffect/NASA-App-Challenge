"""
check_forecast.py  --  Tahmin JSON'unun temel kurallarını kontrol eder (pytest gerekmez).

    python check_forecast.py --data <payload klasörü>

Kontroller:
  1. Gelecek sızıntısı yok: gün 156 tahmini, 157+ günleri silinmiş veriyle aynı çıkar.
  2. Yer ekibi görünümü öz bildirimleri (stres, ruh hali, uyku kalitesi) içermez.
  3. Baseline oluşmadan (gün 10) tahmin verilmez: status = insufficient_data.
  4. Kontrol ikizinde (olay yok) AST-02 gün 140-173 arası hiçbir gösterge "likely" çıkmaz.
  5. JSON'daki her sayı sonlu ve aralık alt sınırı <= üst sınır.
"""
import argparse
import json
import math

from predict import forecast_from_records


def load(path):
    return [json.loads(line) for line in open(path, encoding="utf-8")]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    a = ap.parse_args()
    mission = load(f"{a.data}/payloads_tr_mission_iss180.jsonl")
    control = load(f"{a.data}/payloads_tr_control_iss180.jsonl")
    results = []

    def check(name, cond):
        results.append(bool(cond))
        print(("GEÇTİ " if cond else "KALDI ") + name)

    full = forecast_from_records(mission, "AST-02", 156)
    cut = forecast_from_records([r for r in mission if r["gorev_gunu"] <= 156], "AST-02", 156)
    check("1 gelecek sızıntısı yok", full == cut)

    ground = forecast_from_records(mission, "AST-02", 156, audience="ground")
    check("2 yer ekibi görünümünde öz bildirim yok", not any(d["self_report"] for d in ground["forecasts"]))

    check("3 baseline yokken tahmin yok", forecast_from_records(mission, "AST-01", 10)["status"] == "insufficient_data")

    flagged = [(t, d["indicator"], d["risk_next_week"]) for t in range(140, 174)
               for d in forecast_from_records(control, "AST-02", t)["forecasts"] if d["risk_next_week"] != "low"]
    check(f"4 kontrol ikizinde (AST-02, gün 140-173) 'likely' veya 'possible' yok (bulunan: {flagged[:5]})", not flagged)

    good = all(math.isfinite(d["forecast_next_7_day_mean"]) and d["forecast_range_80pct"][0] <= d["forecast_range_80pct"][1]
               for d in full["forecasts"])
    check("5 sayılar sonlu, aralıklar düzgün", good)

    # 6. birimdeki değişim yönü z'deki değişim yönüyle aynı (tüm test günleri)
    bad_dir = []
    for t in range(140, 174):
        for d in forecast_from_records(mission, "AST-02", t)["forecasts"]:
            du = d["forecast_next_7_day_mean"] - d["last_7_day_mean"]
            dz = d["z_forecast"] - d["z_now"]
            if abs(du) > 0.02 and abs(dz) > 0.02 and (du > 0) != (dz > 0):
                bad_dir.append((t, d["indicator"], du, dz))
    check(f"6 birim yönü = z yönü (çelişen: {bad_dir[:3]})", not bad_dir)

    # 7. kötü uç doğru tarafta: worse_when 'higher' ise worst_case_value aralığın üst ucu, 'lower' ise alt ucu
    ends_ok = all(d["worst_case_value"] == d["forecast_range_80pct"][1 if d["worse_when"] == "higher" else 0]
                  for d in full["forecasts"])
    check("7 worst_case_value aralığın kötü ucunda", ends_ok)
    raise SystemExit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
