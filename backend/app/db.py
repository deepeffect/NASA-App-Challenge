"""Veritabanı bağlantısı (SQLite + SQLModel).

Neden SQLite: veri küçük (~50-100 bin satır), analiz zaten pandas'ta yapılıyor ve
WAL modu sayesinde uvicorn çalışırken `seed`/`ingest` gibi komutlar ayrı process'ten
yazabiliyor (DuckDB dosyayı tek process'e kilitler).
"""

from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine

from app.config import get_settings

_engines: dict[str, Engine] = {}


def _sqlite_pragmas(dbapi_conn, _record) -> None:  # noqa: ANN001
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA synchronous=NORMAL")
    cur.execute("PRAGMA foreign_keys=ON")
    cur.execute("PRAGMA busy_timeout=5000")
    cur.close()


def engine_for(url: str) -> Engine:
    """URL başına tek engine (gemi ve Dünya DB'leri testte aynı süreçte açılabilir)."""
    eng = _engines.get(url)
    if eng is None:
        connect_args: dict = {}
        if url.startswith("sqlite"):
            connect_args["check_same_thread"] = False
            path = url.split("sqlite:///", 1)[-1]
            if path and path != ":memory:" and not url.startswith("sqlite://:"):
                Path(path).parent.mkdir(parents=True, exist_ok=True)
        eng = create_engine(url, connect_args=connect_args)
        if url.startswith("sqlite"):
            event.listen(eng, "connect", _sqlite_pragmas)
        _engines[url] = eng
    return eng


def get_engine() -> Engine:
    """Global ayarların (ortam / .env) engine'i."""
    return engine_for(get_settings().database_url_resolved)


def init_db(engine: Engine | None = None) -> None:
    """Tabloları oluştur (yoksa). Tablo modelleri import edilince metadata'ya kaydolur."""
    try:
        from app.models import tables  # noqa: F401
    except ImportError:  # (a) adımında tablo modülü henüz yok
        pass
    SQLModel.metadata.create_all(engine or get_engine())


def get_session() -> Iterator[Session]:
    """FastAPI dependency."""
    with Session(get_engine()) as session:
        yield session


def reset_engine() -> None:
    """Testler ve CLI için: ayarlar değişince engine'leri yeniden kur."""
    for eng in _engines.values():
        eng.dispose()
    _engines.clear()
