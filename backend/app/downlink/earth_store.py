"""Dünya üssünün veritabanı (downlink ile gelen, gizlilik filtresinden geçmiş veri)."""

from sqlmodel import Session


def earth_astronaut_ids(session: Session) -> list[str]:  # noqa: ARG001
    """Dünya'da bilinen astronotlar (downlink snapshot'ından). 7. bölümde doldurulur."""
    return []
