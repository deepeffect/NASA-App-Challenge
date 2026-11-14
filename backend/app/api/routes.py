"""REST API route'ları. Route'lar ince tutulur; iş mantığı services/ altındadır.

(a) adımı: tüm endpoint'ler stub servise bağlı (sözleşme önce).
"""

import json
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sse_starlette.sse import EventSourceResponse

from app.analysis.catalog import load_catalog
from app.models.schemas import (
    AlertListResponse,
    AstronautSummary,
    BriefingResponse,
    CatalogResponse,
    ChatRequest,
    CheckinListResponse,
    CheckinRequest,
    CheckinResponse,
    CrewResponse,
    ErrorResponse,
    EventSource,
    ExplainRequest,
    ExplainResponse,
    FeedbackRequest,
    FeedbackResponse,
    GroundReport,
    HealthEvent,
    HealthResponse,
    HealthSystem,
    IngestReport,
    Lang,
    MetricSeriesResponse,
    Severity,
    ShareRequest,
    ShareResponse,
)
from app.services import health as health_svc
from app.services import stub as svc

router = APIRouter()

AsOf = Annotated[
    date | None,
    Query(description="Zaman kaydırıcısı: bu güne kadarki veriyle hesapla (YYYY-MM-DD). Boş → verideki son gün."),
]
NOT_FOUND = {404: {"model": ErrorResponse}}


class SSEResponseDoc(Response):
    """Sadece OpenAPI dokümantasyonu için: text/event-stream."""

    media_type = "text/event-stream"


def _require_astronaut(aid: str) -> None:
    if not svc.known_astronaut(aid):
        raise HTTPException(status_code=404, detail=f"Astronot bulunamadı: {aid}")


def _require_metric(metric: str) -> None:
    if load_catalog().get(metric) is None:
        raise HTTPException(status_code=404, detail=f"Bilinmeyen metrik: {metric}")


# ============================================================================ sistem
@router.get("/health", response_model=HealthResponse, tags=["system"], summary="Sistem durumu (DB, LLM, RAG)")
def get_health() -> HealthResponse:
    return health_svc.health()


@router.get("/metrics/catalog", response_model=CatalogResponse, tags=["system"], summary="Metrik kataloğu")
def get_catalog() -> CatalogResponse:
    cat = load_catalog()
    return CatalogResponse(systems=cat.system_infos(), metrics=[m.to_info() for m in cat.metrics.values()])


# ============================================================================ mürettebat
@router.get("/crew", response_model=CrewResponse, tags=["crew"], summary="Tüm astronotlar + genel durum")
def get_crew(as_of: AsOf = None) -> CrewResponse:
    return svc.crew(as_of)


@router.get(
    "/astronauts/{astronaut_id}/summary",
    response_model=AstronautSummary,
    responses=NOT_FOUND,
    tags=["astronauts"],
    summary="Sistem skorları, son değerler, aktif olaylar",
)
def get_summary(astronaut_id: str, as_of: AsOf = None) -> AstronautSummary:
    _require_astronaut(astronaut_id)
    return svc.summary(astronaut_id, as_of)


@router.get(
    "/astronauts/{astronaut_id}/metrics",
    response_model=MetricSeriesResponse,
    responses=NOT_FOUND,
    tags=["astronauts"],
    summary="Metrik zaman serisi + baseline + eşikler + ilgili olaylar",
)
def get_metric_series(
    astronaut_id: str,
    metric: Annotated[str, Query(description="Katalogdaki metrik adı, örn. sleep_duration")],
    days: Annotated[int, Query(ge=1, le=400, description="as_of'tan geriye kaç gün")] = 30,
    resolution: Annotated[Literal["daily", "raw"], Query(description="raw → ham (saatlik) noktalar da döner")] = "daily",
    as_of: AsOf = None,
) -> MetricSeriesResponse:
    _require_astronaut(astronaut_id)
    _require_metric(metric)
    return svc.metric_series(astronaut_id, metric, days, as_of, resolution)


@router.get(
    "/astronauts/{astronaut_id}/checkins",
    response_model=CheckinListResponse,
    responses=NOT_FOUND,
    tags=["checkin"],
    summary="Check-in geçmişi (yeniden eskiye)",
)
def get_checkins(
    astronaut_id: str,
    days: Annotated[int, Query(ge=1, le=400)] = 14,
    as_of: AsOf = None,
) -> CheckinListResponse:
    _require_astronaut(astronaut_id)
    return svc.checkins(astronaut_id, days, as_of)


@router.get(
    "/astronauts/{astronaut_id}/briefing",
    response_model=BriefingResponse,
    responses=NOT_FOUND,
    tags=["llm"],
    summary="Günlük LLM brifingi (LLM yoksa kural tabanlı şablon)",
)
async def get_briefing(
    astronaut_id: str,
    as_of: AsOf = None,
    lang: Lang = "tr",
    refresh: Annotated[bool, Query(description="true → cache'i atla")] = False,
) -> BriefingResponse:
    _require_astronaut(astronaut_id)
    return svc.briefing(astronaut_id, as_of, lang)


