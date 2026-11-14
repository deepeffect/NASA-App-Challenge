"""Astronotun kendi ekranı (gemi, /me). Token sadece kendi astronotuna erişir."""

from typing import Annotated

from fastapi import APIRouter, Path, Request

from app.auth import AstronautDep, ensure_own
from app.i18n import Lang, LangDep
from app.models.schemas import ActionDoneRequest, ActionDoneResponse, DayView, ErrorResponse, PersonalCatalogResponse, PersonalOverview
from app.personal.dataset import AstronautSeries
from app.personal.store import personal_data
from app.services import personal as svc
from app.station import DBSession, station_settings

router = APIRouter(tags=["personal"])
public_router = APIRouter(tags=["catalog"])
ERRORS = {401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}}
Day = Annotated[int, Path(ge=1, description="1'den başlar; son gün = bugün")]


@public_router.get("/catalog", response_model=PersonalCatalogResponse, summary="Ölçümler ve bütün self-care çözümleri")
def get_catalog(lang: LangDep) -> PersonalCatalogResponse:
    return svc.catalog_response(lang)


def own_series(request: Request, db: DBSession, astronaut_id: str, lang: Lang) -> AstronautSeries:
    return svc.get_series(personal_data(request.app.state.engine), db, astronaut_id, lang)


@router.get("/me", response_model=PersonalOverview, responses=ERRORS, summary="Kendi genel bakışım: 30 günlük şerit")
def my_overview(p: AstronautDep, request: Request, db: DBSession, lang: LangDep) -> PersonalOverview:
    return svc.overview(own_series(request, db, p.subject, lang), lang)


def _day_view(request: Request, db: DBSession, astronaut_id: str, day: int, lang: Lang) -> DayView:
    from app.downlink.outbox import done_codes
    from app.services.checkin import load_session, share_of

    series = own_series(request, db, astronaut_id, lang)
    i = svc.day_index(len(series.days), day, lang)
    share = share_of(load_session(db, astronaut_id, i))
    return svc.astronaut_day(series, day, lang, share=share, done_codes=done_codes(db, astronaut_id, i))


@router.get("/me/days/{day}", response_model=DayView, responses=ERRORS, summary="Kendi günüm (durum, to-do, ölçümler)")
def my_day(day: Day, p: AstronautDep, request: Request, db: DBSession, lang: LangDep) -> DayView:
    return _day_view(request, db, p.subject, day, lang)


@router.get(
    "/personal/{astronaut_id}", response_model=PersonalOverview, responses=ERRORS, summary="Genel bakış (sadece kendi kimliğiniz)"
)
def overview(astronaut_id: str, p: AstronautDep, request: Request, db: DBSession, lang: LangDep) -> PersonalOverview:
    ensure_own(p, astronaut_id, lang)
    return svc.overview(own_series(request, db, p.subject, lang), lang)


@router.get(
    "/personal/{astronaut_id}/days/{day}", response_model=DayView, responses=ERRORS, summary="Gün (sadece kendi kimliğiniz)"
)
def personal_day(astronaut_id: str, day: Day, p: AstronautDep, request: Request, db: DBSession, lang: LangDep) -> DayView:
    ensure_own(p, astronaut_id, lang)
    return _day_view(request, db, p.subject, day, lang)


@router.post(
    "/actions/done",
    response_model=ActionDoneResponse,
    responses={**ERRORS, 400: {"model": ErrorResponse}},
    summary="Bugünün to-do öğesini 'yaptım' olarak işaretle (veya kaldır)",
)
def post_action_done(req: ActionDoneRequest, p: AstronautDep, request: Request, db: DBSession, lang: LangDep) -> ActionDoneResponse:
    series = own_series(request, db, p.subject, lang)
    svc.mark_action(db, station_settings(request), series, req.code, req.done, lang)
    return ActionDoneResponse(code=req.code, done=req.done, day=_day_view(request, db, p.subject, len(series.days), lang))
