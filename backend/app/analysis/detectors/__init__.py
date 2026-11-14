"""Olay dedektörleri. Modülleri import etmek kayıt (register) işlemini tetikler."""

from app.analysis.detectors import examples, pattern, rules  # noqa: F401
from app.analysis.detectors.base import DETECTOR_REGISTRY, EventDetector, build_detectors, register_detector

__all__ = ["DETECTOR_REGISTRY", "EventDetector", "build_detectors", "register_detector"]
