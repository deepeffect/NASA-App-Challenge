"""Vektör indeksi arayüzü — GERÇEK İMPLEMENTASYON LLM EKİBİNDE.

Öneri: FAISS IndexFlatIP (birkaç bin chunk için tam arama anlıktır) + chunks.json yan dosyası.
Kayıt yeri: settings.rag_index_path (varsayılan data/processed/rag/). `python -m app.cli reindex`
önce chunks.json'u yazar; vektör arka ucu açıkken embeddings + faiss.index'i de yazmalıdır.
"""

from pathlib import Path
from typing import Protocol

import numpy as np

from app.llm.rag.chunker import Chunk


class VectorIndex(Protocol):
    def build(self, chunks: list[Chunk], vectors: np.ndarray) -> None: ...

    def save(self, path: Path) -> None: ...

    def load(self, path: Path) -> list[Chunk]: ...

    def search(self, query_vector: np.ndarray, k: int) -> list[tuple[Chunk, float]]: ...


class FaissIndex:
    """TODO(LLM ekibi): faiss.IndexFlatIP(dim); build → index.add(vectors); search → index.search(q[None], k)."""

    def __init__(self) -> None:
        raise NotImplementedError("FaissIndex henüz uygulanmadı (LLM ekibi). RAG_BACKEND=keyword kullanın.")
