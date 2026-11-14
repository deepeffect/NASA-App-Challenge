"""/api/health: DB, LLM sunucusu ve RAG durumunu kontrol eder."""

import time
from datetime import UTC, datetime

import httpx
from sqlalchemy import text

from app import __version__
from app.config import Settings, get_settings
from app.db import get_engine
from app.models.schemas import DBHealth, HealthResponse, LLMHealth, RAGHealth

_LLM_CACHE: dict[str, tuple[float, LLMHealth]] = {}
_LLM_CACHE_TTL_S = 10.0


def check_db() -> DBHealth:
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
            try:
                astronauts = conn.execute(text("SELECT COUNT(*) FROM astronaut")).scalar_one()
                measurements = conn.execute(text("SELECT COUNT(*) FROM measurement")).scalar_one()
                latest = conn.execute(text("SELECT MAX(timestamp) FROM measurement")).scalar_one()
            except Exception:  # tablolar henüz yok
                return DBHealth(ok=True, error="tables not created yet")
        latest_date = None
        if latest:
            latest_date = (latest if isinstance(latest, datetime) else datetime.fromisoformat(str(latest))).date()
        return DBHealth(ok=True, astronauts=astronauts, measurements=measurements, latest_date=latest_date)
    except Exception as e:  # noqa: BLE001
        return DBHealth(ok=False, error=str(e))


def model_matches(wanted: str, available: list[str]) -> bool:
    """Ollama 'qwen3:14b' ile 'qwen3:14b', 'qwen3' ile 'qwen3:latest' eşleşir."""
    if wanted in available:
        return True
    if ":" not in wanted and f"{wanted}:latest" in available:
        return True
    return any(a.split("/")[-1] == wanted for a in available)


def check_llm(settings: Settings | None = None, use_cache: bool = True) -> LLMHealth:
    s = settings or get_settings()
    now = datetime.now(UTC)
    if s.llm_provider == "mock":
        return LLMHealth(
            provider="mock",
            base_url=None,
            model="mock",
            reachable=True,
            model_available=True,
            available_models=["mock"],
            tool_mode="native",
            thinking=False,
            latency_ms=0.0,
            checked_at=now,
        )
    key = f"{s.llm_base_url}|{s.llm_model}"
    cached = _LLM_CACHE.get(key)
    if use_cache and cached and time.monotonic() - cached[0] < _LLM_CACHE_TTL_S:
        return cached[1]

    base = s.llm_base_url.rstrip("/")
    t0 = time.perf_counter()
    try:
        r = httpx.get(
            f"{base}/models",
            headers={"Authorization": f"Bearer {s.llm_api_key}"},
            timeout=s.llm_health_timeout,
        )
        latency = (time.perf_counter() - t0) * 1000
        r.raise_for_status()
        models = [m.get("id", "") for m in r.json().get("data", [])]
        result = LLMHealth(
            provider="openai",
            base_url=s.llm_base_url,
            model=s.llm_model,
            reachable=True,
            model_available=model_matches(s.llm_model, models),
            available_models=models,
            tool_mode=s.llm_tool_mode,
            thinking=s.llm_thinking,
            latency_ms=round(latency, 1),
            error=None if model_matches(s.llm_model, models) else f"'{s.llm_model}' is not installed on the server",
            checked_at=now,
        )
    except Exception as e:  # noqa: BLE001
        result = LLMHealth(
            provider="openai",
            base_url=s.llm_base_url,
            model=s.llm_model,
            reachable=False,
            model_available=False,
            tool_mode=s.llm_tool_mode,
            thinking=s.llm_thinking,
            error=f"{type(e).__name__}: {e}",
            checked_at=now,
        )
    _LLM_CACHE[key] = (time.monotonic(), result)
    return result


def check_rag(settings: Settings | None = None) -> RAGHealth:
    s = settings or get_settings()
    try:
        from app.llm.rag import rag_health  # (g) adımında gelir

        return rag_health(s)
    except ImportError:
        docs = s.docs_path
        n = sum(1 for p in docs.rglob("*") if p.suffix.lower() in {".md", ".txt", ".pdf"}) if docs.exists() else 0
        return RAGHealth(backend="keyword", ok=True, documents=n, chunks=0)


def health() -> HealthResponse:
    db = check_db()
    llm = check_llm()
    rag = check_rag()
    if not db.ok:
        status = "error"
    elif not (llm.reachable and llm.model_available) or not rag.ok:
        status = "degraded"
    else:
        status = "ok"
    return HealthResponse(status=status, version=__version__, time=datetime.now(UTC), db=db, llm=llm, rag=rag)
