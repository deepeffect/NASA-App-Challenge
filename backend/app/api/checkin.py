"""Günlük check-in (gemi). Gün = bugün; geçmiş günler salt okunur."""

import asyncio
from typing import Annotated

from fastapi import APIRouter, Path, Request

from app.auth import AstronautDep
from app.i18n import LangDep
from app.models.schemas import CheckinState, CheckinTurnRequest, CheckinTurnResponse, ErrorResponse
from app.personal.store import personal_data
from app.services import checkin as svc
from app.services.personal import day_index, get_series
from app.station import DBSession, station_settings

router = APIRouter(tags=["checkin"])
ERRORS = {
    400: {"model": ErrorResponse},
    401: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
}
Day = Annotated[int, Path(ge=1, description="1'den başlar")]


def _lock(request: Request, astronaut_id: str) -> asyncio.Lock:
    """Aynı astronotun turları sırayla işlenir (prototipteki ciBusy)."""
    state = request.app.state
    locks: dict[str, asyncio.Lock] | None = getattr(state, "checkin_locks", None)
    if locks is None:
        locks = state.checkin_locks = {}
    return locks.setdefault(astronaut_id, asyncio.Lock())


@router.get("/checkin", response_model=CheckinState, responses=ERRORS, summary="Bugünün check-in durumu")
def get_today(p: AstronautDep, request: Request, db: DBSession, lang: LangDep) -> CheckinState:
    series = get_series(personal_data(request.app.state.engine), db, p.subject, lang)
    return svc.state_view(series, series.today_index, svc.load_session(db, p.subject, series.today_index), lang)


@router.get("/checkin/days/{day}", response_model=CheckinState, responses=ERRORS, summary="Bir günün check-in'i (geçmiş: salt okunur)")
def get_day(day: Day, p: AstronautDep, request: Request, db: DBSession, lang: LangDep) -> CheckinState:
    series = get_series(personal_data(request.app.state.engine), db, p.subject, lang)
    i = day_index(len(series.days), day, lang)
    return svc.state_view(series, i, svc.load_session(db, p.subject, i), lang)


@router.post(
    "/checkin/turn",
    response_model=CheckinTurnResponse,
    responses=ERRORS,
    summary="Check-in cevabı → asistanın dönüşü (prototipin assistantTurn sözleşmesi)",
)
async def post_turn(req: CheckinTurnRequest, p: AstronautDep, request: Request, db: DBSession, lang: LangDep) -> CheckinTurnResponse:
    series = get_series(personal_data(request.app.state.engine), db, p.subject, lang)
    async with _lock(request, p.subject):
        return await svc.turn(db, station_settings(request), series, req.answer, lang)


@router.post("/checkin/reset", response_model=CheckinState, responses=ERRORS, summary="Baştan başla (sadece paylaşılmadıysa)")
async def post_reset(p: AstronautDep, request: Request, db: DBSession, lang: LangDep) -> CheckinState:
    series = get_series(personal_data(request.app.state.engine), db, p.subject, lang)
    async with _lock(request, p.subject):
        return svc.reset(db, series, lang)
