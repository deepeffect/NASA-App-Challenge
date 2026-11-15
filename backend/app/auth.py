"""Giriş ve yetki (demo düzeyinde; LAN içi, internet yok).

- Astronot (sadece gemide): kimlik = şifre, büyük/küçük harf duyarsız. Token o astronotla sınırlı.
- Dünya üssü (sadece Dünya istasyonunda): EARTH / EARTH_PASSWORD. Token salt okunur.
Token: base64url(JSON) + "." + HMAC-SHA256 imzası. İçinde istasyon rolü vardır; başka istasyonun
token'ı (farklı anahtar veya rol) reddedilir.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import Depends, Query, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel import Session

from app.config import Settings
from app.errors import ApiError
from app.i18n import Lang, LangDep, t
from app.station import station_settings

EARTH_ID = "EARTH"
KV_SECRET = "auth.secret"
_bearer = HTTPBearer(auto_error=False, description="POST /api/auth/login ile alınan token")


@dataclass(frozen=True)
class Principal:
    kind: Literal["astronaut", "earth"]
    subject: str
    station: str

    @property
    def astronaut_id(self) -> str | None:
        return self.subject if self.kind == "astronaut" else None


# ============================================================================ token
def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def station_secret(request: Request) -> bytes:
    """Ayardaki AUTH_SECRET, yoksa istasyon DB'sinde saklanan rastgele anahtar."""
    cached = getattr(request.app.state, "auth_secret", None)
    if cached:
        return cached
    s: Settings = station_settings(request)
    if s.auth_secret:
        secret = s.auth_secret.encode("utf-8")
    else:
        from app.personal.store import kv_get, kv_set

        with Session(request.app.state.engine) as session:
            value = kv_get(session, KV_SECRET)
            if not value:
                value = secrets.token_hex(32)
                kv_set(session, KV_SECRET, value)
                session.commit()
        secret = str(value).encode("utf-8")
    request.app.state.auth_secret = secret
    return secret


def issue_token(secret: bytes, p: Principal, ttl_hours: float) -> tuple[str, datetime]:
    now = int(time.time())
    exp = now + int(ttl_hours * 3600)
    claims = {"k": p.kind, "s": p.subject, "st": p.station, "iat": now, "exp": exp}
    body = _b64(json.dumps(claims).encode("utf-8"))
    sig = _b64(hmac.new(secret, body.encode("ascii"), hashlib.sha256).digest())
    return f"{body}.{sig}", datetime.fromtimestamp(exp, UTC)


def verify_token(secret: bytes, token: str, station: str) -> Principal | None:
    try:
        body, sig = token.split(".", 1)
        expected = _b64(hmac.new(secret, body.encode("ascii"), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expected):
            return None
        claims = json.loads(_unb64(body))
        if claims["st"] != station or claims["exp"] < time.time() or claims["k"] not in ("astronaut", "earth"):
            return None
        return Principal(kind=claims["k"], subject=claims["s"], station=claims["st"])
    except (ValueError, KeyError, TypeError):
        return None


# ============================================================================ giriş
def _same(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def looks_like_astronaut_id(uid: str) -> bool:
    return len(uid) >= 2 and uid[0] == "A" and uid[1:].isdigit()


def authenticate(settings: Settings, astronaut_ids: list[str], raw_id: str, raw_password: str, lang: Lang) -> Principal:
    """Prototipteki giriş kuralları; ayrı hata mesajları (boş kimlik / bilinmeyen kimlik / yanlış şifre)."""
    uid = raw_id.strip().upper()
    pw = raw_password.strip().upper()
    role = settings.station_role
    if not uid:
        raise ApiError(400, "empty_id", t("login_empty_id", lang))
    if role == "ship":
        if uid == EARTH_ID:
            raise ApiError(403, "wrong_station", t("login_earth_on_ship", lang))
        if uid not in astronaut_ids:
            first, last = (astronaut_ids[0], astronaut_ids[-1]) if astronaut_ids else ("—", "—")
            raise ApiError(401, "unknown_id", t("login_unknown_id_ship", lang, id=uid, first=first, last=last))
        if not _same(pw, uid):
            raise ApiError(401, "wrong_password", t("login_wrong_password", lang))
        return Principal(kind="astronaut", subject=uid, station=role)
    # Dünya üssü
    if uid != EARTH_ID:
        if uid in astronaut_ids or looks_like_astronaut_id(uid):
            raise ApiError(403, "wrong_station", t("login_astronaut_on_earth", lang))
        raise ApiError(401, "unknown_id", t("login_unknown_id_earth", lang, id=uid, earth=EARTH_ID))
    if not _same(pw, settings.earth_password.strip().upper()):
        raise ApiError(401, "wrong_password", t("login_wrong_password_earth", lang))
    return Principal(kind="earth", subject=EARTH_ID, station=role)


# ============================================================================ dependency'ler
def current_principal(
    request: Request,
    lang: LangDep,
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)] = None,
    access_token: Annotated[str | None, Query(description="Sadece SSE için: EventSource başlık gönderemez")] = None,
) -> Principal:
    token = creds.credentials if creds else access_token
    if not token:
        raise ApiError(401, "auth_required", t("auth_required", lang))
    p = verify_token(station_secret(request), token, station_settings(request).station_role)
    if p is None:
        raise ApiError(401, "auth_invalid", t("auth_invalid", lang))
    return p


PrincipalDep = Annotated[Principal, Depends(current_principal)]


def require_astronaut(p: PrincipalDep, lang: LangDep) -> Principal:
    if p.kind != "astronaut":
        raise ApiError(403, "forbidden_kind", t("forbidden_kind", lang))
    return p


def require_earth(p: PrincipalDep, lang: LangDep) -> Principal:
    if p.kind != "earth":
        raise ApiError(403, "forbidden_kind", t("forbidden_kind", lang))
    return p


AstronautDep = Annotated[Principal, Depends(require_astronaut)]
EarthDep = Annotated[Principal, Depends(require_earth)]


def ensure_own(p: Principal, astronaut_id: str, lang: Lang) -> None:
    """Token sadece kendi astronotuna erişir: başka astronotun verisi 403."""
    if p.astronaut_id is None or p.astronaut_id != astronaut_id.strip().upper():
        raise ApiError(403, "forbidden_other_astronaut", t("forbidden_other_astronaut", lang))
