"""Kişisel sağlık kataloğu: `config/catalog.yaml` (ölçümler, aralıklar, self-care çözümleri).

Dosya düzenlenince sunucuyu yeniden başlatmadan etkili olur (mtime ile önbellek).
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field, model_validator

from app.config import get_settings
from app.i18n import Lang

DOMAINS = ("exposure", "immune", "bone_muscle", "cardiovascular", "behavioral")


class Text(BaseModel):
    """İki dilli metin."""

    tr: str
    en: str

    def get(self, lang: Lang) -> str:
        return self.en if lang == "en" else self.tr


class TextList(BaseModel):
    tr: list[str]
    en: list[str]

    def get(self, lang: Lang) -> list[str]:
        return self.en if lang == "en" else self.tr


class Range(BaseModel):
    min: float
    max: float | None = Field(None, description="null → üst sınır yok")


class Indicator(BaseModel):
    col: str
    domain: str
    label: Text
    unit: Text
    dec: int = Field(ge=0, le=6)
    healthy: Range
    warning: Range
    action: str
    trig: int = Field(ge=1, le=2)
    private: bool = False
    # Öz bildirim ölçeğinin üst sınırı. Verilirse değer "3/5" biçiminde yazılır (veri seti ezebilir: DatasetInfo).
    scale_max: int | None = Field(None, ge=1)


class Solution(BaseModel):
    code: str
    domain: str
    title: Text
    when: Text
    do_yourself: TextList
    contact_ground_if: Text
    basis: Text


class PersonalCatalog(BaseModel):
    threshold_source: str
    verified: bool
    threshold_note: Text
    statuses: list[Text] = Field(min_length=3, max_length=3)
    domains: dict[str, Text]
    areas: list[str]
    missions: dict[str, Text]
    profiles: dict[str, Text]
    indicators: list[Indicator]
    solutions: list[Solution]

    @model_validator(mode="after")
    def _consistent(self) -> PersonalCatalog:
        if list(self.domains) != list(DOMAINS):
            raise ValueError(f"domains sırası {DOMAINS} olmalı")
        if any(a not in self.domains or a == "exposure" for a in self.areas):
            raise ValueError("areas sadece sağlık alanlarını içermeli")
        cols = [i.col for i in self.indicators]
        codes = [s.code for s in self.solutions]
        if len(set(cols)) != len(cols) or len(set(codes)) != len(codes):
            raise ValueError("ölçüm kolonları ve çözüm kodları tekil olmalı")
        for i in self.indicators:
            if i.domain not in self.domains:
                raise ValueError(f"{i.col}: bilinmeyen domain {i.domain}")
            if i.action not in codes:
                raise ValueError(f"{i.col}: bilinmeyen aksiyon {i.action}")
        return self

    # ---------------------------------------------------------------- yardımcılar
    @property
    def columns(self) -> list[str]:
        return [i.col for i in self.indicators]

    @property
    def private_columns(self) -> frozenset[str]:
        return frozenset(i.col for i in self.indicators if i.private)

    def indicator(self, col: str) -> Indicator | None:
        return next((i for i in self.indicators if i.col == col), None)

    def solution(self, code: str) -> Solution | None:
        return next((s for s in self.solutions if s.code == code), None)


_CACHE: dict[Path, tuple[float, PersonalCatalog]] = {}


def catalog_path() -> Path:
    return get_settings().config_dir / "catalog.yaml"


def load_personal_catalog(path: Path | None = None) -> PersonalCatalog:
    p = path or catalog_path()
    mtime = p.stat().st_mtime
    hit = _CACHE.get(p)
    if hit and hit[0] == mtime:
        return hit[1]
    cat = PersonalCatalog.model_validate(yaml.safe_load(p.read_text(encoding="utf-8")))
    _CACHE[p] = (mtime, cat)
    return cat
