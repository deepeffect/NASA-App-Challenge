"""Check-in bağlamı: prototipteki ciSend() içinde kurulan `ctx`, backend tarafından.

Astronot token'dan, gün = bugün (son kayıt). Okumalar prototipteki gibi biçimlidir:
value = toFixed(used, dec), unit = unitText, healthy = rangeText.
"""

from __future__ import annotations

from typing import Any

from app.i18n import Lang
from app.personal.catalog import PersonalCatalog
from app.personal.dataset import AstronautSeries
from app.personal.evaluate import readings_for_day
from app.personal.view import num, range_text, unit_text


def build_context(
    cat: PersonalCatalog,
    series: AstronautSeries,
    i: int,
    lang: Lang,
    history: list[dict[str, str]],
    step: int,
    answer: str,
) -> dict[str, Any]:
    meta = series.meta
    day = series.days[i]
    return {
        "astronaut": {"id": meta.id, "age": meta.age, "sex": meta.sex, "mission": cat.missions[meta.mission].get(lang)},
        "day": i + 1,
        "mission_day": day.mission_day,
        "status": cat.statuses[day.health_status].get(lang),
        "readings": [
            {
                "col": r.ind.col,
                "label": r.ind.label.get(lang),
                "value": num(r.used, r.ind.dec, lang),
                "unit": unit_text(r.ind, lang),
                "healthy": range_text(r.ind, lang),
                "level": r.level,
            }
            for r in readings_for_day(cat, series, i)
        ],
        "todo": [cat.solution(c).title.get(lang) for c in day.self_care if cat.solution(c)],  # type: ignore[union-attr]
        "history": list(history),
        "step": step,
        "answer": answer,
        # Prototipte SOL global'inden okunan başlıklar (fix / fever cümleleri için)
        "solution_titles": {s.code: s.title.get(lang) for s in cat.solutions},
    }
