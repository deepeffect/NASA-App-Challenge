"""Komut satırı araçları.

    python -m app.cli reset                              # bu istasyonun (STATION_ROLE) DB'sini sıfırla
    python -m app.cli seed [--seed 42] [--spe-day 120]   # sentetik veriyi DB'ye yükle (DB'yi sıfırlar)
    python -m app.cli ingest data/raw/dosya.csv          # dosyayı API'siz yükle
    python -m app.cli analyze [--as-of 2026-10-20]       # ekip durumu konsolda
    python -m app.cli reindex                            # RAG belgelerini yeniden indeksle
    python -m app.cli export-openapi                     # docs/openapi.json üret
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from app.config import REPO_ROOT


def cmd_reset(args: argparse.Namespace) -> None:
    """Seçili rolün DB'sindeki bütün tabloları silip yeniden kurar (dosya kilitliyken de çalışır)."""
    from sqlmodel import SQLModel

    from app.config import get_settings
    from app.db import get_engine, init_db
    from app.models import tables  # noqa: F401  (metadata'ya kayıt)

    s = get_settings()
    SQLModel.metadata.drop_all(get_engine())
    init_db()
    print(f"[{s.station_role}] veritabanı sıfırlandı: {s.database_url_resolved}")
    if s.station_role == "ship" and s.data_source == "astronaut_health":
        from app.personal.store import ensure_dataset_loaded

        stats = ensure_dataset_loaded(get_engine(), s, force=True)
        print(f"Veri seti yüklendi ({s.dataset_path.name}): {stats}")


def _force_synthetic() -> None:
    """Eski komutlar (seed/ingest/analyze) her zaman sentetik moddadır → DB: data/processed/health.db."""
    import os

    from app.config import get_settings
    from app.db import reset_engine

    os.environ["DATA_SOURCE"] = "synthetic"
    get_settings.cache_clear()
    reset_engine()


def cmd_seed(args: argparse.Namespace) -> None:
    _force_synthetic()
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

    _force_synthetic()
    from app.db import get_engine, init_db
    from app.ingest.pipeline import ingest_bytes

    init_db()
    path = Path(args.path)
    with Session(get_engine()) as s:
        report = ingest_bytes(s, path.name, path.read_bytes(), args.adapter, args.astronaut_id)
    print(json.dumps(report.model_dump(mode="json"), indent=2, ensure_ascii=False))


def cmd_analyze(args: argparse.Namespace) -> None:
    """Konsolda ekip durumu ve aktif olaylar (veri/analiz sorumlusu için hızlı kontrol)."""
    _force_synthetic()
    from sqlmodel import Session

    from app.db import get_engine, init_db
    from app.services.data import get_data_service

    init_db()
    with Session(get_engine()) as s:
        res = get_data_service().analysis(s, date.fromisoformat(args.as_of) if args.as_of else None)
    m = res.mission()
    print(f"as_of={m.as_of}  görev günü {m.mission_day}/{m.total_days}")
    for aid, a in res.astronauts.items():
        flagged = ", ".join(f"{x.system}={x.status}({x.score:.0f})" for x in a.systems if x.status not in ("green",) and x.score is not None)
        print(f"\n{aid} {a.info.name:<12} {a.overall.status.upper():<7} skor={a.overall.score}  {flagged}")
        for e in a.active_events:
            if e.severity == "info" and not args.all:
                continue
            print(f"   [{e.severity:<8}] {e.title}  ({e.window.start} → {e.window.end}, {e.detector})")


def cmd_reindex(args: argparse.Namespace) -> None:
    from app.llm.rag import reindex

    stats = reindex()
    print("RAG indeksi yeniden kuruldu:")
    for k, v in stats.items():
        print(f"  {k}: {v}")


def cmd_export_openapi(args: argparse.Namespace) -> None:
    from app.main import create_docs_app

    app = create_docs_app()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(app.openapi(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"OpenAPI şeması yazıldı: {out}")


def cmd_convert_ast(args: argparse.Namespace) -> None:
    """AST görev verisi (data/raw/ast) → panel biçiminde ayrı dosya (DATASET_PATH ile seçilir)."""
    from collections import Counter

    from app.personal.ast_convert import convert, write

    doc = convert(Path(args.source), args.first_day, args.last_day)
    out = Path(args.out)
    write(doc, out)
    recs = doc["records"]
    by_status = Counter((r["astronaut_id"], r["health_status"]) for r in recs)
    print(f"Yazıldı: {out}  ({len(doc['astronauts'])} astronot × {len(recs) // len(doc['astronauts'])} gün, "
          f"görev günü {args.first_day}–{args.last_day})")
    for a in doc["astronauts"]:
        aid = a["astronaut_id"]
        print(f"  {aid}: Normal {by_status[(aid, 0)]} · Dikkat {by_status[(aid, 1)]} · Rahatsız {by_status[(aid, 2)]} gün")
    print(f"  ölçülen {len(recs[0]['levels'])} ölçüm; bu veri setinde olmayan {len(doc['dataset']['absent'])}; skor yok")
    try:  # .env'de göreli yol repo köküne göre çözülür
        shown = out.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        shown = out.as_posix()
    print(f"Kullanmak için backend/.env:  DATASET_PATH={shown}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m app.cli", description="Astronaut Health Monitor CLI")
    sub = p.add_subparsers(dest="command", required=True)

    c = sub.add_parser("convert-ast", help="AST görev verisini (data/raw/ast) panel biçimine çevir")
    c.add_argument("--source", default=str(REPO_ROOT / "data" / "raw" / "ast"), help="payloads_tr_… ve payloads_… dosyalarının klasörü")
    c.add_argument("--out", default=str(REPO_ROOT / "data" / "raw" / "astronaut_health_ast.json"))
    c.add_argument("--first-day", type=int, default=149, help="Pencerenin ilk görev günü")
    c.add_argument("--last-day", type=int, default=178, help="Pencerenin son görev günü (panelde 'bugün')")
    c.set_defaults(func=cmd_convert_ast)

    z = sub.add_parser("reset", help="Bu istasyonun (STATION_ROLE) veritabanını sıfırla")
    z.set_defaults(func=cmd_reset)

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

    a = sub.add_parser("analyze", help="Ekip durumunu ve aktif olayları konsola yaz")
    a.add_argument("--as-of", default=None, help="YYYY-MM-DD (boş → son gün)")
    a.add_argument("--all", action="store_true", help="info olayları da göster")
    a.set_defaults(func=cmd_analyze)

    r = sub.add_parser("reindex", help="data/docs altındaki belgeleri yeniden indeksle (RAG)")
    r.set_defaults(func=cmd_reindex)

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
