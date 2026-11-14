"""Bağımlılıksız BM25 anahtar kelime araması (embedding yokken varsayılan RAG arka ucu).

Türkçe için: büyük/küçük harf + Türkçe karakter katlama ve 5 karakterlik önek kökleme
("uykusu", "uykunun" → "uykus"/"uykun" ≠ ama "uyku" ile birlikte ilk 5 harf) — basit ama etkili.
"""

import math
import re
from collections import Counter

from app.llm.rag.chunker import Chunk
from app.safety.emergency import fold_text

_STOP = {
    "ve", "ile", "bir", "bu", "su", "o", "da", "de", "mi", "mu", "ne", "icin", "gibi", "daha", "cok", "en", "ya", "ki",
    "the", "a", "an", "of", "and", "or", "to", "in", "on", "for", "is", "are", "be", "with", "by", "as", "at", "it",
    "what", "how", "nasil", "nedir", "var", "hakkinda", "about",
}
PREFIX = 5


def tokenize(text: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+", fold_text(text))
    return [w[:PREFIX] for w in words if len(w) > 1 and w not in _STOP]


class BM25Index:
    def __init__(self, chunks: list[Chunk], k1: float = 1.5, b: float = 0.75) -> None:
        self.chunks = chunks
        self.k1, self.b = k1, b
        self.docs = [Counter(tokenize(f"{c.section or ''} {c.text}")) for c in chunks]
        self.lengths = [sum(d.values()) for d in self.docs]
        self.avgdl = (sum(self.lengths) / len(self.lengths)) if self.lengths else 0.0
        df: Counter = Counter()
        for d in self.docs:
            df.update(d.keys())
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def search(self, query: str, k: int = 4) -> list[tuple[Chunk, float]]:
        q = tokenize(query)
        if not q or not self.docs:
            return []
        scores = []
        for i, d in enumerate(self.docs):
            s = 0.0
            for t in q:
                tf = d.get(t)
                if not tf:
                    continue
                denom = tf + self.k1 * (1 - self.b + self.b * self.lengths[i] / (self.avgdl or 1))
                s += self.idf.get(t, 0.0) * tf * (self.k1 + 1) / denom
            if s > 0:
                scores.append((s, i))
        scores.sort(reverse=True)
        return [(self.chunks[i], round(s, 3)) for s, i in scores[:k]]
