"""İstasyon rolleri: rol başına DB, /api/station, Dünya'nın salt okunurluğu, dil seçimi."""

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.i18n import parse_accept_language, resolve_lang
from app.main import create_app


def make_client(role: str) -> TestClient:
    return TestClient(create_app(Settings(station_role=role)))


@pytest.mark.parametrize("role", ["ship", "earth"])
def test_default_db_file_per_role(role: str) -> None:
    s = Settings(station_role=role, data_source="astronaut_health", database_url=None)
    assert s.database_url_resolved.endswith(f"data/processed/{role}.db")


def test_legacy_synthetic_ship_keeps_old_db_file() -> None:
    s = Settings(station_role="ship", data_source="synthetic", database_url=None)
    assert s.legacy_enabled and s.database_url_resolved.endswith("data/processed/health.db")
    assert not Settings(station_role="earth", data_source="synthetic").legacy_enabled


def test_explicit_database_url_wins() -> None:
    assert Settings(station_role="earth", database_url="sqlite:///x.db").database_url_resolved == "sqlite:///x.db"


def test_station_endpoint_ship(ship_client) -> None:
    info = ship_client.get("/api/station").json()
    assert info["role"] == "ship" and info["home_path"] == "/me" and info["read_only"] is False


def test_station_endpoint_legacy_ship() -> None:
    with make_client("ship") as c:  # test ortamı: DATA_SOURCE=synthetic
        info = c.get("/api/station").json()
    assert info["role"] == "ship" and info["home_path"] == "/legacy" and info["legacy_enabled"] is True


def test_station_endpoint_earth() -> None:
    with make_client("earth") as c:
        info = c.get("/api/station").json()
    assert info["role"] == "earth" and info["home_path"] == "/monitor" and info["read_only"] is True


def test_earth_rejects_writes_with_403() -> None:
    with make_client("earth") as c:
        for method, path in [("post", "/api/checkin"), ("put", "/api/alerts/x/share"), ("delete", "/api/anything")]:
            r = getattr(c, method)(path, headers={"Accept-Language": "en"})
            assert r.status_code == 403, path
            assert r.json()["code"] == "read_only"
            assert "read-only" in r.json()["detail"]
        r = c.post("/api/checkin", headers={"Accept-Language": "tr-TR,tr;q=0.9"})
        assert "salt okunur" in r.json()["detail"]


def test_earth_has_no_ship_routes() -> None:
    with make_client("earth") as c:
        assert c.get("/api/crew").status_code == 404


def test_ship_keeps_legacy_routes() -> None:
    paths = set(create_app(Settings(station_role="ship")).openapi()["paths"])
    assert "/api/crew" in paths and "/api/station" in paths


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        (None, None),
        ("", None),
        ("en-US,en;q=0.9,tr;q=0.8", "en"),
        ("tr-TR,tr;q=0.9,en-US;q=0.8", "tr"),
        ("de-DE,de;q=0.9,en;q=0.5", "en"),
        ("fr", None),
        ("en;q=0.2,tr;q=0.7", "tr"),
        ("tr;q=0,en", "en"),
    ],
)
def test_parse_accept_language(header: str | None, expected: str | None) -> None:
    assert parse_accept_language(header) == expected


def test_explicit_lang_beats_header() -> None:
    assert resolve_lang("en", "tr-TR") == "en"
    assert resolve_lang(None, "en-GB") == "en"
    assert resolve_lang("xx", None) == "tr"
