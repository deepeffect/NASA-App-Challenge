"""Süreç içi yayıncı: Dünya alıcısı yeni olay aldıkça /api/stream/monitor dinleyicilerine iletir."""

from __future__ import annotations

import asyncio
from typing import Any


class Broadcaster:
    def __init__(self, maxsize: int = 256) -> None:
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()
        self._maxsize = maxsize

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(self._maxsize)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[dict[str, Any]]) -> None:
        self._subscribers.discard(q)

    def publish(self, item: dict[str, Any]) -> None:
        for q in list(self._subscribers):
            try:
                q.put_nowait(item)
            except asyncio.QueueFull:  # yavaş dinleyici: en eskiyi at
                q.get_nowait()
                q.put_nowait(item)

    @property
    def subscribers(self) -> int:
        return len(self._subscribers)
