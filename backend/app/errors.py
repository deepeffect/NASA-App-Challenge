"""Yeni uçların hata cevabı: {"detail": <kullanıcının dilinde>, "code": <makine kodu>}."""

from fastapi import Request
from fastapi.responses import JSONResponse


class ApiError(Exception):
    def __init__(self, status_code: int, code: str, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.code = code
        self.detail = detail


async def api_error_handler(_request: Request, exc: ApiError) -> JSONResponse:
    headers = {"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else None
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail, "code": exc.code}, headers=headers)


async def validation_error_handler(request: Request, exc) -> JSONResponse:  # noqa: ANN001
    """Yeni istasyonlar: 422'de kullanıcının dilinde kısa açıklama + alan listesi."""
    from fastapi.encoders import jsonable_encoder

    from app.i18n import current_lang, t

    errors = jsonable_encoder(exc.errors())
    fields = ", ".join(".".join(str(x) for x in e.get("loc", [])[1:]) or "body" for e in errors[:5])
    return JSONResponse(
        status_code=422,
        content={"detail": t("validation_error", current_lang(), fields=fields), "code": "validation_error", "errors": errors},
    )


async def http_error_handler(request: Request, exc) -> JSONResponse:  # noqa: ANN001
    """Yeni istasyonlar: yönlendirme hataları (404/405) kullanıcının dilinde."""
    from app.i18n import current_lang, t

    lang = current_lang()
    code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code)
    detail = t(code, lang) if code and exc.detail in ("Not Found", "Method Not Allowed") else exc.detail
    return JSONResponse(status_code=exc.status_code, content={"detail": detail, "code": code}, headers=getattr(exc, "headers", None))
