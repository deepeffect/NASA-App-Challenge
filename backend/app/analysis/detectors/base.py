"""Olay dedektörü arayüzü ve registry.

Kural tabanlı dedektörler ve ML dedektörleri AYNI arayüzü uygular ve AYNI şemada
(HealthEvent) olay üretir. Yeni dedektör eklemek için:

    from app.analysis.detectors.base import register_detector

    @register_detector("iforest")
    class IsolationForestDetector:
        name = "ml.isolation_forest"          # HealthEvent.detector alanına yazılır
        def detect(self, ctx: AnalysisContext) -> list[HealthEvent]:
            ...                                # source="anomaly", event_id=make_event_id(...)

Sonra `.env`: ANALYSIS_DETECTORS=threshold,baseline_deviation,trend,iforest,system_pattern
Dedektörler listedeki sırayla çalışır; her biri `ctx.events` ile öncekilerin ürettiklerini görür.
"""

from collections.abc import Callable
from typing import Protocol, runtime_checkable

from app.analysis.context import AnalysisContext
from app.models.schemas import HealthEvent


@runtime_checkable
class EventDetector(Protocol):
    name: str

    def detect(self, ctx: AnalysisContext) -> list[HealthEvent]: ...


DETECTOR_REGISTRY: dict[str, type] = {}


def register_detector(key: str) -> Callable[[type], type]:
    def deco(cls: type) -> type:
        DETECTOR_REGISTRY[key] = cls
        return cls

    return deco


def build_detectors(keys: list[str]) -> list[EventDetector]:
    unknown = [k for k in keys if k not in DETECTOR_REGISTRY]
    if unknown:
        raise ValueError(f"Bilinmeyen dedektör(ler): {unknown}. Kayıtlı: {sorted(DETECTOR_REGISTRY)}")
    return [DETECTOR_REGISTRY[k]() for k in keys]
