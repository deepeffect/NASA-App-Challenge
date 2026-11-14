"""Embedder arayüzü — GERÇEK İMPLEMENTASYON LLM EKİBİNDE.

İki çalışma yeri desteklenecek (karar LLM ekibinin):
  - EMBEDDER=sentence_transformers : bu makinede CPU'da (örn. BAAI/bge-m3; `pip install -e ".[rag]"`).
    Model internetsiz çalışma için ÖNCEDEN indirilmeli (HF cache veya yerel klasör yolu).
  - EMBEDDER=ollama : arkadaşın makinesindeki Ollama'nın embedding modeli (örn. `ollama pull bge-m3`),
    OpenAI uyumlu /v1/embeddings üzerinden (EMBEDDING_BASE_URL, yoksa LLM_BASE_URL).

Sözleşme: vektörler L2-normalize edilmiş float32 dönmeli (iç çarpım = kosinüs benzerliği).
"""

from typing import Protocol

import numpy as np

from app.config import Settings, get_settings


class Embedder(Protocol):
    name: str
    dim: int

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        """(len(texts), dim) float32, L2-normalize."""
        ...

    def embed_query(self, text: str) -> np.ndarray:
        """(dim,) float32, L2-normalize. bge-m3 gibi modellerde sorgu öneki gerekirse burada eklenir."""
        ...


class SentenceTransformerEmbedder:
    """TODO(LLM ekibi): sentence_transformers.SentenceTransformer(model, device="cpu") ile uygula.

    İpuçları: `normalize_embeddings=True`, batch_size=16-32, modeli bir kez yükleyip sakla,
    VRAM'i LLM'e bırakmak için device="cpu".
    """

    name = "sentence_transformers"

    def __init__(self, model: str) -> None:
        self.model = model
        self.dim = 0
        raise NotImplementedError("SentenceTransformerEmbedder henüz uygulanmadı (LLM ekibi). RAG_BACKEND=keyword kullanın.")

    def embed_documents(self, texts: list[str]) -> np.ndarray:  # pragma: no cover
        raise NotImplementedError

    def embed_query(self, text: str) -> np.ndarray:  # pragma: no cover
        raise NotImplementedError


class OllamaEmbedder:
    """TODO(LLM ekibi): openai.OpenAI(base_url=...).embeddings.create(model=..., input=[...]) ile uygula.

    Ollama /v1/embeddings OpenAI formatını destekler. Ağ gecikmesi için batch'le gönderin.
    """

    name = "ollama"

    def __init__(self, model: str, base_url: str) -> None:
        self.model, self.base_url = model, base_url
        self.dim = 0
        raise NotImplementedError("OllamaEmbedder henüz uygulanmadı (LLM ekibi). RAG_BACKEND=keyword kullanın.")

    def embed_documents(self, texts: list[str]) -> np.ndarray:  # pragma: no cover
        raise NotImplementedError

    def embed_query(self, text: str) -> np.ndarray:  # pragma: no cover
        raise NotImplementedError


def get_embedder(settings: Settings | None = None) -> Embedder:
    s = settings or get_settings()
    if s.embedder == "ollama":
        return OllamaEmbedder(s.embedding_model, s.embedding_base_url or s.llm_base_url)
    return SentenceTransformerEmbedder(s.embedding_model)
