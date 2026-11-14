"""İki rolde de bulunan route'lar."""

from fastapi import APIRouter, Request

from app import __version__
from app.models.schemas import StationInfo
from app.station import HOME_PATH, station_settings

router = APIRouter(tags=["station"])


@router.get("/station", response_model=StationInfo, summary="Bu istasyonun rolü ve ana ekranı")
def get_station(request: Request) -> StationInfo:
    s = station_settings(request)
    return StationInfo(
        role=s.station_role,
        version=__version__,
        home_path=HOME_PATH[s.station_role],
        read_only=s.station_role == "earth",
    )
