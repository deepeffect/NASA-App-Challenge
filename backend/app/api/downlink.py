"""Gemi → Dünya downlink uçları. EARTH_LINK_TOKEN ile korunur (Dünya alıcısı kullanır, tarayıcı değil).

GET /api/downlink/snapshot          yayınlanmış durumun tamamı (gzip)
GET /api/downlink/stream?since=<n>  SSE: seq > n olan yayınlanmış olaylar + link.heartbeat
                                    follow=false → mevcut olayları verip kapanır (test / curl)
"""

from __future__ import annotations

import asyncio
import gzip
import hmac
import time
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Header, Query, Request
from fastapi.responses import Response, StreamingResponse
from sqlmodel import Session

from app.config import Settings
from app.downlink import outbox
from app.errors import ApiError
from app.i18n import LangDep, t
from app.models.schemas import DownlinkSnapshot, ErrorResponse
from app.station import station_settings

router = APIRouter(tags=["downlink"])
ERRORS = {401: {"model": ErrorResponse}, 503: {"model": ErrorResponse}}


def require_link(request: Request, lang: str, authorization: str | None, link_token: str | None) -> Settings:
    s = station_settings(request)
    if not s.earth_link_token:
        raise ApiError(503, "downlink_disabled", t("downlink_disabled", lang))  # type: ignore[arg-type]
    given = (authorization or "").removeprefix("Bearer ").strip() or (link_token or "")
    if not hmac.compare_digest(given.encode("utf-8"), s.earth_link_token.encode("utf-8")):
        raise ApiError(401, "link_token_invalid", t("link_token_invalid", lang))  # type: ignore[arg-type]
    return s


Auth = Annotated[str | None, Header(description="Bearer <EARTH_LINK_TOKEN>")]
LinkToken = Annotated[str | None, Query(description="Başlık gönderilemiyorsa EARTH_LINK_TOKEN")]


@router.get("/downlink/snapshot", response_model=DownlinkSnapshot, responses=ERRORS, summary="Yayınlanmış durumun tamamı")
def get_snapshot(
    request: Request, lang: LangDep, authorization: Auth = None, link_token: LinkToken = None
) -> Response:
    s = require_link(request, lang, authorization, link_token)
    with Session(request.app.state.engine) as db:
        snap = outbox.snapshot(db, s)
    body = snap.model_dump_json().encode("utf-8")
    if "gzip" in request.headers.get("accept-encoding", ""):
        return Response(gzip.compress(body, 5), media_type="application/json", headers={"Content-Encoding": "gzip"})
    return Response(body, media_type="application/json")


def _sse(event: str, data: str, event_id: int | None = None) -> str:
    head = f"id: {event_id}\n" if event_id is not None else ""
    return f"{head}event: {event}\ndata: {data}\n\n"


@router.get(
    "/downlink/stream",
    responses={**ERRORS, 200: {"content": {"text/event-stream": {}}}},
    summary="SSE olay akışı (since=<seq>), link.heartbeat ile",
)
async def get_stream(
    request: Request,
    lang: LangDep,
    since: Annotated[int, Query(ge=0, description="Bu seq'ten SONRAKİ olaylar")] = 0,
    follow: Annotated[bool, Query(description="false → mevcut olayları verip kapan")] = True,
    authorization: Auth = None,
    link_token: LinkToken = None,
    last_event_id: Annotated[str | None, Header()] = None,
) -> StreamingResponse:
    s = require_link(request, lang, authorization, link_token)
    if last_event_id and last_event_id.isdigit():
        since = max(since, int(last_event_id))
    engine = request.app.state.engine

    async def gen() -> AsyncIterator[str]:
        cursor = since
        next_beat = 0.0
        while True:
            with Session(engine) as db:
                epoch = outbox.ship_epoch(db)
                events = outbox.published_events(db, cursor)
                for ev in events:
                    cursor = ev.seq or cursor
                    yield _sse(ev.type, outbox.to_wire(ev, epoch, s).model_dump_json(), ev.seq)
                now = time.monotonic()
                if not follow or now >= next_beat:
                    yield _sse("link.heartbeat", outbox.heartbeat(db, s).model_dump_json())
                    next_beat = now + s.downlink_heartbeat_seconds
            if not follow:
                return
            if events:
                continue  # birikmiş olaylar varsa beklemeden devam
            if await request.is_disconnected():
                return
            await asyncio.sleep(s.downlink_poll_seconds)

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

