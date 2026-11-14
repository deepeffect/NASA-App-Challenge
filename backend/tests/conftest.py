import os
from pathlib import Path

import pytest

# Testler her zaman mock LLM ve geçici DB ile çalışır (.env'den bağımsız).
os.environ["LLM_PROVIDER"] = "mock"
os.environ["MOCK_STREAM_DELAY_MS"] = "0"
os.environ["APP_ENV"] = "test"
# Geliştiricinin .env'indeki LLM ayarları testleri etkilemesin (kod varsayılanları)
os.environ["LLM_QWEN_SOFT_SWITCH"] = "true"
os.environ["LLM_THINKING"] = "false"
os.environ["LLM_TOOL_MODE"] = "auto"


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
