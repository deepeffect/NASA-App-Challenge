"""Metrik kataloğu (metrics.yaml) ve kural parametreleri (rules.yaml) yükleyicisi."""

import re
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

from app.config import get_settings
from app.models.schemas import (
    Direction,
    Frequency,
    HealthSystem,
    MetricInfo,
    SystemInfo,
    Thresholds,
    ValueRange,
)

ALL_RULES = ["threshold", "baseline_deviation", "trend"]


class ThresholdDef(BaseModel):
    verified: bool = False
    source: str = "placeholder"
    warning: ValueRange | None = None
    critical: ValueRange | None = None


class MetricDef(BaseModel):
    name: str
    display_name: dict[str, str]
    unit: str
    system: HealthSystem
    frequency: Frequency = "daily"
    bad_direction: Direction
    aggregation: Literal["mean", "sum", "last", "max", "min"] = "mean"
    min_std: float = 1e-6
    decimals: int = 1
    aliases: list[str] = []
    normal_range: ValueRange | None = None
    thresholds: ThresholdDef | None = None
    rules: list[str] = Field(default_factory=lambda: list(ALL_RULES))

    @property
    def threshold_verified(self) -> bool:
        return bool(self.thresholds and self.thresholds.verified)

    @property
    def has_thresholds(self) -> bool:
        t = self.thresholds
        return bool(t and (t.warning or t.critical))

    def label(self, lang: str = "tr") -> str:
        return self.display_name.get(lang) or self.display_name.get("tr") or self.name

    def to_info(self) -> MetricInfo:
        return MetricInfo(
            name=self.name,
            display_name=self.label("tr"),
            display_name_en=self.label("en"),
            unit=self.unit,
            system=self.system,
            frequency=self.frequency,
            bad_direction=self.bad_direction,
            aggregation=self.aggregation,
            normal_range=self.normal_range,
            thresholds=Thresholds(**self.thresholds.model_dump()) if self.thresholds else None,
            threshold_verified=self.threshold_verified,
            rules=self.rules,
            decimals=self.decimals,
        )


class Catalog(BaseModel):
    systems: dict[str, dict[str, str]]
    metrics: dict[str, MetricDef]

    def get(self, name: str) -> MetricDef | None:
        return self.metrics.get(name)

    def resolve(self, name_or_alias: str) -> MetricDef | None:
        """Metrik adını veya takma adını (büyük/küçük harf, boşluk, tire duyarsız) çöz."""
        key = normalize_key(name_or_alias)
        if key in self.metrics:
            return self.metrics[key]
        return self._alias_map().get(key)

    def _alias_map(self) -> dict[str, MetricDef]:
        out: dict[str, MetricDef] = {}
        for m in self.metrics.values():
            for a in m.aliases:
                out[normalize_key(a)] = m
        return out

    def metrics_for_system(self, system: str) -> list[MetricDef]:
        return [m for m in self.metrics.values() if m.system == system]

    def system_label(self, system: str, lang: str = "tr") -> str:
        return self.systems.get(system, {}).get(lang, system)

    def system_infos(self) -> list[SystemInfo]:
        return [
            SystemInfo(
                id=sid,  # type: ignore[arg-type]
                display_name=labels.get("tr", sid),
                display_name_en=labels.get("en", sid),
                metrics=[m.name for m in self.metrics_for_system(sid)],
            )
            for sid, labels in self.systems.items()
        ]


def normalize_key(s: str) -> str:
    return re.sub(r"[\s\-./]+", "_", s.strip().lower())


# ----------------------------------------------------------------------------- rules.yaml
class BaselineCfg(BaseModel):
    days: int = 14
    min_days: int = 7


class DeviationCfg(BaseModel):
    z_info: float = 1.5
    z_warning: float = 2.0
    z_critical: float = 3.5


class TrendCfg(BaseModel):
    min_consecutive_days: int = 3
    info_change_std: float = 1.0
    warning_change_std: float = 2.0


class EpisodeCfg(BaseModel):
    merge_gap_days: int = 2


class PatternCfg(BaseModel):
    min_metrics: int = 2
    min_severity: Literal["info", "warning", "critical"] = "warning"


class ScoringCfg(BaseModel):
    penalties: dict[str, float] = {"critical": 45, "warning": 20, "info": 3}
    green_min: float = 80
    yellow_min: float = 50
    critical_forces_red: bool = True
    warning_forces_yellow: bool = True


class RulesConfig(BaseModel):
    baseline: BaselineCfg = BaselineCfg()
    window_days: int = 7
    min_periods: int = 4
    deviation: DeviationCfg = DeviationCfg()
    trend: TrendCfg = TrendCfg()
    episodes: EpisodeCfg = EpisodeCfg()
    pattern: PatternCfg = PatternCfg()
    scoring: ScoringCfg = ScoringCfg()


# ----------------------------------------------------------------------------- yükleyiciler
def _read_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


@lru_cache(maxsize=8)
def _load_catalog_cached(path: str, mtime: float) -> Catalog:
    raw = _read_yaml(Path(path))
    metrics = {name: MetricDef(name=name, **spec) for name, spec in (raw.get("metrics") or {}).items()}
    return Catalog(systems=raw.get("systems") or {}, metrics=metrics)


@lru_cache(maxsize=8)
def _load_rules_cached(path: str, mtime: float) -> RulesConfig:
    return RulesConfig(**_read_yaml(Path(path)))


def load_catalog(path: Path | None = None) -> Catalog:
    p = path or get_settings().config_dir / "metrics.yaml"
    return _load_catalog_cached(str(p), p.stat().st_mtime)


def load_rules(path: Path | None = None) -> RulesConfig:
    p = path or get_settings().config_dir / "rules.yaml"
    return _load_rules_cached(str(p), p.stat().st_mtime)
