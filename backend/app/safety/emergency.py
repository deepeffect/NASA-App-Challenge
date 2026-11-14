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

def fold_text(text: str) -> str:
    """Büyük/küçük harf + aksan duyarsız normalizasyon: "CHEST  Pain" → "chest pain".

    RAG anahtar kelime araması da bunu kullanır; noktasız ı/İ NFKD ile ayrışmadığı için elle katlanır.
    """
    s = unicodedata.normalize("NFKD", text.replace("İ", "i").replace("I", "i").lower().replace("ı", "i"))
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


def get_protocol(lang: str = "en", path: Path | None = None) -> EmergencyProtocol:
    proto = _config(path).get("protocol", {})
    return EmergencyProtocol(
        id=proto.get("id", "EMERGENCY"),
        title=proto.get("title") or "Emergency",
        steps=proto.get("steps") or [],
        contacts=proto.get("contacts") or [],
        verified=bool(proto.get("verified", False)),
    )


def detect_emergency(text: str | None, lang: str = "en", path: Path | None = None) -> EmergencyNotice | None:
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
                    labels.append(spec.get("label") or sid)
                terms.append(term)
    if not symptoms:
        return None
    message = (
        f"Possible emergency symptom detected ({', '.join(labels)}). "
        "Start the emergency protocol and contact the crew medical officer now. "
        "This alert is rule-based and works without the AI assistant."
    )
    return EmergencyNotice(
        matched_symptoms=symptoms,
        matched_labels=labels,
        matched_terms=terms,
        protocol=get_protocol(lang, path),
        message=message,
    )
