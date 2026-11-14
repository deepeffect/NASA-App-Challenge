"""Komut satırı araçları.

    python -m app.cli export-openapi     # docs/openapi.json üret
"""

import argparse
import json
import sys
from pathlib import Path

from app.config import REPO_ROOT


def cmd_export_openapi(args: argparse.Namespace) -> None:
    from app.main import app

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(app.openapi(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"OpenAPI şeması yazıldı: {out}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m app.cli", description="Astronaut Health Monitor CLI")
    sub = p.add_subparsers(dest="command", required=True)

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
