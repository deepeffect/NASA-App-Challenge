"""Uygulama yapılandırması (pydantic-settings).

Öncelik: ortam değişkenleri > backend/.env > varsayılanlar.
Göreli yollar repo köküne göre çözülür (çalışma dizininden bağımsız).
"""

import json
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- İstasyon ---
    # ship: gemi bilgisayarı (bütün veri, astronot ekranı /me) | earth: Dünya üssü (salt okunur /monitor)
    station_role: Literal["ship", "earth"] = "ship"
    # earth: gemi backend'inin adresi (downlink buradan alınır), örn. http://192.168.1.10:8000
    ship_url: str | None = None

    # --- Veri kaynağı ---
    # astronaut_health: data/raw/astronaut_health.json (yeni mimari, /me ve /monitor)
    # synthetic: eski sentetik veri + eski analiz motoru (/legacy ekranları ve eski testler)
    data_source: Literal["astronaut_health", "synthetic"] = "astronaut_health"
    dataset_path: Path = REPO_ROOT / "data" / "raw" / "astronaut_health.json"

    # --- Genel ---
    app_env: Literal["dev", "demo", "test"] = "dev"
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # --- Yollar ---
    data_dir: Path = REPO_ROOT / "data"
    config_dir: Path = BACKEND_DIR / "config"
    database_url: str | None = None
    docs_dir: Path | None = None
    rag_index_dir: Path | None = None

    # --- Analiz ---
    analysis_detectors: Annotated[list[str], NoDecode] = [
        "threshold",
        "baseline_deviation",
        "trend",
        "system_pattern",
    ]

    # --- LLM ---
    llm_provider: Literal["mock", "openai"] = "mock"
    llm_base_url: str = "http://localhost:11434/v1"
    llm_model: str = "qwen3:14b"
    llm_api_key: str = "ollama"
    llm_timeout: float = Field(120.0, gt=0)
    llm_health_timeout: float = Field(3.0, gt=0)
    llm_temperature: float = Field(0.3, ge=0, le=2)
    llm_max_tokens: int = Field(1024, ge=64)
    llm_thinking: bool = False
    llm_qwen_soft_switch: bool = True
    llm_tool_mode: Literal["auto", "native", "prompt"] = "auto"
    llm_max_tool_steps: int = Field(5, ge=1, le=12)
    llm_extra_body: dict[str, Any] = {}
    mock_stream_delay_ms: int = Field(15, ge=0)

    # --- RAG ---
    rag_backend: Literal["keyword", "embedding"] = "keyword"
    embedder: Literal["sentence_transformers", "ollama"] = "sentence_transformers"
    embedding_model: str = "BAAI/bge-m3"
    embedding_base_url: str | None = None
    rag_top_k: int = Field(4, ge=1, le=20)

    @field_validator("cors_origins", "analysis_detectors", mode="before")
    @classmethod
    def _split_list(cls, v: Any) -> Any:
        if isinstance(v, str):
            v = v.strip()
            if v.startswith("["):
                return json.loads(v)
            return [p.strip() for p in v.split(",") if p.strip()]
        return v

    @field_validator("data_dir", "config_dir", "docs_dir", "rag_index_dir", "dataset_path", mode="after")
    @classmethod
    def _resolve_path(cls, v: Path | None) -> Path | None:
        if v is None or v.is_absolute():
            return v
        return (REPO_ROOT / v).resolve()

    # --- Türetilmiş değerler ---
    @property
    def database_url_resolved(self) -> str:
        """DATABASE_URL verilmediyse rol başına ayrı dosya: data/processed/ship.db | earth.db.

        Eski sentetik mod (gemi + DATA_SOURCE=synthetic) eski dosyayı kullanmaya devam eder: health.db.
        """
        if self.database_url:
            return self.database_url
        name = "health" if self.legacy_enabled else self.station_role
        return f"sqlite:///{(self.data_dir / 'processed' / f'{name}.db').as_posix()}"

    @property
    def legacy_enabled(self) -> bool:
        """Eski ekranlar/API ve eski analiz motoru sadece gemide ve DATA_SOURCE=synthetic iken."""
        return self.station_role == "ship" and self.data_source == "synthetic"

    @property
    def docs_path(self) -> Path:
        return self.docs_dir or self.data_dir / "docs"

    @property
    def rag_index_path(self) -> Path:
        return self.rag_index_dir or self.data_dir / "processed" / "rag"


@lru_cache
def get_settings() -> Settings:
    return Settings()
