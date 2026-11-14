#!/usr/bin/env python3
"""Prototipe gömülü veriden veri setini yeniden üretir (orijinal astronaut_health.json kayıpsa).

    python scripts/extract_dataset_from_artifact.py            # yaz + doğrula
    python scripts/extract_dataset_from_artifact.py --check    # sadece mevcut dosyayı doğrula

Girdi : frontend/reference/personal-artifact.html  (<script type="application/json" id="data">)
Çıktı : data/raw/astronaut_health.json

DİKKAT: Bu bir YENİDEN ÜRETİMDİR. Ölçüm kolon adları (`exp_radiation_mSv_day` vb.) gömülü veriden
birebir gelir; diğer alan adları (`health_status`, `self_care_actions` …) tahmindir. Gömülü veride
olmayan hiçbir şey eklenmez; prototipin metadata'sı (indicators/solutions) bu dosyaya alınmaz.
Doğrulama: çıktı tekrar prototip formatına paketlenir ve gömülü veriyle birebir karşılaştırılır.

Sadece standart kütüphane kullanır.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_HTML = REPO_ROOT / "frontend" / "reference" / "personal-artifact.html"
DEFAULT_OUT = REPO_ROOT / "data" / "raw" / "astronaut_health.json"

DATA_RE = re.compile(r'<script type="application/json" id="data">(.*?)</script>', re.S)
AREAS = ("immune", "bone_muscle", "cardiovascular", "behavioral")
ASTRONAUT_FIELDS = ("age", "sex", "bmi", "mission", "profile")


def load_embedded(html_path: Path) -> dict:
    m = DATA_RE.search(html_path.read_text(encoding="utf-8"))
    if not m:
        raise SystemExit(f'{html_path}: <script id="data"> bloğu bulunamadı')
    return json.loads(m.group(1))


def unpack(emb: dict) -> dict:
    """Gömülü (sütun dizili, indeksli) format → astronot + günlük kayıt listesi."""
    codes = [s["code"] for s in emb["solutions"]]
    columns = [ind["col"] for ind in emb["indicators"]]
    astronauts, records = [], []
    for a in emb["astronauts"]:
        astronauts.append({"astronaut_id": a["id"], **{k: a[k] for k in ASTRONAUT_FIELDS}})
        for i, mission_day in enumerate(a["days"]):
            rec: dict = {"astronaut_id": a["id"], "mission_day": mission_day}
            rec.update({c: a["v"][c][i] for c in columns})
            rec.update({f"{k}_score": a["score"][k][i] for k in AREAS})
            rec["daily_health_score"] = a["daily"][i]
            rec["cumulative_health_score"] = a["cum"][i]
            rec["health_status"] = a["status"][i]
            rec["main_concern"] = a["concern"][i]
            rec["self_care_actions"] = [codes[k] for k in a["act"][i]]  # sıra korunur (öncelik sırası)
            rec["needs_ground_support"] = bool(a["ground"][i])
            records.append(rec)
    return {
        "_reconstructed": {
            "source": "frontend/reference/personal-artifact.html (<script id=\"data\">)",
            "script": "scripts/extract_dataset_from_artifact.py",
            "note": "Orijinal veri setinin yeniden üretimi. Ölçüm kolon adları gömülü veriden; diğer alan adları tahmin.",
        },
        "astronauts": astronauts,
        "records": records,
    }


def repack(ds: dict, emb: dict) -> dict:
    """Yeniden üretilen dosya → gömülü format (doğrulama için ters dönüşüm)."""
    code_idx = {s["code"]: k for k, s in enumerate(emb["solutions"])}
    columns = [ind["col"] for ind in emb["indicators"]]
    by_id: dict[str, list[dict]] = {}
    for r in ds["records"]:
        by_id.setdefault(r["astronaut_id"], []).append(r)
    out = []
    for a in ds["astronauts"]:
        rs = sorted(by_id.get(a["astronaut_id"], []), key=lambda r: r["mission_day"])
        out.append({
            "id": a["astronaut_id"], **{k: a[k] for k in ASTRONAUT_FIELDS},
            "days": [r["mission_day"] for r in rs],
            "v": {c: [r[c] for r in rs] for c in columns},
            "score": {k: [r[f"{k}_score"] for r in rs] for k in AREAS},
            "daily": [r["daily_health_score"] for r in rs],
            "cum": [r["cumulative_health_score"] for r in rs],
            "status": [r["health_status"] for r in rs],
            "concern": [r["main_concern"] for r in rs],
            "act": [[code_idx[c] for c in r["self_care_actions"]] for r in rs],
            "ground": [int(r["needs_ground_support"]) for r in rs],
        })
    return {"indicators": emb["indicators"], "solutions": emb["solutions"], "astronauts": out}


def dump(ds: dict) -> str:
    """Okunur ve git diff dostu: her kayıt tek satır."""
    head = json.dumps(ds["_reconstructed"], ensure_ascii=False, indent=2).replace("\n", "\n  ")
    rows = lambda xs: ",\n    ".join(json.dumps(x, ensure_ascii=False) for x in xs)  # noqa: E731
    return (
        "{\n"
        f'  "_reconstructed": {head},\n'
        f'  "astronauts": [\n    {rows(ds["astronauts"])}\n  ],\n'
        f'  "records": [\n    {rows(ds["records"])}\n  ]\n'
        "}\n"
    )


def check(out_path: Path, emb: dict) -> None:
    ds = json.loads(out_path.read_text(encoding="utf-8"))
    if repack(ds, emb) != emb:
        raise SystemExit(f"DOĞRULAMA BAŞARISIZ: {out_path} gömülü veriyle birebir eşleşmiyor")
    print(f"Doğrulandı: {len(ds['astronauts'])} astronot, {len(ds['records'])} günlük kayıt; "
          "gömülü veriyle birebir aynı.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--html", type=Path, default=DEFAULT_HTML)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--check", action="store_true", help="Yazma, sadece mevcut çıktıyı doğrula")
    args = ap.parse_args()
    emb = load_embedded(args.html)
    if not args.check:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(dump(unpack(emb)), encoding="utf-8", newline="\n")
        print(f"Yazıldı: {args.out}")
    check(args.out, emb)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # Windows konsolu (cp1252) için
    main()
