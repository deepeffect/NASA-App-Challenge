"""Giriş (iki istasyonda da): POST /api/auth/login, GET /api/auth/hint, GET /api/auth/me."""

from fastapi import APIRouter, Request
from sqlmodel import Session

from app.auth import EARTH_ID, PrincipalDep, authenticate, issue_token, station_secret
from app.i18n import LangDep, t
from app.models.schemas import AccountRange, AuthHint, ErrorResponse, LoginRequest, LoginResponse, PrincipalInfo
from app.station import HOME_PATH, DBSession, station_settings

router = APIRouter(tags=["auth"])
ERRORS = {400: {"model": ErrorResponse}, 401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}}


def station_astronaut_ids(request: Request, session: Session) -> list[str]:
    """Bu istasyonda bilinen astronot kimlikleri (sıralı)."""
    s = station_settings(request)
    if s.station_role == "ship":
        if s.data_source != "astronaut_health":
            return []
        from app.personal.store import personal_data

        return sorted(personal_data(request.app.state.engine).ids(session))
    from app.downlink.earth_store import earth_astronaut_ids

    return earth_astronaut_ids(session)


@router.post("/auth/login", response_model=LoginResponse, responses=ERRORS, summary="Giriş (gemi: astronot, Dünya: EARTH)")
def login(req: LoginRequest, request: Request, lang: LangDep, db: DBSession) -> LoginResponse:
    s = station_settings(request)
    p = authenticate(s, station_astronaut_ids(request, db), req.id, req.password, lang)
    token, exp = issue_token(station_secret(request), p, s.auth_token_ttl_hours)
    return LoginResponse(
        token=token,
        kind=p.kind,
        subject=p.subject,
        astronaut_id=p.astronaut_id,
        station=s.station_role,
        home_path=HOME_PATH[s.station_role],
        expires_at=exp,
    )


@router.get("/auth/hint", response_model=AuthHint, summary="Giriş kartı ipucu: kimlik aralığı ve hesap sayısı")
def hint(request: Request, lang: LangDep, db: DBSession) -> AuthHint:
    s = station_settings(request)
    if s.station_role == "ship":
        ids = station_astronaut_ids(request, db)
        if not ids:
            return AuthHint(station="ship", astronauts=None, earth_id=None, text=t("hint_ship_empty", lang))
        rng = AccountRange(first_id=ids[0], last_id=ids[-1], count=len(ids))
        text = t("hint_ship", lang, first=rng.first_id, last=rng.last_id, count=rng.count)
        return AuthHint(station="ship", astronauts=rng, earth_id=None, text=text)
    if s.earth_password.strip().upper() == EARTH_ID:
        text = t("hint_earth", lang, earth=EARTH_ID, password=EARTH_ID)
    else:
        text = t("hint_earth_custom", lang, earth=EARTH_ID)
    return AuthHint(station="earth", astronauts=None, earth_id=EARTH_ID, text=text)


@router.get("/auth/me", response_model=PrincipalInfo, responses=ERRORS, summary="Token'ın sahibi")
def me(p: PrincipalDep) -> PrincipalInfo:
    return PrincipalInfo(
        kind=p.kind, subject=p.subject, astronaut_id=p.astronaut_id, station=p.station, read_only=p.kind == "earth"
    )
