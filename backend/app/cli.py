"""Komut satırı araçları.

    python -m app.cli seed [--seed 42] [--spe-day 120]   # sentetik veriyi DB'ye yükle (DB'yi sıfırlar)
    python -m app.cli ingest data/raw/dosya.csv          # dosyayı API'siz yükle
    python -m app.cli export-openapi                     # docs/openapi.json üret
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from app.config import REPO_ROOT


def cmd_seed(args: argparse.Namespace) -> None:
    from app.data.seed import seed_database
    from app.data.synthetic import SyntheticConfig

    cfg = SyntheticConfig(
        seed=args.seed,
        days=args.days,
        start=date.fromisoformat(args.start),
        scenario_day=args.scenario_day,
        scenario_astronaut=None if args.no_scenario else "AST-02",
        spe_day=args.spe_day,
    )
    stats = seed_database(cfg, reset=not args.keep)
    print("Sentetik veri yüklendi:")
    for k, v in stats.items():
        print(f"  {k}: {v}")


def cmd_ingest(args: argparse.Namespace) -> None:
    from sqlmodel import Session

    from app.db import get_engine, init_db
    from app.ingest.pipeline import ingest_bytes

    init_db()
    path = Path(args.path)
    with Session(get_engine()) as s:
        report = ingest_bytes(s, path.name, path.read_bytes(), args.adapter, args.astronaut_id)
    print(json.dumps(report.model_dump(mode="json"), indent=2, ensure_ascii=False))


def cmd_export_openapi(args: argparse.Namespace) -> None:
    from app.main import app

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(app.openapi(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"OpenAPI şeması yazıldı: {out}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m app.cli", description="Astronaut Health Monitor CLI")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("seed", help="Sentetik veriyi üret ve DB'ye yükle (varsayılan: DB'yi sıfırlar)")
    s.add_argument("--seed", type=int, default=42)
    s.add_argument("--days", type=int, default=180)
    s.add_argument("--start", default="2026-05-19", help="Görevin ilk günü (YYYY-MM-DD)")
    s.add_argument("--scenario-day", type=int, default=150, help="AST-02 senaryosunun başladığı görev günü")
    s.add_argument("--no-scenario", action="store_true", help="Demo senaryosunu kapat (herkes normal)")
    s.add_argument("--spe-day", type=int, default=None, help="Güneş parçacık olayı (SPE) günü; boş → kapalı")
    s.add_argument("--keep", action="store_true", help="DB'yi sıfırlama, üzerine ekle")
    s.set_defaults(func=cmd_seed)

    i = sub.add_parser("ingest", help="CSV/JSON dosyasını DB'ye yükle")
    i.add_argument("path")
    i.add_argument("--adapter", default=None)
    i.add_argument("--astronaut-id", default=None)
    i.set_defaults(func=cmd_ingest)

    e = sub.add_parser("export-openapi", help="OpenAPI şemasını docs/openapi.json'a yaz")
    e.add_argument("--out", default=str(REPO_ROOT / "docs" / "openapi.json"))
    e.set_defaults(func=cmd_export_openapi)
    return p


def main(argv: list[str] | None = None) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # Windows konsolunda Türkçe karakterler
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
