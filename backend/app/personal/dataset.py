"""astronaut_health veri seti: ortak model + adaptörler.

Adaptör, ham JSON'u ortak `Dataset` modeline çevirir. Şu an iki format tanınır:
  - `reconstructed`: data/raw/astronaut_health.json (scripts/extract_dataset_from_artifact.py çıktısı;
    orijinal bulunana kadar bağlayıcı şema)
  - `prototype_embedded`: prototipin gömülü `<script id="data">` formatı (sütun dizili, indeksli)
Orijinal veri seti gelince buraya yeni bir adaptör eklenir ve aynı sonucu verdiği test edilir.

Durum, ana endişe, ground flag, self-care kodları ve skorlar VERİDEN okunur (yeniden hesaplanmaz).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.personal.catalog import PersonalCatalog, load_personal_catalog


class DatasetError(ValueError):
    """Veri seti okunamadı veya katalogla uyumsuz."""


class AstronautMeta(BaseModel):
    id: str
    age: int
    sex: str
    bmi: float
    mission: str
    profile: str


class DayData(BaseModel):
    mission_day: int
    values: dict[str, float]
    area_scores: dict[str, float]
    daily_score: float
    cumulative_score: float
    health_status: int = Field(ge=0, le=2)
    main_concern: str
    self_care: list[str] = Field(description="Self-care kodları, veri setindeki (öncelik) sırasıyla")
    needs_ground_support: bool


class AstronautSeries(BaseModel):
    meta: AstronautMeta
    days: list[DayData] = Field(min_length=1, description="mission_day'e göre sıralı; son eleman = bugün")

    @model_validator(mode="after")
    def _sorted_unique(self) -> AstronautSeries:
        md = [d.mission_day for d in self.days]
        if md != sorted(set(md)):
            raise ValueError(f"{self.meta.id}: görev günleri sıralı ve tekil olmalı")
        return self

    @property
    def today_index(self) -> int:
        return len(self.days) - 1


class Dataset(BaseModel):
    adapter: str
    fingerprint: str = Field(description="Kaynak dosyanın sha256'sı (değişince yeniden yüklenir)")
    astronauts: list[AstronautSeries]

    def by_id(self) -> dict[str, AstronautSeries]:
        return {a.meta.id: a for a in self.astronauts}


# ============================================================================ adaptörler
Adapter = tuple[str, Callable[[Any], bool], Callable[[Any, PersonalCatalog], list[AstronautSeries]]]


def _is_reconstructed(raw: Any) -> bool:
    return isinstance(raw, dict) and isinstance(raw.get("records"), list) and isinstance(raw.get("astronauts"), list)


def _parse_reconstructed(raw: dict, cat: PersonalCatalog) -> list[AstronautSeries]:
    by_id: dict[str, list[dict]] = {}
    for r in raw["records"]:
        by_id.setdefault(r["astronaut_id"], []).append(r)
    out = []
    for a in raw["astronauts"]:
        aid = a["astronaut_id"]
        recs = sorted(by_id.get(aid, []), key=lambda r: r["mission_day"])
        days = [
            DayData(
                mission_day=r["mission_day"],
                values={c: r[c] for c in cat.columns},
                area_scores={k: r[f"{k}_score"] for k in cat.areas},
                daily_score=r["daily_health_score"],
                cumulative_score=r["cumulative_health_score"],
                health_status=r["health_status"],
                main_concern=r["main_concern"],
                self_care=list(r["self_care_actions"]),
                needs_ground_support=bool(r["needs_ground_support"]),
            )
            for r in recs
        ]
        meta = AstronautMeta(id=aid, **{k: a[k] for k in ("age", "sex", "bmi", "mission", "profile")})
        out.append(AstronautSeries(meta=meta, days=days))
    return out


def _is_prototype_embedded(raw: Any) -> bool:
    return (
        isinstance(raw, dict)
        and {"indicators", "solutions", "astronauts"} <= raw.keys()
        and bool(raw["astronauts"])
        and "v" in raw["astronauts"][0]
    )


def _parse_prototype_embedded(raw: dict, cat: PersonalCatalog) -> list[AstronautSeries]:
    codes = [s["code"] for s in raw["solutions"]]
    out = []
    for a in raw["astronauts"]:
        days = [
            DayData(
                mission_day=md,
                values={c: a["v"][c][i] for c in cat.columns},
                area_scores={k: a["score"][k][i] for k in cat.areas},
                daily_score=a["daily"][i],
                cumulative_score=a["cum"][i],
                health_status=a["status"][i],
                main_concern=a["concern"][i],
                self_care=[codes[k] for k in a["act"][i]],
                needs_ground_support=bool(a["ground"][i]),
            )
            for i, md in enumerate(a["days"])
        ]
        meta = AstronautMeta(id=a["id"], **{k: a[k] for k in ("age", "sex", "bmi", "mission", "profile")})
        out.append(AstronautSeries(meta=meta, days=days))
    return out


ADAPTERS: list[Adapter] = [
    ("reconstructed", _is_reconstructed, _parse_reconstructed),
    ("prototype_embedded", _is_prototype_embedded, _parse_prototype_embedded),
]


def _validate(series: list[AstronautSeries], cat: PersonalCatalog) -> None:
    codes = {s.code for s in cat.solutions}
    concerns = {"none", *cat.areas}
    seen: set[str] = set()
    for a in series:
        if a.meta.id in seen:
            raise DatasetError(f"Aynı astronot iki kez: {a.meta.id}")
        seen.add(a.meta.id)
        if a.meta.mission not in cat.missions or a.meta.profile not in cat.profiles:
            raise DatasetError(f"{a.meta.id}: katalogda olmayan görev/profil ({a.meta.mission}, {a.meta.profile})")
        for d in a.days:
            unknown = [c for c in d.self_care if c not in codes]
            if unknown:
                raise DatasetError(f"{a.meta.id} görev günü {d.mission_day}: bilinmeyen self-care kodu {unknown}")
            if d.main_concern not in concerns:
                raise DatasetError(f"{a.meta.id} görev günü {d.mission_day}: bilinmeyen ana endişe {d.main_concern}")


def parse_dataset(raw: Any, fingerprint: str = "", cat: PersonalCatalog | None = None) -> Dataset:
    cat = cat or load_personal_catalog()
    for name, can_handle, parse in ADAPTERS:
        if can_handle(raw):
            try:
                series = parse(raw, cat)
            except (KeyError, TypeError, ValueError) as e:
                raise DatasetError(f"{name} formatı okunamadı: {e!r}") from e
            _validate(series, cat)
            return Dataset(adapter=name, fingerprint=fingerprint, astronauts=series)
    raise DatasetError("Veri seti formatı tanınmadı (bilinen adaptörler: " + ", ".join(a[0] for a in ADAPTERS) + ")")


def file_fingerprint(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_dataset_file(path: Path, cat: PersonalCatalog | None = None) -> Dataset:
    if not path.exists():
        raise DatasetError(f"Veri seti bulunamadı: {path}")
    data = path.read_bytes()
    return parse_dataset(json.loads(data), hashlib.sha256(data).hexdigest(), cat)
