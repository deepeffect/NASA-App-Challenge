"""Dünya alıcısı (arka plan görevi): gemiden snapshot + SSE stream → earth.db.

Akış:
  1. Dönem (epoch) bilinmiyorsa GET /api/downlink/snapshot → bütün veri yazılır, last_seq = snapshot.seq
  2. GET /api/downlink/stream?since=last_seq → her olay işlenir (tekrar seq yok sayılır), heartbeat ile
     bağlantı durumu güncellenir
  3. Bağlantı koparsa bekleyip (1 → 30 sn) 2. adımdan, kaldığı seq'ten devam eder
  4. Olay veya heartbeat farklı bir dönem taşırsa (gemi DB'si sıfırlandı) 1. adıma döner
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx
from sqlalchemy.engine import Engine
from sqlmodel import Session

from app.config import Settings
from app.downlink import earth_store
from app.downlink.broadcast import Broadcaster
from app.models.schemas import DownlinkEvent, DownlinkHeartbeat, DownlinkSnapshot

log = logging.getLogger(__name__)


class EpochChanged(Exception):
    """Gemi dönemi değişti → snapshot ile baştan senkronize ol."""


async def iter_sse(lines: AsyncIterator[str]) -> AsyncIterator[dict[str, str]]:
    """SSE satırlarını olaylara çevirir: {"event", "id", "data"} (yorum satırları atlanır).

    Yarım kalan son olay (bağlantı ortasında koptu) teslim edilmez: olay ancak boş satırla biter.
    """
    ev: dict[str, Any] = {"data": []}
    async for raw in lines:
        line = raw.rstrip("\r")
        if line == "":
            if ev["data"] or "event" in ev:
                yield {"event": ev.get("event", "message"), "id": ev.get("id", ""), "data": "\n".join(ev["data"])}
            ev = {"data": []}
            continue
        if line.startswith(":"):
            continue
        field, _, value = line.partition(":")
        value = value[1:] if value.startswith(" ") else value
        if field == "data":
            ev["data"].append(value)
        elif field in ("event", "id"):
            ev[field] = value


class Receiver:
    def __init__(self, engine: Engine, settings: Settings, broadcaster: Broadcaster | None = None) -> None:
        self.engine = engine
        self.settings = settings
        self.broadcaster = broadcaster or Broadcaster()

    # ------------------------------------------------------------ yardımcılar
    def client(self, transport: httpx.AsyncBaseTransport | None = None) -> httpx.AsyncClient:
        s = self.settings
        return httpx.AsyncClient(
            base_url=(s.ship_url or "").rstrip("/"),
            headers={"Authorization": f"Bearer {s.earth_link_token or ''}"},
            timeout=httpx.Timeout(60.0, read=max(30.0, s.downlink_heartbeat_seconds * 6)),
            transport=transport,
        )

    def _link(self, **changes: Any) -> None:
        with Session(self.engine) as db:
            state = earth_store.update_link(db, **changes)
            db.commit()
        self.broadcaster.publish({"kind": "link", "link": state})

    def state(self) -> dict[str, Any]:
        with Session(self.engine) as db:
            return earth_store.link_state(db)

    # ------------------------------------------------------------ adımlar
    async def sync_snapshot(self, client: httpx.AsyncClient) -> DownlinkSnapshot:
        r = await client.get("/api/downlink/snapshot")
        r.raise_for_status()
        snap = DownlinkSnapshot.model_validate_json(r.content)
        with Session(self.engine) as db:
            earth_store.apply_snapshot(db, snap)
        log.info("Downlink snapshot alındı: dönem %s, seq %s, %s gün", snap.epoch, snap.seq, len(snap.days))
        self.broadcaster.publish({"kind": "snapshot", "seq": snap.seq})
        return snap

    def handle(self, raw: dict[str, str]) -> None:
        epoch = self.state()["epoch"]
        if raw["event"] == "link.heartbeat":
            hb = DownlinkHeartbeat.model_validate_json(raw["data"])
            if hb.epoch != epoch:
                raise EpochChanged(hb.epoch)
            with Session(self.engine) as db:
                earth_store.apply_heartbeat(db, hb)
            self.broadcaster.publish({"kind": "link", "link": self.state()})
            return
        ev = DownlinkEvent.model_validate(json.loads(raw["data"]))
        if ev.epoch != epoch:
            raise EpochChanged(ev.epoch)
        with Session(self.engine) as db:
            stored = earth_store.apply_event(db, ev)
        if stored is not None:
            self.broadcaster.publish(
                {
                    "kind": "event",
                    "type": stored.type,
                    "seq": stored.seq,
                    "astronaut_id": stored.astronaut_id,
                    "day_index": stored.day_index,
                    "ship_time": ev.ship_time.isoformat(),
                    "earth_received_time": stored.earth_received_time.isoformat(),
                }
            )

    async def consume(self, client: httpx.AsyncClient, follow: bool = True) -> None:
        """Tek bağlantı ömrü: gerekirse snapshot, sonra stream (koparsa istisna yükselir)."""
        if self.state()["epoch"] is None:
            await self.sync_snapshot(client)
        since = int(self.state()["last_seq"] or 0)
        params = {"since": since, "follow": "true" if follow else "false"}
        async with client.stream("GET", "/api/downlink/stream", params=params) as resp:
            resp.raise_for_status()
            self._link(connected=True, last_error=None)
            async for raw in iter_sse(resp.aiter_lines()):
                self.handle(raw)

    async def run_forever(self) -> None:
        backoff = 1.0
        self._link(connected=False)
        async with self.client() as client:
            while True:
                try:
                    await self.consume(client, follow=True)
                    backoff = 1.0  # sunucu akışı kapattı: hemen yeniden bağlan
                except asyncio.CancelledError:
                    raise
                except EpochChanged as e:
                    log.warning("Gemi dönemi değişti (%s): yeniden senkronize ediliyor", e)
                    self._link(epoch=None, connected=False)
                    continue
                except Exception as e:  # noqa: BLE001 — bağlantı hatası: bekle, kaldığın yerden devam et
                    log.info("Downlink bağlantısı yok: %s", e)
                    self._link(connected=False, last_error=f"{type(e).__name__}: {e}"[:300])
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, 30.0)
                    continue
                self._link(connected=False)
