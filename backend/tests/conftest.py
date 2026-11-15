import os
from datetime import UTC, datetime, time, timedelta
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

# Eski mod (synthetic) testlerinin takvimi: veri seti sabit bir aralıktır (SyntheticConfig: başlangıç + gün sayısı).
# Beklentiler bu aralığa GÖRE yazılır (görev günü = SYNTH.days, son gün = SYNTH_LAST_DAY), bugünün tarihine göre değil.
from app.data.synthetic import SyntheticConfig  # noqa: E402

SYNTH = SyntheticConfig()
SYNTH_LAST_DAY = SYNTH.start + timedelta(days=SYNTH.days - 1)
# Eski veri servisinin "şimdi"si: veri setinin son günü, akşam (o günün sentetik ölçümlerinden sonra)
FROZEN_NOW = datetime.combine(SYNTH_LAST_DAY, time(22, 0), UTC)


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


@pytest.fixture(scope="session", autouse=True)
def _frozen_legacy_clock(_isolated_settings):
    """Eski veri servisinin saati FROZEN_NOW'a sabitlenir (sadece testte; uygulama kodu değişmez).

    Neden: `POST /api/checkin` zaman damgası verilmezse check-in'i ve ruh hali / stres / uyku ölçümlerini "şimdi"ye
    yazar. Bu testler ortak, tohumlanmış bir veritabanını paylaşır; bugünün tarihi veri setinin son gününü geçince
    (UTC) o ölçümler veriye yeni bir gün ekler ve analizin "son günü" kayar (görev günü 181, rapor dönemi bugün…).
    Saat sabitlenince zaman damgasız check-in'ler hep veri setinin son gününe düşer: sonuçlar hangi gün
    çalıştırılırsa çalıştırılsın aynıdır. Yeni mimarinin testleri (tests/station) bu servisi kullanmaz.
    """
    from app.services import data as data_svc

    class _Clock(datetime):
        @classmethod
        def now(cls, tz=None):  # noqa: ANN001, ANN206
            return FROZEN_NOW.astimezone(tz) if tz is not None else FROZEN_NOW.replace(tzinfo=None)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(data_svc, "datetime", _Clock)
        yield


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
