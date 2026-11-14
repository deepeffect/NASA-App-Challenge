"""Testler için: referans prototipin gömülü verisi ve yolu."""

import json
import re
from functools import lru_cache
from pathlib import Path

from app.config import REPO_ROOT

PROTOTYPE_HTML = REPO_ROOT / "frontend" / "reference" / "personal-artifact.html"
_DATA_RE = re.compile(r'<script type="application/json" id="data">(.*?)</script>', re.S)


@lru_cache
def embedded_data(path: Path = PROTOTYPE_HTML) -> dict:
    return json.loads(_DATA_RE.search(path.read_text(encoding="utf-8")).group(1))
