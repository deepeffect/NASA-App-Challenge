"""
predict.py  --  Eğitilmiş modelle bir astronotun gelecek hafta tahminini LLM'e verilecek JSON olarak üretir.

Komut satırı:
    python predict.py --payloads <payloads_tr_mission_iss180.jsonl> --astronaut AST-02 --day 156
    python predict.py --payloads <...jsonl> --astronaut AST-02 --day 156 --audience ground   # öz bildirimler çıkarılır

Asistan API'sinden (Python) çağırma:
    from predict import forecast_from_records
    js = forecast_from_records(records, astronaut_id="AST-02", day=156)

`records`: o astronotun görevin BAŞINDAN o güne kadarki payload kayıtları (dict listesi, jsonl satırlarıyla aynı yapı).
Model son 7 güne bakar; ilk ~20 gün sadece kişisel baseline'ı (değerleri birime çevirmek için) hesaplamakta kullanılır.
"""
from __future__ import annotations

import argparse
import json
import os
import tempfile
from functools import lru_cache
from pathlib import Path

import joblib
import pandas as pd

from forecast_core import forecast_json, load_payloads, series_tables

MODELS_DIR = Path(__file__).resolve().parent / "models"
DEFAULT_MODEL = "forecast_v2"
# Model seçimi: ortam değişkeni AI_GAMBIT_FORECAST_MODEL=forecast_v1 / forecast_v2 (boşsa DEFAULT_MODEL)
MODEL_PATH = MODELS_DIR / f"{os.environ.get('AI_GAMBIT_FORECAST_MODEL') or DEFAULT_MODEL}.joblib"


@lru_cache(maxsize=1)
def load_model(path: str = str(MODEL_PATH)) -> dict:
    return joblib.load(path)


def _records_to_long(records: list[dict], aid: str) -> pd.DataFrame:
    # load_payloads dosya okur; aynı ayrıştırmayı kullanmak için kayıtları geçici jsonl'e yazıyoruz
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, encoding="utf-8") as fh:
        for r in records:
            if r.get("astronot_id") == aid:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        tmp = fh.name
    try:
        return load_payloads(tmp, "live")
    finally:
        os.unlink(tmp)


def forecast_from_records(records: list[dict], astronaut_id: str, day: int | None = None,
                          audience: str = "astronaut") -> dict:
    if day is not None:
        records = [r for r in records if int(r["gorev_gunu"]) <= day]   # gelecek günleri asla görmesin
    long = _records_to_long(records, astronaut_id)
    if long.empty:
        return {"type": "health_forecast", "astronaut_id": astronaut_id, "status": "no_data"}
    tab = series_tables(long)[("live", astronaut_id)]
    t = int(day if day is not None else tab["value"].index.max())
    return forecast_json(load_model(), tab, astronaut_id, t, audience=audience)


def main() -> None:
    ap = argparse.ArgumentParser(description="Gelecek hafta tahmini (LLM JSON)")
    ap.add_argument("--payloads", required=True, help="payloads_tr_*.jsonl dosyası")
    ap.add_argument("--astronaut", required=True)
    ap.add_argument("--day", type=int, default=None, help="tahminin yapıldığı görev günü (boş: son gün)")
    ap.add_argument("--audience", choices=["astronaut", "ground"], default="astronaut")
    args = ap.parse_args()
    records = [json.loads(line) for line in open(args.payloads, encoding="utf-8")]
    print(json.dumps(forecast_from_records(records, args.astronaut, args.day, args.audience), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
