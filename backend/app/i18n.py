"""Dil seçimi ve kullanıcıya dönen kısa metinler (TR/EN).

Öncelik: açık `lang` parametresi (sorgu veya gövde) > `Accept-Language` başlığı > Türkçe.
Frontend dil seçimini her zaman `lang` ile açıkça gönderir; başlık sadece yedektir.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import Depends, Query, Request

Lang = Literal["tr", "en"]
SUPPORTED: tuple[Lang, ...] = ("tr", "en")
DEFAULT_LANG: Lang = "tr"


def parse_accept_language(header: str | None) -> Lang | None:
    """`en-US,en;q=0.9,tr;q=0.8` → desteklenen en yüksek ağırlıklı dil (yoksa None)."""
    if not header:
        return None
    best: tuple[float, int, Lang] | None = None
    for pos, part in enumerate(header.split(",")):
        piece = part.strip()
        if not piece:
            continue
        tag, _, params = piece.partition(";")
        q = 1.0
        for p in params.split(";"):
            k, _, v = p.strip().partition("=")
            if k == "q":
                try:
                    q = float(v)
                except ValueError:
                    q = 0.0
        primary = tag.strip().lower().split("-")[0]
        if primary in SUPPORTED and q > 0:
            cand = (q, -pos, primary)  # eşit ağırlıkta önce yazılan kazanır
            if best is None or cand > best:
                best = cand  # type: ignore[assignment]
    return best[2] if best else None


def resolve_lang(explicit: str | None, accept_language: str | None) -> Lang:
    if explicit:
        e = explicit.strip().lower().split("-")[0]
        if e in SUPPORTED:
            return e  # type: ignore[return-value]
    return parse_accept_language(accept_language) or DEFAULT_LANG


def get_lang(
    request: Request,
    lang: Annotated[Lang | None, Query(description="Cevap dili; boşsa Accept-Language, o da yoksa tr")] = None,
) -> Lang:
    """FastAPI dependency: `?lang=` > Accept-Language > tr."""
    return resolve_lang(lang, request.headers.get("accept-language"))


LangDep = Annotated[Lang, Depends(get_lang)]


# ----------------------------------------------------------------------------- metinler
MESSAGES: dict[str, dict[Lang, str]] = {
    "earth_read_only": {
        "tr": "Dünya üssü salt okunurdur; bu istasyonda değişiklik yapılamaz.",
        "en": "The Earth base is read-only; nothing can be changed at this station.",
    },
    "not_on_station": {
        "tr": "Bu özellik bu istasyonda yok.",
        "en": "This feature is not available at this station.",
    },
}


def t(key: str, lang: Lang, **kwargs: object) -> str:
    """Anahtardan metin; bilinmeyen anahtar → anahtarın kendisi (testte yakalanır)."""
    entry = MESSAGES.get(key)
    if entry is None:
        return key
    text = entry.get(lang) or entry[DEFAULT_LANG]
    return text.format(**kwargs) if kwargs else text
