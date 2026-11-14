"""Astronotun kendi ekranı (gemi, /me). Token sadece kendi astronotuna erişir."""

from typing import Annotated

from fastapi import APIRouter, Path, Request

from app.auth import AstronautDep, ensure_own
from app.i18n import Lang, LangDep
from app.models.schemas import DayView, ErrorResponse, PersonalCatalogResponse, PersonalOverview
from app.personal.dataset import AstronautSeries
from app.personal.store import personal_data
from app.services import personal as svc
from app.station import DBSession

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


@router.get("/me/days/{day}", response_model=DayView, responses=ERRORS, summary="Kendi günüm (durum, to-do, ölçümler)")
def my_day(day: Day, p: AstronautDep, request: Request, db: DBSession, lang: LangDep) -> DayView:
    return svc.astronaut_day(own_series(request, db, p.subject, lang), day, lang)


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
    return svc.astronaut_day(own_series(request, db, p.subject, lang), day, lang)
