"""Kural tabanlı acil belirti tespiti. LLM'den tamamen bağımsızdır.

Sohbet mesajları ve check-in notları `detect_emergency()` ile taranır; eşleşme varsa
LLM'e gitmeden önce bir EmergencyNotice üretilir.
"""

import unicodedata
from functools import lru_cache
from pathlib import Path

import yaml

from app.config import get_settings
from app.models.schemas import EmergencyNotice, EmergencyProtocol

_TR_FOLD = str.maketrans({"ç": "c", "ğ": "g", "ı": "i", "ö": "o", "ş": "s", "ü": "u", "â": "a", "î": "i", "û": "u"})


def fold_text(text: str) -> str:
    """Büyük/küçük harf + Türkçe karakter + aksan duyarsız normalizasyon.

    "Göğüs AĞRISI" → "gogus agrisi". Türkçe 'İ' → 'i' (Python lower() 'i̇' üretir, düzeltilir).
    """
    s = text.replace("İ", "i").replace("I", "ı").lower().translate(_TR_FOLD)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.replace("’", "'").replace("`", "'")
    return " ".join(s.split())


@lru_cache(maxsize=4)
def _load(path: str, mtime: float) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _config(path: Path | None = None) -> dict:
    p = path or get_settings().config_dir / "emergency.yaml"
    return _load(str(p), p.stat().st_mtime)


def get_protocol(lang: str = "tr", path: Path | None = None) -> EmergencyProtocol:
    proto = _config(path).get("protocol", {})
    pick = lambda d: (d or {}).get(lang) or (d or {}).get("tr")  # noqa: E731
    return EmergencyProtocol(
        id=proto.get("id", "EMERGENCY"),
        title=pick(proto.get("title")) or "Emergency",
        steps=pick(proto.get("steps")) or [],
        contacts=proto.get("contacts") or [],
        verified=bool(proto.get("verified", False)),
    )


def detect_emergency(text: str | None, lang: str = "tr", path: Path | None = None) -> EmergencyNotice | None:
    """Metin acil belirti içeriyorsa EmergencyNotice, yoksa None."""
    if not text or not text.strip():
        return None
    folded = fold_text(text)
    cfg = _config(path)
    symptoms: list[str] = []
    labels: list[str] = []
    terms: list[str] = []
    for sid, spec in (cfg.get("symptoms") or {}).items():
        for term in spec.get("terms", []):
            if fold_text(term) in folded:
                if sid not in symptoms:
                    symptoms.append(sid)
                    label = (spec.get("label") or {}).get(lang) or (spec.get("label") or {}).get("tr") or sid
                    labels.append(label)
                terms.append(term)
    if not symptoms:
        return None
    if lang == "en":
        message = (
            f"Possible emergency symptom detected ({', '.join(labels)}). "
            "Start the emergency protocol and contact the crew medical officer now. "
            "This alert is rule-based and works without the AI assistant."
        )
    else:
        message = (
            f"Olası acil belirti tespit edildi ({', '.join(labels)}). "
            "Acil protokolü başlatın ve mürettebat sağlık sorumlusuna hemen haber verin. "
            "Bu uyarı kural tabanlıdır, yapay zekâ asistanından bağımsız çalışır."
        )
    return EmergencyNotice(
        matched_symptoms=symptoms,
        matched_labels=labels,
        matched_terms=terms,
        protocol=get_protocol(lang, path),
        message=message,
    )
