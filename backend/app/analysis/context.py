"""Dedektörlere verilen analiz bağlamı."""

from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from app.analysis.catalog import Catalog, MetricDef, RulesConfig
from app.analysis.features import SeriesFeatures
from app.models.schemas import HealthEvent


@dataclass
class AnalysisContext:
    as_of: date
    catalog: Catalog
    rules: RulesConfig
    astronaut_ids: list[str]
    features: dict[tuple[str, str], SeriesFeatures]
    raw: pd.DataFrame  # as_of'a kadar kesilmiş ham long veri (ML dedektörleri için)
    events: list[HealthEvent] = field(default_factory=list)  # önceki dedektörlerin ürettikleri

    def series(self, astronaut_id: str, metric: str) -> SeriesFeatures | None:
        return self.features.get((astronaut_id, metric))

    def iter_series(self, rule: str | None = None) -> Iterator[tuple[SeriesFeatures, MetricDef]]:
        """Kataloğu bilinen serileri dolaş; rule verilirse sadece o kuralın açık olduğu metrikler."""
        for (aid, metric), sf in sorted(self.features.items()):
            m = self.catalog.get(metric)
            if m is None or (rule is not None and rule not in m.rules):
                continue
            yield sf, m
