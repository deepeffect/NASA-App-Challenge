"""Belge arama giriş noktası: search(query, k) → [DocRef].

RAG_BACKEND=keyword  (varsayılan) BM25, bağımlılıksız
RAG_BACKEND=embedding Embedder + VectorIndex (LLM ekibi uygulayana kadar keyword'e düşer, health'te not edilir)

İndeks, docs klasörünün imzası (dosya adları + değişiklik zamanları) değişince kendiliğinden yeniden kurulur.
`python -m app.cli reindex` chunk'ları data/processed/rag/chunks.json'a da yazar.
"""

import json
import logging
import threading
from dataclasses import dataclass
from pathlib import Path

from app.config import Settings, get_settings
from app.llm.rag.chunker import Chunk, chunk_document
from app.llm.rag.documents import iter_doc_files, load_documents
from app.llm.rag.keyword import BM25Index
from app.models.schemas import DocRef, RAGHealth

log = logging.getLogger(__name__)
SNIPPET_CHARS = 400


@dataclass
class _State:
    signature: tuple
    documents: int
    chunks: list[Chunk]
    index: BM25Index
    backend_note: str | None


_lock = threading.Lock()
_state: _State | None = None


def _signature(docs_dir: Path) -> tuple:
    return tuple((p.as_posix(), p.stat().st_mtime) for p in iter_doc_files(docs_dir))


def _build(s: Settings) -> _State:
    docs = load_documents(s.docs_path)
    chunks = [c for d in docs for c in chunk_document(d)]
    note = None
    if s.rag_backend == "embedding":
        try:
            from app.llm.rag.embedder import get_embedder

            get_embedder(s)  # TODO(LLM ekibi): embed + VectorIndex kurulumunu burada yap
        except NotImplementedError as e:
            note = f"embedding arka ucu hazır değil, keyword kullanılıyor: {e}"
            log.warning(note)
    return _State(_signature(s.docs_path), len(docs), chunks, BM25Index(chunks), note)


def _get_state(s: Settings | None = None) -> _State:
    global _state
    s = s or get_settings()
    sig = _signature(s.docs_path)
    with _lock:
        if _state is None or _state.signature != sig:
            _state = _build(s)
        return _state


def search(query: str, k: int | None = None) -> list[DocRef]:
    st = _get_state()
    hits = st.index.search(query, k or get_settings().rag_top_k)
    return [DocRef(file=c.file, section=c.section, page=c.page, snippet=c.text[:SNIPPET_CHARS], score=score)
            for c, score in hits]


def reindex(settings: Settings | None = None) -> dict:
    global _state
    s = settings or get_settings()
    with _lock:
        _state = _build(s)
        st = _state
    out_dir = s.rag_index_path
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "chunks.json").write_text(json.dumps([c.to_dict() for c in st.chunks], ensure_ascii=False, indent=1),
                                         encoding="utf-8")
    return {"documents": st.documents, "chunks": len(st.chunks), "backend": "keyword", "note": st.backend_note,
            "docs_dir": str(s.docs_path), "index_dir": str(out_dir)}


def rag_health(settings: Settings | None = None) -> RAGHealth:
    try:
        st = _get_state(settings)
        return RAGHealth(backend="keyword", ok=True, documents=st.documents, chunks=len(st.chunks), error=st.backend_note)
    except Exception as e:  # noqa: BLE001
        return RAGHealth(backend="keyword", ok=False, error=str(e))
