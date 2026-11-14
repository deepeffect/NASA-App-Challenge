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
