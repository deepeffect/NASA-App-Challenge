"""İki rolde de bulunan route'lar."""

from fastapi import APIRouter, Request

from app import __version__
from app.models.schemas import StationInfo
from app.station import home_path, station_settings

router = APIRouter(tags=["station"])


@router.get("/station", response_model=StationInfo, summary="Bu istasyonun rolü ve ana ekranı")
def get_station(request: Request) -> StationInfo:
    s = station_settings(request)
    return StationInfo(
        role=s.station_role,
        version=__version__,
        home_path=home_path(s),
        read_only=s.station_role == "earth",
        data_source=s.data_source,
        legacy_enabled=s.legacy_enabled,
    )
