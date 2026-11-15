"""Kişisel sağlık servisleri (gemi): genel bakış, gün görünümü, katalog."""

from __future__ import annotations

from sqlmodel import Session

from app.config import Settings
from app.errors import ApiError
from app.i18n import Lang, t
from app.models.schemas import (
    CatalogDomain,
    CatalogIndicator,
    CatalogRange,
    CatalogSolution,
    CrewInfo,
    DayView,
    PersonalCatalogResponse,
    PersonalOverview,
)
from app.models.tables import ActionDone
from app.personal.catalog import PersonalCatalog, load_personal_catalog
from app.personal.dataset import AstronautMeta, AstronautSeries
from app.personal.store import PersonalData
from app.personal.view import build_day_view, build_strip, range_text


def crew_info(cat: PersonalCatalog, meta: AstronautMeta, first_day: int, last_day: int, n_days: int, lang: Lang) -> CrewInfo:
    return CrewInfo(
        id=meta.id,
        age=meta.age,
        sex=meta.sex,
        bmi=meta.bmi,
        mission=meta.mission,
        mission_label=cat.missions[meta.mission].get(lang),
        profile=meta.profile,
        profile_label=cat.profiles[meta.profile].get(lang),
        first_mission_day=first_day,
        last_mission_day=last_day,
        n_days=n_days,
    )


def series_crew_info(cat: PersonalCatalog, series: AstronautSeries, lang: Lang) -> CrewInfo:
    return crew_info(cat, series.meta, series.days[0].mission_day, series.days[-1].mission_day, len(series.days), lang)


def get_series(data: PersonalData, session: Session, astronaut_id: str, lang: Lang) -> AstronautSeries:
    series = data.series(session, astronaut_id)
    if series is None:
        raise ApiError(404, "unknown_astronaut", t("unknown_astronaut", lang, id=astronaut_id))
    return series


def day_index(n_days: int, day: int, lang: Lang) -> int:
    if not 1 <= day <= n_days:
        raise ApiError(404, "unknown_day", t("unknown_day", lang, day=day, n=n_days))
    return day - 1


def overview(series: AstronautSeries, lang: Lang) -> PersonalOverview:
    cat = load_personal_catalog()
    return PersonalOverview(
        astronaut=series_crew_info(cat, series, lang),
        today=len(series.days),
        n_days=len(series.days),
        strip=build_strip(cat, series, lang),
        threshold_note=cat.threshold_note.get(lang),
    )


def astronaut_day(
    series: AstronautSeries, day: int, lang: Lang, share: str | None = None, done_codes: frozenset[str] = frozenset()
) -> DayView:
    cat = load_personal_catalog()
    i = day_index(len(series.days), day, lang)
    return build_day_view(cat, series, i, lang, share=share, done_codes=done_codes)


def catalog_response(lang: Lang) -> PersonalCatalogResponse:
    cat = load_personal_catalog()
    return PersonalCatalogResponse(
        statuses=[s.get(lang) for s in cat.statuses],
        domains=[CatalogDomain(id=k, label=v.get(lang)) for k, v in cat.domains.items()],
        areas=list(cat.areas),
        indicators=[
            CatalogIndicator(
                col=i.col,
                domain=i.domain,
                domain_label=cat.domains[i.domain].get(lang),
                label=i.label.get(lang),
                unit=i.unit.get(lang),
                dec=i.dec,
                healthy=CatalogRange(min=i.healthy.min, max=i.healthy.max),
                warning=CatalogRange(min=i.warning.min, max=i.warning.max),
                healthy_text=range_text(i, lang),
                action=i.action,
                trig=i.trig,
                private=i.private,
                averaged=i.domain != "exposure",
            )
            for i in cat.indicators
        ],
        solutions=[
            CatalogSolution(
                code=s.code,
                domain=s.domain,
                title=s.title.get(lang),
                when=s.when.get(lang),
                steps=s.do_yourself.get(lang),
                contact_ground_if=s.contact_ground_if.get(lang),
                basis=s.basis.get(lang),
            )
            for s in cat.solutions
        ],
        threshold_source=cat.threshold_source,
        verified=cat.verified,
        threshold_note=cat.threshold_note.get(lang),
    )


def mark_action(db: Session, settings: Settings, series: AstronautSeries, code: str, done: bool, lang: Lang) -> None:
    """Bugünün to-do öğesi: işaretle / kaldır → `action.done` olayı (Dünya'da maskeliyse kodsuz)."""
    from app.downlink.outbox import current_earth_day, emit_day_event

    i = series.today_index
    if code not in series.days[i].self_care:
        raise ApiError(400, "action_not_in_todo", t("action_not_in_todo", lang, code=code))
    row = db.get(ActionDone, (series.meta.id, i, code))
    if done == (row is not None):
        return  # zaten bu durumda
    if done:
        db.add(ActionDone(astronaut_id=series.meta.id, day_index=i, code=code))
    else:
        db.delete(row)
    db.flush()
    visible = {x.code for x in current_earth_day(db, series, i).todo}
    masked = code not in visible
    emit_day_event(db, settings, "action.done", series, i, code=None if masked else code, masked=masked, done=done)
    db.commit()