# ============================================================================ olaylar
@router.get("/alerts", response_model=AlertListResponse, tags=["alerts"], summary="Olay/uyarı listesi")
def list_alerts(
    astronaut_id: str | None = None,
    severity: Annotated[list[Severity] | None, Query(description="Tam eşleşme; tekrarlanabilir")] = None,
    min_severity: Annotated[Severity | None, Query(description="Bu seviye ve üstü")] = None,
    system: HealthSystem | None = None,
    source: EventSource | None = None,
    metric: str | None = None,
    status: Literal["active", "resolved", "all"] = "active",
    as_of: AsOf = None,
) -> AlertListResponse:
    if astronaut_id:
        _require_astronaut(astronaut_id)
    return svc.alerts(
        astronaut_id=astronaut_id, severity=severity, min_severity=min_severity, system=system,
        source=source, metric=metric, status=status, as_of=as_of,
    )


def _event_or_404(event_id: str, as_of: date | None) -> HealthEvent:
    ev = svc.find_event(event_id, as_of)
    if ev is None:
        raise HTTPException(status_code=404, detail=f"Olay bulunamadı: {event_id}")
    return ev


@router.get("/alerts/{event_id}", response_model=HealthEvent, responses=NOT_FOUND, tags=["alerts"], summary="Tek olay")
def get_alert(event_id: str, as_of: AsOf = None) -> HealthEvent:
    return _event_or_404(event_id, as_of)


@router.post(
    "/alerts/{event_id}/explain",
    response_model=ExplainResponse,
    responses=NOT_FOUND,
    tags=["llm"],
    summary="Olayın LLM açıklaması (AlertExplanation)",
)
async def explain_alert(event_id: str, body: ExplainRequest | None = None) -> ExplainResponse:
    req = body or ExplainRequest()
    return svc.explain(_event_or_404(event_id, req.as_of), req)


@router.post(
    "/alerts/{event_id}/feedback",
    response_model=FeedbackResponse,
    responses=NOT_FOUND,
    tags=["alerts"],
    summary="'Yanlış alarm' / 'Faydalı' geri bildirimi",
)
def post_feedback(event_id: str, body: FeedbackRequest, as_of: AsOf = None) -> FeedbackResponse:
    _event_or_404(event_id, as_of)
    return svc.feedback(event_id, body)


@router.put(
    "/alerts/{event_id}/share",
    response_model=ShareResponse,
    responses=NOT_FOUND,
    tags=["alerts"],
    summary="Olayı yer ekibiyle paylaş / paylaşımı kaldır",
)
def put_share(event_id: str, body: ShareRequest, as_of: AsOf = None) -> ShareResponse:
    _event_or_404(event_id, as_of)
    return svc.share(event_id, body)


# ============================================================================ check-in
@router.post(
    "/checkin",
    response_model=CheckinResponse,
    status_code=201,
    responses=NOT_FOUND,
    tags=["checkin"],
    summary="Günlük öz bildirim (not acil belirti için taranır)",
)
def post_checkin(body: CheckinRequest) -> CheckinResponse:
    _require_astronaut(body.astronaut_id)
    return svc.checkin(body)


# ============================================================================ sohbet
@router.post(
    "/chat",
    tags=["llm"],
    summary="Streaming sohbet (SSE)",
    response_class=SSEResponseDoc,
    responses={
        200: {
            "description": (
                "text/event-stream. Her olay `event: <ad>` + `data: <json>` satırlarıdır. "
                "Olay adları ve payload şemaları: meta→SSEMeta, token→SSEToken, thinking→SSEThinking, "
                "tool_call→SSEToolCall, tool_result→SSEToolResult, emergency→EmergencyNotice, "
                "done→SSEDone, error→SSEError. Tarayıcıda EventSource POST desteklemez: "
                "@microsoft/fetch-event-source kullanın."
            ),
            "content": {"text/event-stream": {"schema": {"type": "string"}}},
        },
        404: {"model": ErrorResponse},
    },
)
async def post_chat(body: ChatRequest) -> EventSourceResponse:
    _require_astronaut(body.astronaut_id)

    async def gen():
        async for name, payload in svc.chat_stream(body):
            yield {"event": name, "data": json.dumps(payload.model_dump(mode="json"), ensure_ascii=False)}

    return EventSourceResponse(gen(), ping=15)


# ============================================================================ veri yükleme
@router.post(
    "/ingest",
    response_model=IngestReport,
    tags=["ingest"],
    summary="CSV/JSON veri yükleme (format otomatik algılanır)",
)
async def post_ingest(
    file: Annotated[UploadFile, File(description="CSV veya JSON dosyası")],
    adapter: Annotated[str | None, Query(description="Adaptörü zorla: long_csv | wide_csv | json_records")] = None,
    astronaut_id: Annotated[str | None, Query(description="Dosyada astronaut_id kolonu yoksa kullanılır")] = None,
) -> IngestReport:
    content = await file.read()
    return svc.ingest(file.filename or "upload", content)


# ============================================================================ yer raporu
@router.get(
    "/ground-report",
    response_model=GroundReport,
    tags=["crew"],
    summary="Yer ekibi raporu (sadece paylaşılan check-in ve olaylar)",
)
def get_ground_report(
    as_of: AsOf = None,
    days: Annotated[int, Query(ge=1, le=60)] = 7,
) -> GroundReport:
    return svc.ground_report(as_of, days)
