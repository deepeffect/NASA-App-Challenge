"""FastAPI uygulaması.

Çalıştırma (backend/ içinde):  uvicorn app.main:app --reload
Dokümantasyon:                 http://localhost:8000/docs
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi

from app import __version__
from app.api import router as legacy_router
from app.api.station import router as station_router
from app.config import Settings, get_settings
from app.db import init_db
from app.models.schemas import SSE_MODELS
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
async def lifespan(_app: FastAPI):
    init_db()
    yield


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
    if settings.station_role == "earth":
        # CORS'tan önce eklenir → CORS en dışta kalır, 403 cevabı da CORS başlığı taşır
        app.middleware("http")(earth_read_only_middleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(station_router, prefix="/api")
    if settings.station_role == "ship":
        app.include_router(legacy_router, prefix="/api")
    app.openapi = _custom_openapi(app)  # type: ignore[method-assign]
    return app


app = create_app()
