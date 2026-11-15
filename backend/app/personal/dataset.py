"""astronaut_health veri seti: ortak model + adaptörler.

Adaptör, ham JSON'u ortak `Dataset` modeline çevirir. Şu an üç format tanınır:
  - `levels`: "astronaut_health+levels/1" (app/personal/ast_convert.py çıktısı). Seviye, normal metni ve
    yazılış VERİDEN gelir; ölçülmeyen kolonlar kayıtta yoktur; skor yoktur (bkz. `DatasetInfo`).
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
from typing import Any, Literal

from pydantic import BaseModel, Field, PrivateAttr, model_validator

from app.personal.catalog import Indicator, PersonalCatalog, Text, load_personal_catalog

FORMAT_LEVELS = "astronaut_health+levels/1"


class DatasetError(ValueError):
    """Veri seti okunamadı veya katalogla uyumsuz."""


class IndicatorOverride(BaseModel):
    """Veri setinin bir ölçümde kataloğu ezdiği alanlar (ad, birim, ondalık, ölçek)."""

    label: Text | None = None
    unit: Text | None = None
    dec: int | None = Field(None, ge=0, le=6)
    scale_max: int | None = Field(None, ge=1)


AbsentReason = Literal["not_measured", "not_in_file"]


class DatasetInfo(BaseModel):
    """Veri setine özgü kurallar. Varsayılanlar prototip veri setidir (sabit aralık, 3 günlük ortalama, skor var).

    Gemide veri dosyasından okunur ve istasyon DB'sinde saklanır; Dünya'ya downlink snapshot'ıyla gider.
    """

    levels_from_data: bool = Field(False, description="Seviye (0/1/2) kayıttan okunur; durum, ana endişe, öz bakım ve yer "
                                   "desteği bu seviyelerden türetilmiştir (Dünya'da sadece görünür ölçümlerden yeniden türetilir)")
    averaged: bool = Field(True, description="false → her ölçüm o günün değeridir (3 günlük ortalama alınmaz)")
    has_scores: bool = Field(True, description="false → alan skoru, günlük ve kümülatif skor yok")
    indicators: dict[str, IndicatorOverride] = Field(default_factory=dict)
    absent: dict[str, AbsentReason] = Field(default_factory=dict, description="Bu veri setinde olmayan katalog kolonları ve nedeni")
    source_note: Text | None = Field(None, description="Ekrandaki veri kaynağı satırı")
    readings_note: Text | None = None
    threshold_note: Text | None = None
    range_label: Text | None = Field(None, description="Ölçüm tablosundaki aralık sütununun başlığı")

    _effective: dict[str, Indicator] = PrivateAttr(default_factory=dict)

    def effective(self, ind: Indicator) -> Indicator:
        """Katalog ölçümü + bu veri setinin ezdiği alanlar (çoğu veri setinde ölçümün kendisi)."""
        ov = self.indicators.get(ind.col)
        if ov is None:
            return ind
        hit = self._effective.get(ind.col)
        if hit is None:
            update = {k: getattr(ov, k) for k in ("label", "unit", "dec", "scale_max") if getattr(ov, k) is not None}
            hit = self._effective[ind.col] = ind.model_copy(update=update)
        return hit


class AstronautMeta(BaseModel):
    id: str
    age: int | None = None
    sex: str | None = None
    bmi: float | None = None
    mission: str
    profile: str | None = None


class DayData(BaseModel):
    mission_day: int
    values: dict[str, float] = Field(description="Sadece o gün ÖLÇÜLEN kolonlar")
    area_scores: dict[str, float] = Field(default_factory=dict)
    daily_score: float | None = None
    cumulative_score: float | None = None
    health_status: int = Field(ge=0, le=2)
    main_concern: str
    self_care: list[str] = Field(description="Self-care kodları, veri setindeki (öncelik) sırasıyla")
    needs_ground_support: bool
    # --- sadece `levels_from_data` veri setlerinde ---
    levels: dict[str, int] | None = Field(None, description="kolon → 0/1/2 (veri setindeki işaret)")
    normal: dict[str, dict[str, str]] | None = Field(None, description="kolon → {tr, en}: verideki normal metni")
    display: dict[str, str] | None = Field(None, description="kolon → verideki yazılış (ör. '116/82')")


class AstronautSeries(BaseModel):
    meta: AstronautMeta
    days: list[DayData] = Field(min_length=1, description="mission_day'e göre sıralı; son eleman = bugün")
    info: DatasetInfo = Field(default_factory=DatasetInfo, description="Bu serinin veri setinin kuralları (ortak nesne)")

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
    info: DatasetInfo = Field(default_factory=DatasetInfo)

    def by_id(self) -> dict[str, AstronautSeries]:
        return {a.meta.id: a for a in self.astronauts}


# ============================================================================ adaptörler
Adapter = tuple[str, Callable[[Any], bool], Callable[[Any, PersonalCatalog], list[AstronautSeries]]]


def _is_levels(raw: Any) -> bool:
    return isinstance(raw, dict) and raw.get("format") == FORMAT_LEVELS


def _parse_levels(raw: dict, cat: PersonalCatalog) -> list[AstronautSeries]:
    """Seviyesi veriden gelen format: kayıtta olmayan kolon o gün ölçülmemiştir; skor alanı yoktur."""
    info = DatasetInfo.model_validate(raw.get("dataset") or {})
    by_id: dict[str, list[dict]] = {}
    for r in raw["records"]:
        by_id.setdefault(r["astronaut_id"], []).append(r)
    out = []
    for a in raw["astronauts"]:
        aid = a["astronaut_id"]
        days = [
            DayData(
                mission_day=r["mission_day"],
                values={c: float(r[c]) for c in cat.columns if r.get(c) is not None},
                health_status=r["health_status"],
                main_concern=r["main_concern"],
                self_care=list(r["self_care_actions"]),
                needs_ground_support=bool(r["needs_ground_support"]),
                levels=r.get("levels"),
                normal=r.get("normal"),
                display=r.get("display"),
            )
            for r in sorted(by_id.get(aid, []), key=lambda r: r["mission_day"])
        ]
        meta = AstronautMeta(id=aid, mission=a["mission"], **{k: a.get(k) for k in ("age", "sex", "bmi", "profile")})
        out.append(AstronautSeries(meta=meta, days=days, info=info))
    return out


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
    ("levels", _is_levels, _parse_levels),
    ("reconstructed", _is_reconstructed, _parse_reconstructed),
    ("prototype_embedded", _is_prototype_embedded, _parse_prototype_embedded),
]


def _validate(series: list[AstronautSeries], cat: PersonalCatalog) -> None:
    codes = {s.code for s in cat.solutions}
    concerns = {"none", *cat.areas}
    columns = set(cat.columns)
    seen: set[str] = set()
    for a in series:
        if a.meta.id in seen:
            raise DatasetError(f"Aynı astronot iki kez: {a.meta.id}")
        seen.add(a.meta.id)
        if a.meta.mission not in cat.missions or (a.meta.profile is not None and a.meta.profile not in cat.profiles):
            raise DatasetError(f"{a.meta.id}: katalogda olmayan görev/profil ({a.meta.mission}, {a.meta.profile})")
        info = a.info
        stray = [c for c in (*info.absent, *info.indicators) if c not in columns]
        if stray:
            raise DatasetError(f"Veri seti bilgisinde katalogda olmayan kolon: {stray}")
        for d in a.days:
            unknown = [c for c in d.self_care if c not in codes]
            if unknown:
                raise DatasetError(f"{a.meta.id} görev günü {d.mission_day}: bilinmeyen self-care kodu {unknown}")
            if d.main_concern not in concerns:
                raise DatasetError(f"{a.meta.id} görev günü {d.mission_day}: bilinmeyen ana endişe {d.main_concern}")
            # Sessiz boşluk olmaz: her katalog kolonu ya o gün ölçülmüştür ya da veri seti "yok" demiştir
            gaps = [c for c in cat.columns if (c in d.values) == (c in info.absent)]
            if gaps:
                raise DatasetError(f"{a.meta.id} görev günü {d.mission_day}: ölçüm ne var ne 'yok' işaretli (ya da ikisi birden): {gaps}")
            if info.has_scores and (d.daily_score is None or d.cumulative_score is None or set(d.area_scores) != set(cat.areas)):
                raise DatasetError(f"{a.meta.id} görev günü {d.mission_day}: skor alanları eksik")
            if info.levels_from_data:
                levels = d.levels or {}
                if set(levels) != set(d.values) or any(v not in (0, 1, 2) for v in levels.values()):
                    raise DatasetError(f"{a.meta.id} görev günü {d.mission_day}: seviyeler ölçülen kolonlarla aynı ve 0/1/2 olmalı")


def parse_dataset(raw: Any, fingerprint: str = "", cat: PersonalCatalog | None = None) -> Dataset:
    cat = cat or load_personal_catalog()
    for name, can_handle, parse in ADAPTERS:
        if can_handle(raw):
            try:
                series = parse(raw, cat)
            except (KeyError, TypeError, ValueError) as e:
                raise DatasetError(f"{name} formatı okunamadı: {e!r}") from e
            _validate(series, cat)
            info = series[0].info if series else DatasetInfo()
            return Dataset(adapter=name, fingerprint=fingerprint, astronauts=series, info=info)
    raise DatasetError("Veri seti formatı tanınmadı (bilinen adaptörler: " + ", ".join(a[0] for a in ADAPTERS) + ")")


def file_fingerprint(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_dataset_file(path: Path, cat: PersonalCatalog | None = None) -> Dataset:
    if not path.exists():
        raise DatasetError(f"Veri seti bulunamadı: {path}")
    data = path.read_bytes()
    return parse_dataset(json.loads(data), hashlib.sha256(data).hexdigest(), cat)
