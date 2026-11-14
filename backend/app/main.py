"""FastAPI uygulaması.

Çalıştırma (backend/ içinde):  uvicorn app.main:app --reload
Dokümantasyon:                 http://localhost:8000/docs
"""

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi

from app import __version__
from app.api import router as legacy_router
from app.api.assistant import router as assistant_router
from app.api.auth import router as auth_router
from app.api.checkin import router as checkin_router
from app.api.downlink import router as downlink_router
from app.api.monitor import router as monitor_router
from app.api.personal import public_router as catalog_router
from app.api.personal import router as personal_router
from app.api.station import router as station_router
from app.config import Settings, get_settings
from app.db import engine_for, init_db
from app.models.schemas import SSE_MODELS
from app.errors import ApiError, api_error_handler, http_error_handler, validation_error_handler
from app.i18n import lang_middleware
from app.station import earth_read_only_middleware

DESCRIPTION = """
Astronot sağlık izleme sistemi — tamamen offline/gemide çalışır.

**Mimari ilke:** Sayısal analizi LLM yapmaz. Analiz motoru (Python) baseline, trend,
anomali, skor ve uyarıları üretir; LLM sadece yorumlar. Kural tabanlı uyarılar LLM
kapalıyken de çalışır.

Zaman kaydırıcısı: çoğu GET endpoint'i `as_of=YYYY-MM-DD` alır.

**İstasyonlar:** aynı kod iki rolde çalışır (`STATION_ROLE`). `ship` (gemi) bütün veriyi tutar ve
astronot ekranını (`/me`) servis eder; `earth` (Dünya üssü) gemiden downlink ile gelen paylaşılabilir
veriyi tutar, `/monitor` ekranını servis eder ve salt okunurdur.
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: Settings = app.state.settings
    init_db(app.state.engine)
    if settings.station_role == "ship" and settings.data_source == "astronaut_health":
        from app.personal.store import ensure_dataset_loaded

        ensure_dataset_loaded(app.state.engine, settings)
    task: asyncio.Task | None = None
    if settings.station_role == "earth":
        from app.downlink.broadcast import Broadcaster
        from app.downlink.receiver import Receiver

        app.state.broadcaster = Broadcaster()
        if settings.ship_url and settings.earth_link_token:
            app.state.receiver = Receiver(app.state.engine, settings, app.state.broadcaster)
            task = asyncio.create_task(app.state.receiver.run_forever(), name="downlink-receiver")
        else:
            logging.getLogger(__name__).warning("Dünya üssü: SHIP_URL veya EARTH_LINK_TOKEN yok, downlink alıcısı çalışmıyor")
    yield
    if task is not None:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task


def _custom_openapi(app: FastAPI):
    """SSE olay modellerini de components/schemas'a ekler (frontend tip üretimi için)."""

    def openapi() -> dict:
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(title=app.title, version=app.version, description=app.description, routes=app.routes)
        comps = schema.setdefault("components", {}).setdefault("schemas", {})
        for model in SSE_MODELS.values():
            js = model.model_json_schema(ref_template="#/components/schemas/{model}", mode="serialization")
            for name, sub in js.pop("$defs", {}).items():
                comps.setdefault(name, sub)
            comps.setdefault(model.__name__, js)
        comps["ChatEventName"] = {"type": "string", "enum": list(SSE_MODELS.keys()), "title": "ChatEventName"}
        app.openapi_schema = schema
        return schema

    return openapi


def create_app(settings: Settings | None = None) -> FastAPI:
    """Rolüne göre uygulama. `settings` verilmezse ortamdan okunur (testte iki rol aynı süreçte kurulur)."""
    settings = settings or get_settings()
    app = FastAPI(
        title="Astronaut Health Monitor API",
        version=__version__,
        description=DESCRIPTION,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.engine = engine_for(settings.database_url_resolved)
    if settings.station_role == "earth":
        # CORS'tan önce eklenir → CORS en dışta kalır, 403 cevabı da CORS başlığı taşır
        app.middleware("http")(earth_read_only_middleware)
    app.middleware("http")(lang_middleware)  # istek dili (?lang= > Accept-Language > tr)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_exception_handler(ApiError, api_error_handler)  # type: ignore[arg-type]
    if not settings.legacy_enabled:  # eski ekranlar FastAPI'nin varsayılan hata biçimini bekler
        from fastapi.exceptions import RequestValidationError
        from starlette.exceptions import HTTPException as StarletteHTTPException

        app.add_exception_handler(RequestValidationError, validation_error_handler)  # type: ignore[arg-type]
        app.add_exception_handler(StarletteHTTPException, http_error_handler)  # type: ignore[arg-type]
    app.include_router(station_router, prefix="/api")
    app.include_router(auth_router, prefix="/api")
    app.include_router(catalog_router, prefix="/api")
    if settings.station_role == "ship" and settings.data_source == "astronaut_health":
        app.include_router(personal_router, prefix="/api")
        app.include_router(checkin_router, prefix="/api")
        app.include_router(downlink_router, prefix="/api")
        app.include_router(assistant_router, prefix="/api")
    if settings.station_role == "earth":
        app.include_router(monitor_router, prefix="/api")
    if settings.legacy_enabled:
        # Eski ekranların API'si ve eski analiz motoru: sadece gemi + DATA_SOURCE=synthetic
        app.include_router(legacy_router, prefix="/api")
    app.openapi = _custom_openapi(app)  # type: ignore[method-assign]
    return app


app = create_app()
