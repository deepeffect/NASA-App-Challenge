"""Günlük tetiklenme seviyelerini olay "epizotlarına" çevirme + deterministik olay ID'leri."""

import hashlib
from datetime import UTC, date, datetime, time

import numpy as np

LEVEL_TO_SEVERITY = {1: "info", 2: "warning", 3: "critical"}


def find_episodes(levels: np.ndarray, merge_gap: int) -> list[tuple[int, int]]:
    """levels > 0 olan ardışık günleri (aradaki boşluk ≤ merge_gap ise birleştirerek) (başlangıç, bitiş) indekslerine çevir."""
    hits = np.flatnonzero(np.asarray(levels) > 0)
    if hits.size == 0:
        return []
    episodes: list[tuple[int, int]] = []
    start = end = int(hits[0])
    for i in hits[1:]:
        i = int(i)
        if i - end - 1 <= merge_gap:
            end = i
        else:
            episodes.append((start, end))
            start = end = i
    episodes.append((start, end))
    return episodes


def make_event_id(astronaut_id: str, source: str, detector: str, key: str, start: date) -> str:
    """Deterministik olay ID'si. Aynı epizot zaman kaydırıcısında hep aynı ID'yi alır.

    key: metrik adı (tek metrikli olay) veya sistem adı (çok metrikli olay).
    """
    raw = f"{astronaut_id}|{source}|{detector}|{key}|{start.isoformat()}"
    return "evt_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def event_status(end: date, as_of: date, merge_gap: int) -> str:
    """Bitişinden sonra merge_gap gün daha 'active' kalır (histerezis: aç-kapa titremesini önler)."""
    return "active" if (as_of - end).days <= merge_gap else "resolved"


def day_start(d: date) -> datetime:
    return datetime.combine(d, time(0, 0), UTC)
