"""Gizlilik filtresi — GEMİDE uygulanır. Dünya'ya giden her şey buradan geçer.

Kurallar (prototip + kullanıcı kararları):
  - Gizli ölçümler (ruh hali, stres): sadece o günün check-in'i en az `scores` paylaşıldıysa.
  - Diğer bütün ölçümler her zaman.
  - To-do: tetikleyicisi sadece gizli ölçümler olan öğeler maskelenir; kodları gönderilmez, sayıları gider.
  - Ground sadece görünür ölçümlerden hesaplanır; gösterilen durum ve genel sağlık skoru (kümülatif ve
    tek günlük) her zaman gider. Genel skor gizli değildir; gizli olan ruh hali / stres ölçümleri ve
    davranışsal ALAN skorudur.
  - "Uyku, ruh hali ve stres" alan skoru: check-in en az `scores` paylaşılmadıysa gönderilmez.
  - Check-in: yok / private (tamamlandı, gizli) / scores (konu + flag) / full (+ cevap metni).
    Mesajlar, `urgent` ve CMO bildirimi asla gönderilmez.
"""

from __future__ import annotations

from app.models.schemas import EarthAstronaut, EarthCheckin, EarthCheckinNote, EarthDay, EarthReading, EarthTodo
from app.models.tables import CheckinSession
from app.personal.catalog import PersonalCatalog
from app.personal.dataset import AstronautSeries
from app.personal.evaluate import SHARE_LEVELS, evaluate_day


def share_level_of(row: CheckinSession | None) -> str | None:
    """Prototip shareOf(): tamamlanmamışsa None, tamamlandıysa seviye (varsayılan private)."""
    if row is None or not row.done:
        return None
    return row.share or "private"


def earth_checkin(row: CheckinSession | None) -> EarthCheckin | None:
    share = share_level_of(row)
    if share is None:
        return None
    assert row is not None
    if share == "private":
        return EarthCheckin(share="private", notes=[])
    full = share == "full"
    return EarthCheckin(
        share=share,  # type: ignore[arg-type]
        notes=[EarthCheckinNote(topic_key=n["topic_key"], flag=bool(n["flag"]), text=n["text"] if full else None) for n in row.notes],
    )


def earth_astronaut(series: AstronautSeries) -> EarthAstronaut:
    m = series.meta
    return EarthAstronaut(
        id=m.id, age=m.age, sex=m.sex, bmi=m.bmi, mission=m.mission, profile=m.profile,
        first_mission_day=series.days[0].mission_day, last_mission_day=series.days[-1].mission_day, n_days=len(series.days),
    )


def earth_day(
    cat: PersonalCatalog,
    series: AstronautSeries,
    i: int,
    row: CheckinSession | None = None,
    done_codes: frozenset[str] = frozenset(),
) -> EarthDay:
    share = share_level_of(row)
    shared = -1 if share is None else SHARE_LEVELS[share]
    ev = evaluate_day(cat, series, i, earth=True, shared=shared)
    day = series.days[i]
    return EarthDay(
        astronaut_id=series.meta.id,
        day_index=i,
        mission_day=day.mission_day,
        n_days=len(series.days),
        health_status=day.health_status,
        ground=ev.ground,
        status=ev.status,
        cumulative_score=day.cumulative_score,
        daily_score=day.daily_score,
        main_concern=day.main_concern,
        behavioral_hidden=ev.behavioral_hidden,
        area_scores={k: v for k, v in day.area_scores.items() if not (k == "behavioral" and ev.behavioral_hidden)},
        readings={r.ind.col: EarthReading(today=r.today, used=r.used, level=r.level) for r in ev.readings if not r.hidden},
        todo=[EarthTodo(code=x.code, triggers=[r.ind.col for r in x.visible], done=x.code in done_codes) for x in ev.visible_items],
        todo_masked_count=ev.masked_count,
        checkin=earth_checkin(row),
    )
