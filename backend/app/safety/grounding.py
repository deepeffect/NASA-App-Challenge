"""Sayı denetimi: "Sayıları LLM üretmez" ilkesinin kod düzeyinde kontrolü.

LLM çıktısındaki her sayı, modele verilen veri (tool sonuçları / bağlam JSON'u / kullanıcı mesajı)
içinde, metindeki hassasiyete yuvarlanmış haliyle aranır. Bulunamayanlar `ungrounded_numbers`
olarak raporlanır (engellemez; UI uyarı gösterir).

Bilinçli olarak yok sayılanlar: tarihler, saatler, ID'ler (AST-02, evt_…), 0-10 arası tam sayılar
("3 gün", "1-5 ölçeği" gibi sayım/ölçek ifadeleri).
"""

import math
import re
from collections.abc import Iterable
from typing import Any

_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)?\b|\b\d{1,2}[./]\d{1,2}[./]\d{2,4}\b")
_TIME = re.compile(r"\b\d{1,2}:\d{2}\b")
_IDS = re.compile(r"\b(?:AST|evt|call)[-_][\w-]+\b", re.IGNORECASE)
_NUM = re.compile(r"(?<![\w.,])[-+−]?\d+(?:[.,]\d+)?(?![\w]|[.,]\d)")


def _clean(text: str) -> str:
    for rx in (_DATE, _TIME, _IDS):
        text = rx.sub(" ", text)
    return text


def extract_numbers(text: str) -> list[tuple[str, float, int]]:
    """[(ham, değer, ondalık_basamak)] — Türkçe ondalık virgül desteklenir ("5,1")."""
    out = []
    for m in _NUM.finditer(_clean(text or "")):
        raw = m.group(0)
        norm = raw.replace("−", "-").replace(",", ".")
        try:
            val = float(norm)
        except ValueError:
            continue
        decimals = len(norm.split(".")[1]) if "." in norm else 0
        out.append((raw, val, decimals))
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
        acc.update(v for _, v, _ in extract_numbers(obj))
    elif isinstance(obj, dict):
        for v in obj.values():
            collect_numbers(v, acc)
    elif isinstance(obj, (list, tuple, set)):
        for v in obj:
            collect_numbers(v, acc)
    return acc


def _matches(value: float, decimals: int, sources: Iterable[float]) -> bool:
    tol = 0.5 * 10 ** (-decimals) + 1e-9
    for s in sources:
        if abs(s - value) <= tol or abs(abs(s) - abs(value)) <= tol:  # "2,6 düştü" ↔ z = -2.6
            return True
    return False


def find_ungrounded_numbers(text: str, sources: Iterable[Any], ignore_small_ints: bool = True) -> list[str]:
    pool = set()
    for src in sources:
        collect_numbers(src, pool)
    missing: list[str] = []
    for raw, val, dec in extract_numbers(text):
        if ignore_small_ints and dec == 0 and 0 <= val <= 10:
            continue
        if not _matches(val, dec, pool) and raw not in missing:
            missing.append(raw)
    return missing
