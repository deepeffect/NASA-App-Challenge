"""Backend derlenmiş frontend'i kendisi servis eder (SPA), API yolları etkilenmez."""

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def dist(tmp_path):
    d = tmp_path / "dist"
    (d / "assets").mkdir(parents=True)
    (d / "index.html").write_text("<!doctype html><div id=root></div>", encoding="utf-8")
    (d / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    return d


def client(role: str, dist, **kw) -> TestClient:
    return TestClient(create_app(Settings(station_role=role, frontend_dist=dist, **kw)), follow_redirects=False)


@pytest.mark.parametrize(("role", "home"), [("earth", "/monitor")])
def test_root_redirects_to_station_home(dist, role, home) -> None:
    with client(role, dist) as c:
        r = c.get("/")
        assert r.status_code == 307 and r.headers["location"] == home


def test_legacy_mode_home_is_legacy(dist) -> None:
    with client("ship", dist, data_source="synthetic") as c:
        assert c.get("/").headers["location"] == "/legacy"
        assert c.get("/api/station").json()["home_path"] == "/legacy"


def test_spa_routes_and_assets(dist) -> None:
    with client("earth", dist) as c:
        for path in ("/monitor", "/monitor/astronauts/A003", "/me", "/legacy/checkin"):
            r = c.get(path)
            assert r.status_code == 200 and "id=root" in r.text, path  # "bu istasyonda değil"i arayüz gösterir
        assert c.get("/assets/app.js").text == "console.log(1)"
        assert c.get("/api/station").json()["role"] == "earth"
        r = c.get("/api/nowhere", headers={"Accept-Language": "en"})
        assert r.status_code == 404 and r.json()["code"] == "not_found"
        assert c.get("/docs").status_code == 200 and c.get("/openapi.json").status_code == 200
        assert c.get("/../backend/app/main.py").status_code in (200, 404)  # dist dışına çıkılamaz
        assert "def create_app" not in c.get("/../backend/app/main.py").text


def test_missing_build_shows_hint(tmp_path) -> None:
    with client("earth", tmp_path / "nope") as c:
        r = c.get("/monitor", headers={"Accept-Language": "tr"})
        assert r.status_code == 503 and "npm run serve" in r.text and "derlenmemiş" in r.text
        assert "not built" in c.get("/monitor?lang=en").text
