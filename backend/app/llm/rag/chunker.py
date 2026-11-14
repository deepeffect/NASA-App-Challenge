"""Bölümleri arama/embedding için parçalara (chunk) böler. Paragraf sınırlarına saygı gösterir."""

import hashlib
import re
from dataclasses import asdict, dataclass

from app.llm.rag.documents import Document

MAX_CHARS = 1200
OVERLAP_CHARS = 150


@dataclass
class Chunk:
    id: str
    file: str
    section: str | None
    page: int | None
    text: str

    def to_dict(self) -> dict:
        return asdict(self)


def _split(text: str, max_chars: int, overlap: int) -> list[str]:
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    out: list[str] = []
    cur = ""
    for p in paras:
        while len(p) > max_chars:  # tek paragraf çok uzunsa kelime sınırından kes
            cut = p.rfind(" ", 0, max_chars)
            cut = cut if cut > max_chars // 2 else max_chars
            if cur:
                out.append(cur)
                cur = ""
            out.append(p[:cut].strip())
            p = p[max(0, cut - overlap):].strip()
        if len(cur) + len(p) + 2 <= max_chars:
            cur = f"{cur}\n\n{p}" if cur else p
        else:
            if cur:
                out.append(cur)
            tail = cur[-overlap:] if overlap and cur else ""
            cur = f"{tail}\n\n{p}".strip() if tail else p
    if cur:
        out.append(cur)
    return out


def chunk_document(doc: Document, max_chars: int = MAX_CHARS, overlap: int = OVERLAP_CHARS) -> list[Chunk]:
    chunks: list[Chunk] = []
    for sec in doc.sections:
        for i, piece in enumerate(_split(sec.text, max_chars, overlap)):
            key = f"{doc.file}|{sec.heading}|{sec.page}|{i}"
            chunks.append(Chunk(id=hashlib.sha1(key.encode()).hexdigest()[:12], file=doc.file, section=sec.heading,
                                page=sec.page, text=piece))
    return chunks
