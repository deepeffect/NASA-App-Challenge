import os
from pathlib import Path

import pytest

# Testler her zaman mock LLM ve geçici DB ile çalışır (.env'den bağımsız).
os.environ["LLM_PROVIDER"] = "mock"
os.environ["MOCK_STREAM_DELAY_MS"] = "0"
os.environ["APP_ENV"] = "test"
# Global ayarlar eski sentetik moddadır (eski testler buna bağlı). Yeni mimarinin testleri kendi
# Settings(...) nesnelerini ve geçici DB'lerini kurar (tests/station/conftest.py).
os.environ["DATA_SOURCE"] = "synthetic"
os.environ["STATION_ROLE"] = "ship"

# Geliştiricinin backend/.env dosyası testlere sızmasın: gerçek kurulumda orada SHIP_URL, EARTH_LINK_TOKEN,
# STATION_ROLE=earth gibi değerler olur (yerel ağ testi) ve testlerin beklediği varsayılanları değiştirir.
# Testler sadece kodun varsayılanlarını, yukarıdaki değişkenleri ve kendi Settings(...) argümanlarını görür.
from app.config import Settings  # noqa: E402

Settings.model_config["env_file"] = None


@pytest.fixture(scope="session")
def tmp_db_url(tmp_path_factory: pytest.TempPathFactory) -> str:
    path: Path = tmp_path_factory.mktemp("db") / "test.db"
    return f"sqlite:///{path.as_posix()}"


@pytest.fixture(scope="session", autouse=True)
def _isolated_settings(tmp_db_url: str, tmp_path_factory: pytest.TempPathFactory):
    os.environ["DATABASE_URL"] = tmp_db_url
    os.environ["DOCS_DIR"] = str(Path(__file__).parent / "fixtures" / "docs")
    os.environ["RAG_INDEX_DIR"] = str(tmp_path_factory.mktemp("rag"))
    from app.config import get_settings
    from app.db import reset_engine

    get_settings.cache_clear()
    reset_engine()
    yield
    reset_engine()


@pytest.fixture(scope="session")
def seeded_db(_isolated_settings):
    """Geçici DB'yi demo senaryosuyla doldur (seed=42, 180 gün)."""
    from app.data.seed import seed_database
    from app.data.synthetic import SyntheticConfig
    from app.services.data import get_data_service

    stats = seed_database(SyntheticConfig(seed=42))
    get_data_service().invalidate()
    return stats


@pytest.fixture(scope="session")
def client(seeded_db):
    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app()) as c:
        yield c


# ---------------------------------------------------------------- yeni mimari (astronaut_health)
@pytest.fixture(scope="session")
def dataset():
    from app.config import get_settings
    from app.personal.dataset import load_dataset_file

    return load_dataset_file(get_settings().dataset_path)


@pytest.fixture(scope="session")
def catalog():
    from app.personal.catalog import load_personal_catalog

    return load_personal_catalog()
