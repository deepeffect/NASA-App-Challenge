"""Seviyesi veriden gelen veri setlerinde (DatasetInfo.levels_from_data) türetilen alanlar.

Kaynak veri gösterge başına bir işaret verir (0 yeşil · 1 sarı · 2 kırmızı); durum, ana endişe, öz bakım
kodları ve yer desteği bayrağı kaynakta YOKTUR. Bu modül onları tek bir yerde, belgeli kurallarla türetir:

  durum          = o günkü en kötü seviye (0 Normal · 1 Dikkat · 2 Rahatsız)
  yer desteği    = en az bir gösterge kırmızı (2)
  ana endişe     = en kötü seviyedeki ilk göstergenin (katalog sırası) alanı; en kötüsü sadece ortam
                   ölçümüyse (radyasyon, kabin CO2) "none"
  öz bakım       = seviyesi katalogdaki tetik eşiğine (`trig`) ulaşan her göstergenin katalogdaki önerisi;
                   önce kırmızılar, sonra katalog sırası; aynı kod bir kez

Aynı fonksiyon iki yerde kullanılır: dönüştürücü (bütün ölçümlerle → astronotun gördüğü) ve gizlilik
filtresi (sadece Dünya'nın görebildiği ölçümlerle). Böylece paylaşılmamış ruh hali / stres Dünya'da ne
durumdan, ne ana endişeden, ne yapılacaklardan anlaşılır.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from app.personal.catalog import PersonalCatalog


@dataclass(frozen=True)
class Derived:
    health_status: int
    main_concern: str
    self_care: list[str]
    needs_ground_support: bool


def derive(cat: PersonalCatalog, levels: Mapping[str, int]) -> Derived:
    """`levels`: kolon → 0/1/2 (sadece hesaba katılacak ölçümler)."""
    inds = [i for i in cat.indicators if i.col in levels]
    status = max((levels[i.col] for i in inds), default=0)
    concern = "none"
    if status > 0:
        concern = next((i.domain for i in inds if levels[i.col] == status and i.domain in cat.areas), "none")
    care: list[str] = []
    for want in (2, 1):
        for i in inds:
            if levels[i.col] == want and want >= i.trig and i.action not in care:
                care.append(i.action)
    return Derived(
        health_status=status,
        main_concern=concern,
        self_care=care,
        needs_ground_support=any(levels[i.col] == 2 for i in inds),
    )
