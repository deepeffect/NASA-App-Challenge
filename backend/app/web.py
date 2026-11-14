"""Derlenmiş frontend'i (frontend/dist) backend'in kendisi servis eder: aynı adres, CORS gerekmez.

- `/`            → bu istasyonun ana ekranı (gemi: /me, Dünya: /monitor)
- `/assets/...`  → statik dosyalar
- diğer GET      → index.html (SPA). "/monitor gemide" gibi durumları arayüz "bu istasyonda değil" diye gösterir.
- `/api/...`, `/docs`, `/openapi.json` bu yakalayıcıya düşmez.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException

from app.i18n import resolve_lang
from app.config import Settings
from app.station import home_path

RESERVED = ("api/", "docs", "redoc", "openapi.json")
MISSING = {
    "tr": "<h1>Arayüz derlenmemiş</h1><p>Kök klasörde <code>npm run serve</code> çalıştırın "
    "(frontend derlenir ve bu sunucu servis eder). API çalışıyor: <a href='/docs'>/docs</a></p>",
    "en": "<h1>Frontend not built</h1><p>Run <code>npm run serve</code> in the repository root "
    "(it builds the frontend and this server serves it). The API is running: <a href='/docs'>/docs</a></p>",
}


def mount_frontend(app: FastAPI, settings: Settings) -> None:
    dist = settings.frontend_dist
    index = dist / "index.html"
    if (dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/", include_in_schema=False)
    def root() -> Response:
        return RedirectResponse(home_path(settings), status_code=307)

    @app.api_route("/{full_path:path}", methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"], include_in_schema=False)
    def spa(full_path: str, request: Request) -> Response:
        if full_path.startswith(RESERVED) or request.method not in ("GET", "HEAD"):
            raise HTTPException(status_code=404)  # API'de bilinmeyen yol: JSON 404 (kullanıcının dilinde)
        if not index.exists():
            lang = resolve_lang(request.query_params.get("lang"), request.headers.get("accept-language"))
            return HTMLResponse(MISSING[lang], status_code=503)
        candidate = (dist / full_path).resolve()
        if full_path and candidate.is_file() and dist.resolve() in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(index, headers={"Cache-Control": "no-cache"})
