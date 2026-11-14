"""RAG iskeleti: belge yükleme, chunk'lama, BM25 arama, reindex, health, tool ve sohbet entegrasyonu.

Test belgesi: tests/fixtures/docs/ornek_rag_test_belgesi.md (açıkça ÖRNEK, gerçek kaynak değil).
"""

import json
from pathlib import Path

import pytest

from app.config import get_settings
from app.llm.rag import rag_health, reindex, search
from app.llm.rag.chunker import chunk_document
from app.llm.rag.documents import Document, Section, load_documents
from app.llm.rag.keyword import tokenize

FIXTURES = Path(__file__).parent / "fixtures" / "docs"


def test_load_markdown_sections_and_skip_readme(tmp_path):
    (tmp_path / "README.md").write_text("# indekslenmez", encoding="utf-8")
    (tmp_path / "_taslak.md").write_text("# gizli", encoding="utf-8")
    (tmp_path / "a.md").write_text("# Başlık\n\ngiriş\n\n## Bölüm 1\n\nmetin bir\n\n## Bölüm 2\n\nmetin iki\n", encoding="utf-8")
    docs = load_documents(tmp_path)
    assert [d.file for d in docs] == ["a.md"]
    assert docs[0].title == "Başlık"
    assert [s.heading for s in docs[0].sections] == ["Başlık", "Bölüm 1", "Bölüm 2"]


def test_chunking_respects_size():
    long = "\n\n".join(f"Paragraf {i} " + "kelime " * 60 for i in range(10))
    chunks = chunk_document(Document("x.md", "x", [Section("S", long)]), max_chars=800, overlap=100)
    assert len(chunks) > 3
    assert all(len(c.text) <= 800 for c in chunks)
    assert all(c.section == "S" and c.file == "x.md" for c in chunks)
    assert len({c.id for c in chunks}) == len(chunks)


def test_turkish_tokenizer():
    assert tokenize("Uykusuzluk ve UYKU düzeni") == ["uykus", "uyku", "duzen"]


def test_keyword_search_finds_section():
    hits = search("Uykum bozuldu, uyku düzeni için ne önerilir?", 2)
    assert hits and hits[0].file == "ornek_rag_test_belgesi.md"
    assert hits[0].section == "Örnek bölüm: Uyku"
    assert search("radyasyon dozimetre")[0].section == "Örnek bölüm: Radyasyon"
    assert search("treadmill exercise")[0].section == "Example section: Exercise"
    assert search("tamamen alakasız kuantum") == []


def test_reindex_and_health(tmp_path):
    stats = reindex()
    assert stats["documents"] == 1 and stats["chunks"] >= 3
    chunks = json.loads((get_settings().rag_index_path / "chunks.json").read_text(encoding="utf-8"))
    assert len(chunks) == stats["chunks"]
    h = rag_health()
    assert h.ok and h.backend == "keyword" and h.documents == 1


def test_embedding_backend_falls_back_to_keyword():
    from app.llm.rag import retriever

    s = get_settings().model_copy(update={"rag_backend": "embedding"})
    st = retriever._build(s)
    assert st.backend_note and "keyword" in st.backend_note
    assert st.index.search("uyku")


@pytest.mark.usefixtures("seeded_db")
def test_search_docs_tool_and_chat(client):
    from app.llm.tools import ToolContext, ToolRegistry

    r = ToolRegistry().execute(ToolContext(astronaut_id="AST-02"), "search_docs", {"query": "uyku düzeni"})
    assert r.ok and r.data["results"][0]["section"] == "Örnek bölüm: Uyku"

    from .test_contract import parse_sse

    body = {"astronaut_id": "AST-02", "messages": [{"role": "user", "content": "What do the documents say about treadmill exercise?"}]}
    with client.stream("POST", "/api/chat", json=body) as resp:
        events = parse_sse("".join(resp.iter_text()))
    assert "search_docs" in {p["name"] for n, p in events if n == "tool_call"}
    done = events[-1][1]
    assert done["doc_refs"] and done["doc_refs"][0]["file"] == "ornek_rag_test_belgesi.md"
    assert "ornek_rag_test_belgesi.md" in done["message"]
