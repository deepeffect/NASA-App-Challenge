"""Yeni mimarinin test fikstürleri: her rol kendi Settings nesnesi ve geçici DB'si ile kurulur."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings


def sqlite_url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


@pytest.fixture(scope="session")
def ship_settings(tmp_path_factory: pytest.TempPathFactory) -> Settings:
    db = tmp_path_factory.mktemp("ship") / "ship.db"
    return Settings(station_role="ship", data_source="astronaut_health", database_url=sqlite_url(db))


@pytest.fixture(scope="session")
def ship_app(ship_settings: Settings):
    from app.main import create_app

    return create_app(ship_settings)


@pytest.fixture(scope="session")
def ship_client(ship_app) -> TestClient:
    with TestClient(ship_app) as c:  # açılışta veri seti yüklenir
        yield c


@pytest.fixture(scope="session")
def earth_settings(tmp_path_factory: pytest.TempPathFactory) -> Settings:
    db = tmp_path_factory.mktemp("earth") / "earth.db"
    return Settings(station_role="earth", data_source="astronaut_health", database_url=sqlite_url(db), ship_url=None)


@pytest.fixture(scope="session")
def earth_app(earth_settings: Settings):
    from app.main import create_app

    return create_app(earth_settings)


@pytest.fixture(scope="session")
def earth_client(earth_app) -> TestClient:
    with TestClient(earth_app) as c:
        yield c


def login(client: TestClient, uid: str, password: str | None = None) -> dict[str, str]:
    """Giriş yapıp Authorization başlığını döner."""
    r = client.post("/api/auth/login", json={"id": uid, "password": uid if password is None else password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}
