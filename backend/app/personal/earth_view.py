"""Dünya üssü ekranı: downlink ile gelen `EarthDay` kaydından gün görünümü (gemideki ile aynı render).

Dünya ham veriye hiç sahip olmaz; her şey gemide filtrelenmiş kayıttan kurulur. Gemide hesaplanan
Dünya görünümüyle birebir aynı olduğu test edilir.
"""

from __future__ import annotations

import math

from app.i18n import Lang
from app.models.schemas import DayView, EarthCheckin, EarthCheckinNoteView, EarthCheckinView, EarthDay, StripDay
from app.personal.catalog import PersonalCatalog
from app.personal.checkin_script import TOPIC_BY_KEY
from app.personal.evaluate import DayEvaluation, Reading, TodoItem
from app.personal.view import DayFacts, num, render_day_view, status_label, tx

TEXTS: dict[str, dict[Lang, str]] = {
    "none": {"en": "No completed check-in for this day.", "tr": "Bu gün için tamamlanmış bir check-in yok."},
    "private": {"en": "Check-in completed. The astronaut kept it private.", "tr": "Check-in tamamlandı. Astronot gizli tuttu."},
    "full": {"en": "Shared by the astronaut: everything.", "tr": "Astronotun paylaştığı: her şey."},
    "scores": {
        "en": "Shared by the astronaut: scores only, without their words.",
        "tr": "Astronotun paylaştığı: sadece skorlar, kendi sözleri olmadan.",
    },
    "flagged": {"en": "Flagged", "tr": "İşaretlendi"},
    "no_flag": {"en": "No flag", "tr": "İşaret yok"},
}


def evaluation_from_record(cat: PersonalCatalog, rec: EarthDay) -> DayEvaluation:
    readings = []
    for ind in cat.indicators:
        r = rec.readings.get(ind.col)
        if r is None:
            readings.append(Reading(ind=ind, today=math.nan, used=math.nan, level=0, hidden=True))
        else:
            readings.append(Reading(ind=ind, today=r.today, used=r.used, level=r.level))
    by_col = {r.ind.col: r for r in readings}
    items = []
    for t in rec.todo:
        sol = cat.solution(t.code)
        if sol is None:
            continue
        trig = [by_col[c] for c in t.triggers if c in by_col]
        items.append(TodoItem(solution=sol, triggers=trig, visible=trig))
    return DayEvaluation(
        index=rec.day_index,
        earth=True,
        shared=-1,
        readings=readings,
        items=items,
        ground=rec.ground,
        status=rec.status,
        health_status=rec.health_status,
        main_concern=rec.main_concern,
        behavioral_hidden=rec.behavioral_hidden,
        extra_masked=rec.todo_masked_count,
    )


def earth_day_view(cat: PersonalCatalog, rec: EarthDay, lang: Lang) -> DayView:
    facts = DayFacts(
        astronaut_id=rec.astronaut_id, index=rec.day_index, n_days=rec.n_days, mission_day=rec.mission_day,
        health_status=rec.health_status, cumulative_score=rec.cumulative_score, daily_score=rec.daily_score,
        main_concern=rec.main_concern, area_scores=rec.area_scores,
    )
    share = rec.checkin.share if rec.checkin else None
    done = frozenset(t.code for t in rec.todo if t.done)
    return render_day_view(cat, facts, evaluation_from_record(cat, rec), lang, share=share, done_codes=done)


def earth_strip(cat: PersonalCatalog, recs: list[EarthDay], lang: Lang) -> list[StripDay]:
    out = []
    for rec in sorted(recs, key=lambda r: r.day_index):
        label = status_label(cat, rec.status, lang)
        score = num(rec.cumulative_score, 0, lang)
        out.append(
            StripDay(
                day=rec.day_index + 1, mission_day=rec.mission_day, status=rec.status, status_label=label,
                score=rec.cumulative_score, score_text=score, daily_score=rec.daily_score,
                label=tx("strip_label", lang, day=rec.day_index + 1, status=label, score=score),
            )
        )
    return out


def earth_checkin_view(checkin: EarthCheckin | None, lang: Lang) -> EarthCheckinView:
    """Prototipteki renderCheckin() Dünya dalı."""
    if checkin is None:
        return EarthCheckinView(share=None, text=TEXTS["none"][lang], notes=[])
    if checkin.share == "private":
        return EarthCheckinView(share="private", text=TEXTS["private"][lang], notes=[])
    full = checkin.share == "full"
    notes = []
    for n in checkin.notes:
        topic = TOPIC_BY_KEY[n.topic_key].name[lang] if n.topic_key in TOPIC_BY_KEY else n.topic_key
        notes.append(
            EarthCheckinNoteView(
                topic=topic,
                text=n.text if full else None,
                flag=n.flag,
                flag_text="" if full else TEXTS["flagged" if n.flag else "no_flag"][lang],
            )
        )
    return EarthCheckinView(share=checkin.share, text=TEXTS[checkin.share][lang], notes=notes)
