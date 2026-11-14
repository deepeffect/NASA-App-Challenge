"""'Asistana sor' (gemi, astronaut_health): POST /api/chat — SSE. Astronot token'dan gelir."""

import json

from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

from app.auth import AstronautDep, ensure_own
from app.errors import ApiError
from app.i18n import resolve_lang
from app.llm.lang import detect_lang
from app.models.schemas import ChatRequest, ErrorResponse
from app.personal.store import personal_data
from app.services import personal_chat
from app.services.personal import get_series
from app.station import station_settings

router = APIRouter(tags=["assistant"])


def _client(request: Request):  # noqa: ANN202
    """İstemci uygulama başına önbelleklenir (auto tool modu kararı istekler arasında kalsın)."""
    client = getattr(request.app.state, "llm_client", None)
    if client is None:
        from app.llm.client import get_llm_client

        client = request.app.state.llm_client = get_llm_client(station_settings(request))
    return client


@router.post(
    "/chat",
    summary="'Asistana sor': streaming sohbet (SSE), sadece kendi verinizle",
    responses={
        200: {
            "description": "text/event-stream: meta, token, thinking, tool_call, tool_result, emergency, done, error",
            "content": {"text/event-stream": {"schema": {"type": "string"}}},
        },
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
    },
)
async def post_chat(body: ChatRequest, p: AstronautDep, request: Request) -> EventSourceResponse:
    explicit = body.lang or request.query_params.get("lang")
    header = request.headers.get("accept-language")
    lang = resolve_lang(explicit, header) if (explicit or header) else detect_lang(body.messages[-1].content)
    if body.astronaut_id:
        ensure_own(p, body.astronaut_id, lang)
    engine = request.app.state.engine
    from sqlmodel import Session

    with Session(engine) as db:
        series = get_series(personal_data(engine), db, p.subject, lang)
    settings = station_settings(request)
    client = _client(request)

    async def gen():
        try:
            async for name, payload in personal_chat.chat_stream(engine, settings, client, series, body, lang):
                yield {"event": name, "data": json.dumps(payload.model_dump(mode="json"), ensure_ascii=False)}
        except ApiError as e:  # akış başladıktan sonra
            yield {"event": "error", "data": json.dumps({"code": e.code, "message": e.detail}, ensure_ascii=False)}

    return EventSourceResponse(gen(), ping=15)
