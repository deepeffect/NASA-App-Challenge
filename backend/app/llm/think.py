"""Qwen3 `<think>…</think>` bloklarını içerikten ayırma (stream ve tam metin için).

Sunucu düşünceyi ayrı alanda (`reasoning_content` / `reasoning`) döndürmezse model metninin içine
`<think>` etiketleriyle gömer. Thinking kapalıyken bile Qwen3 boş bir `<think>\n\n</think>` üretir.
"""

import re

OPEN, CLOSE = "<think>", "</think>"
_BLOCK = re.compile(r"<think>.*?(</think>|$)", re.DOTALL)


def split_think(text: str) -> tuple[str, str]:
    """(düşünce, içerik). Kapanmamış <think> metnin sonuna kadar düşünce sayılır."""
    if not text or OPEN not in text:
        return "", text or ""
    thoughts = []
    for m in _BLOCK.finditer(text):
        thoughts.append(m.group(0).removeprefix(OPEN).removesuffix(CLOSE))
    content = _BLOCK.sub("", text)
    return "".join(thoughts).strip(), content.lstrip()


def strip_think(text: str) -> str:
    return split_think(text)[1]


class ThinkFilter:
    """Akış halinde gelen parçaları ('token' | 'thinking', metin) olarak ayırır; etiketler parça sınırında bölünebilir."""

    def __init__(self) -> None:
        self._buf = ""
        self._in_think = False
        self._started = False  # içerik başladı mı (baştaki boşlukları yutmak için)
        self._think_started = False  # mevcut düşünce bloğunda boşluk dışı metin çıktı mı

    def feed(self, chunk: str) -> list[tuple[str, str]]:
        self._buf += chunk
        out: list[tuple[str, str]] = []
        while self._buf:
            tag = CLOSE if self._in_think else OPEN
            idx = self._buf.find(tag)
            if idx >= 0:
                self._emit(out, self._buf[:idx])
                self._buf = self._buf[idx + len(tag):]
                self._in_think = not self._in_think
                self._think_started = False
                continue
            keep = _partial_suffix(self._buf, tag)
            self._emit(out, self._buf[: len(self._buf) - keep])
            self._buf = self._buf[len(self._buf) - keep:]
            break
        return out

    def flush(self) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        self._emit(out, self._buf)
        self._buf = ""
        return out

    def _emit(self, out: list[tuple[str, str]], text: str) -> None:
        if not text:
            return
        if self._in_think:
            if not self._think_started:
                text = text.lstrip()
                if not text:
                    return
                self._think_started = True
            out.append(("thinking", text))
            return
        if not self._started:
            text = text.lstrip()
            if not text:
                return
            self._started = True
        out.append(("token", text))


def _partial_suffix(s: str, tag: str) -> int:
    """s'nin sonunda tag'in başlangıcı olabilecek en uzun kısmın uzunluğu."""
    for n in range(min(len(tag) - 1, len(s)), 0, -1):
        if tag.startswith(s[-n:]):
            return n
    return 0
