"""İstasyon rolü (ship | earth) yardımcıları.

Aynı kod tabanı iki rolde çalışır. Rol `STATION_ROLE` ile seçilir; uygulama kurulurken
`app.state.settings`'e yazılır, route'lar ayarları buradan okur (testte iki rol aynı süreçte).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from fastapi.responses import JSONResponse
from sqlmodel import Session

from app.config import Settings, get_settings
from app.i18n import resolve_lang, t

HOME_PATH = {"ship": "/me", "earth": "/monitor"}
# Dünya üssünde yazma isteği olmasına rağmen izin verilen yollar (giriş yazma değildir)
EARTH_WRITE_ALLOWLIST = frozenset({"/api/auth/login"})
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def home_path(s: Settings) -> str:
    """Bu istasyonun ana ekranı: gemi /me, Dünya /monitor; eski sentetik mod /legacy."""
    return "/legacy" if s.legacy_enabled else HOME_PATH[s.station_role]


def station_settings(request: Request) -> Settings:
    """Uygulamanın kurulduğu ayarlar (create_app(settings=...)); yoksa global ayarlar."""
    return getattr(request.app.state, "settings", None) or get_settings()


def get_db(request: Request) -> Iterator[Session]:
    """Bu uygulamanın (istasyonun) DB oturumu."""
    with Session(request.app.state.engine) as session:
        yield session


DBSession = Annotated[Session, Depends(get_db)]


async def earth_read_only_middleware(request: Request, call_next):  # noqa: ANN001, ANN201
    """Dünya üssü salt okunur: /api altında GET dışı her istek 403 (giriş hariç)."""
    path = request.url.path
    if request.method not in SAFE_METHODS and path.startswith("/api/") and path not in EARTH_WRITE_ALLOWLIST:
        lang = resolve_lang(request.query_params.get("lang"), request.headers.get("accept-language"))
        return JSONResponse(status_code=403, content={"detail": t("earth_read_only", lang), "code": "read_only"})
    return await call_next(request)
