"""Sayı denetimi: "Sayıları LLM üretmez" ilkesinin kod düzeyinde kontrolü.

LLM çıktısındaki her sayı, modele verilen veri (tool sonuçları / bağlam JSON'u / kullanıcı mesajı)
içinde aranır. Bulunamayanlar `ungrounded_numbers` olarak raporlanır (engellemez; UI uyarı gösterir).

Eşleşme toleransı: max(metindeki hassasiyetin yarısı, değerin %2'si)
  "5 saat" ↔ 4,97 · "5,1 sa" ↔ 5 · "7,2" ↔ 7.18 eşleşir; "5 saat" ↔ 7,2 eşleşmez.

Bilinçli olarak yok sayılanlar:
  - tarihler, saatler, kimlikler (AST-02, evt_…), standart/belge kodları (NASA-STD-3001)
  - payda olarak kullanılan sayılar ("35/100", "3/5" → ölçek sınırı)
  - 0-10 arası tam sayılar, ANCAK yanında metrik birimi yoksa ("3 gün", "2 uyarı").
    Birimli küçük sayılar ("5 saat", "9 bpm", "%5") her zaman aranır.
"""

import math
import re
from collections.abc import Iterable
from typing import Any, NamedTuple

_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)?\b|\b\d{1,2}[./]\d{1,2}[./]\d{2,4}\b")
_TIME = re.compile(r"\b\d{1,2}:\d{2}\b")
_IDS = re.compile(
    r"\b(?:AST|evt|call)[-_][\w-]+\b"            # astronot / olay / tool çağrısı kimlikleri
    r"|\b[A-Za-z]+(?:-[A-Za-z]+)*-\d+[A-Za-z]*\b",  # standart/belge kodları: NASA-STD-3001, ISO-8601
    re.IGNORECASE,
)
_NUM = re.compile(r"(?<![\w.,])[-+−]?\d+(?:[.,]\d+)?(?![\w]|[.,]\d)")
# Sayının hemen ardından gelen metrik birimi (TR/EN). "saat" Türkçe ekleri de kapsar: saatten, saatlik…
_UNIT_AFTER = re.compile(
    r"\s?(?:saat\w*|sa\b|hours?\b|hrs?\b|h\b|bpm\b|ms\b|%|msv\b|mmhg\b|°\s?c\b|°|kg\b|dk\b|dakika\w*|minutes?\b|mins?\b|min\b)",
    re.IGNORECASE,
)
SMALL_INT_MAX = 10


class Num(NamedTuple):
    raw: str
    value: float
    decimals: int
    has_unit: bool
    denominator: bool


def _clean(text: str) -> str:
    for rx in (_DATE, _TIME, _IDS):
        text = rx.sub(" ", text)
    return text


def extract_numbers(text: str) -> list[Num]:
    """Metindeki sayılar — Türkçe ondalık virgül desteklenir ("5,1")."""
    out: list[Num] = []
    cleaned = _clean(text or "")
    for m in _NUM.finditer(cleaned):
        raw = m.group(0)
        norm = raw.replace("−", "-").replace(",", ".")
        try:
            val = float(norm)
        except ValueError:
            continue
        decimals = len(norm.split(".")[1]) if "." in norm else 0
        before = cleaned[m.start() - 1] if m.start() > 0 else ""
        has_unit = before == "%" or bool(_UNIT_AFTER.match(cleaned, m.end()))
        out.append(Num(raw, val, decimals, has_unit, before == "/"))
    return out


def collect_numbers(obj: Any, acc: set[float] | None = None) -> set[float]:
    """JSON benzeri yapıdaki tüm sayılar (metin alanlarındaki sayılar dahil)."""
    acc = set() if acc is None else acc
    if isinstance(obj, bool) or obj is None:
        return acc
    if isinstance(obj, (int, float)):
        if math.isfinite(obj):
            acc.add(float(obj))
    elif isinstance(obj, str):
        acc.update(n.value for n in extract_numbers(obj))
    elif isinstance(obj, dict):
        for v in obj.values():
            collect_numbers(v, acc)
    elif isinstance(obj, (list, tuple, set)):
        for v in obj:
            collect_numbers(v, acc)
    return acc


def tolerance(value: float, decimals: int) -> float:
    return max(0.5 * 10 ** (-decimals), 0.02 * abs(value)) + 1e-9


def _matches(value: float, decimals: int, sources: Iterable[float]) -> bool:
    tol = tolerance(value, decimals)
    # abs-abs: "2,6 std düştü" ↔ z = -2.6 gibi işaretsiz anlatımlar
    return any(abs(s - value) <= tol or abs(abs(s) - abs(value)) <= tol for s in sources)


def find_ungrounded_numbers(text: str, sources: Iterable[Any], ignore_small_ints: bool = True) -> list[str]:
    pool: set[float] = set()
    for src in sources:
        collect_numbers(src, pool)
    missing: list[str] = []
    for n in extract_numbers(text):
        if n.denominator:
            continue
        if ignore_small_ints and n.decimals == 0 and 0 <= n.value <= SMALL_INT_MAX and not n.has_unit:
            continue
        if not _matches(n.value, n.decimals, pool) and n.raw not in missing:
            missing.append(n.raw)
    return missing
