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

_engine: Engine | None = None


def _sqlite_pragmas(dbapi_conn, _record) -> None:  # noqa: ANN001
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA synchronous=NORMAL")
    cur.execute("PRAGMA foreign_keys=ON")
    cur.execute("PRAGMA busy_timeout=5000")
    cur.close()


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        url = get_settings().database_url_resolved
        connect_args: dict = {}
        if url.startswith("sqlite"):
            connect_args["check_same_thread"] = False
            path = url.split("sqlite:///", 1)[-1]
            if path and path != ":memory:" and not url.startswith("sqlite://:"):
                Path(path).parent.mkdir(parents=True, exist_ok=True)
        _engine = create_engine(url, connect_args=connect_args)
        if url.startswith("sqlite"):
            event.listen(_engine, "connect", _sqlite_pragmas)
    return _engine


def init_db() -> None:
    """Tabloları oluştur (yoksa). Tablo modelleri import edilince metadata'ya kaydolur."""
    try:
        from app.models import tables  # noqa: F401
    except ImportError:  # (a) adımında tablo modülü henüz yok
        pass
    SQLModel.metadata.create_all(get_engine())


def get_session() -> Iterator[Session]:
    """FastAPI dependency."""
    with Session(get_engine()) as session:
        yield session


def reset_engine() -> None:
    """Testler ve CLI için: ayarlar değişince engine'i yeniden kur."""
    global _engine
    if _engine is not None:
        _engine.dispose()
    _engine = None
