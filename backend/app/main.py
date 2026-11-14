"""FastAPI uygulaması.

Çalıştırma (backend/ içinde):  uvicorn app.main:app --reload
Dokümantasyon:                 http://localhost:8000/docs
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi

from app import __version__
from app.api import router as api_router
from app.config import get_settings
from app.db import init_db
from app.models.schemas import SSE_MODELS

DESCRIPTION = """
Astronot sağlık izleme sistemi — tamamen offline/gemide çalışır.

**Mimari ilke:** Sayısal analizi LLM yapmaz. Analiz motoru (Python) baseline, trend,
anomali, skor ve uyarıları üretir; LLM sadece yorumlar. Kural tabanlı uyarılar LLM
kapalıyken de çalışır.

Zaman kaydırıcısı: çoğu GET endpoint'i `as_of=YYYY-MM-DD` alır.
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


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Astronaut Health Monitor API",
        version=__version__,
        description=DESCRIPTION,
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router, prefix="/api")
    app.openapi = _custom_openapi(app)  # type: ignore[method-assign]
    return app


app = create_app()
