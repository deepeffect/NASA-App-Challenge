"""Basit dil tespiti (TR/EN) — kullanıcının dilinde cevap vermek için."""

import re

_TR_CHARS = set("çğıöşüÇĞİÖŞÜ")
_TR_WORDS = {
    "ve", "bir", "bu", "ne", "nasıl", "nasilim", "nasılım", "mı", "mi", "mu", "mü", "ben", "benim", "bugün", "bugun",
    "uyku", "uykum", "var", "yok", "neden", "için", "icin", "çok", "cok", "durum", "durumum", "son", "gün", "gun",
    "merhaba", "selam", "teşekkürler", "lütfen", "lutfen", "nedir", "hakkında", "hakkinda", "stres", "nabız", "nabiz",
}


def detect_lang(text: str | None, default: str = "tr") -> str:
    if not text:
        return default
    if any(ch in _TR_CHARS for ch in text):
        return "tr"
    words = set(re.findall(r"[a-zçğıöşü]+", text.lower()))
    if words & _TR_WORDS:
        return "tr"
    if words:
        return "en"
    return default
