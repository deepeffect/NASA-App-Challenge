"""Yeni veri modeli (astronaut_health) için LLM tool'ları — "Asistana sor" (gemi, /api/chat).

Tool'lar SADECE giriş yapan astronotun verisine erişir: argüman modellerinde astronot kimliği yoktur,
astronot her zaman `ToolContext.astronaut_id`'den (token'dan) gelir. Sayılar değerlendirme kurallarının
(app/personal/evaluate.py) çıktısıdır; LLM bunları aynen aktarır (CLAUDE.md kural 1).
Gizli ölçümler (ruh hali, stres) astronotun kendisine açıktır; sohbet gemiden çıkmaz.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlmodel import Session

from app.llm.tools import SearchDocsArgs, ToolContext, ToolRegistry, ToolSpec, search_docs
from app.personal.catalog import load_personal_catalog
from app.personal.dataset import AstronautSeries
from app.personal.evaluate import absent_indicators, evaluate_day, readings_for_day
from app.personal.store import personal_data
from app.personal.view import build_day_view, normal_text, tx, value_text

# Seviyenin anlamı: sabit aralıklı veri seti / seviyesi veri setindeki kural motorundan gelen veri seti
LEVEL_RANGE = ["in healthy range", "in caution range", "outside caution range"]
LEVEL_ENGINE = ["no flag (green)", "warning flag (yellow)", "critical flag (red)"]


class NoArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")  # model astronaut_id gönderse bile yok sayılır


class RecentReadingsArgs(NoArgs):
    cols: list[str] | None = Field(None, description="Reading columns, e.g. ['beh_sleep_h']. Empty → readings that are out of range today")
    days: int = Field(7, ge=1, le=30, description="How many recent days")


class TodoArgs(NoArgs):
    day: int | None = Field(None, ge=1, description="Day number 1..N (default: today)")


class SolutionArgs(NoArgs):
    code: str | None = Field(None, description="Self-care solution code, e.g. PROTECT_SLEEP. Empty → all solutions")


def _series(ctx: ToolContext, session: Session) -> AstronautSeries:
    series = personal_data(session.get_bind()).series(session, ctx.astronaut_id)  # type: ignore[arg-type]
    if series is None:
        raise ValueError("no data for the logged-in astronaut")
    return series


def _reading_dict(r, lang: str) -> dict[str, Any]:  # noqa: ANN001
    out = {
        "col": r.ind.col,
        "label": r.ind.label.get(lang),
        "unit": r.ind.unit.get(lang),
        "value": round(r.used, r.ind.dec),
        "value_text": value_text(r, lang),  # type: ignore[arg-type]
        "averaged_3_days": r.averaged,
        "level": r.level,
    }
    if r.ind.scale_max:
        out["scale"] = f"self-report score, 1 (lowest) to {r.ind.scale_max} (highest)"
    if r.normal is not None:
        # Seviye ve normal metni veri setinden (kural motoru, kişisel taban ya da referans): katalog aralığı verilmez
        out["level_meaning"] = LEVEL_ENGINE[r.level]
        out["normal"] = normal_text(r, lang)  # type: ignore[arg-type]
    else:
        out["level_meaning"] = LEVEL_RANGE[r.level]
        out["healthy_min"] = r.ind.healthy.min
        out["healthy_max"] = r.ind.healthy.max
    return out


def _absent_dict(cat, series: AstronautSeries, i: int, lang: str) -> list[dict[str, Any]]:  # noqa: ANN001
    """Bu veri setinde olmayan ölçümler: model 'ölçülmedi' diyebilsin, değer uydurmasın."""
    absent = absent_indicators(cat, series, i)
    return [
        {"col": ind.col, "label": series.info.effective(ind).label.get(lang), "status": tx(f"absent_{absent[ind.col]}", lang)}  # type: ignore[arg-type]
        for ind in cat.indicators
        if ind.col in absent
    ]


def get_today_summary(ctx: ToolContext, session: Session, _args: NoArgs) -> dict[str, Any]:
    cat = load_personal_catalog()
    series = _series(ctx, session)
    i = series.today_index
    v = build_day_view(cat, series, i, ctx.lang)  # type: ignore[arg-type]
    ev = evaluate_day(cat, series, i)
    out = {
        "astronaut_id": series.meta.id,
        "day": v.day,
        "n_days": v.n_days,
        "mission_day": v.mission_day,
        "mission": cat.missions[series.meta.mission].get(ctx.lang),  # type: ignore[arg-type]
        "status": v.status_label,
        "status_level": v.status,
        "summary": v.subtitle,
        "needs_ground_support": v.ground,
        "main_concern": v.main_concern_label,
        "out_of_range_readings": [_reading_dict(r, ctx.lang) for r in ev.readings if r.level > 0],
        "todo": [t.title for t in v.todo],
        "thresholds_note": v.threshold_note,
    }
    if v.score is not None:
        out["health_score"] = round(v.score, 1)
        out["area_scores"] = {a.label: round(a.score, 1) for a in v.areas if a.score is not None}
    else:
        out["scores"] = v.scores_note  # bu veri setinde skor yok: model skor söylemez
    if v.source_note:
        out["data_source"] = v.source_note
    absent = _absent_dict(cat, series, i, ctx.lang)
    if absent:
        out["not_available"] = absent
    return out


def get_recent_readings(ctx: ToolContext, session: Session, args: RecentReadingsArgs) -> dict[str, Any]:
    cat = load_personal_catalog()
    series = _series(ctx, session)
    i = series.today_index
    cols = args.cols or [r.ind.col for r in readings_for_day(cat, series, i) if r.level > 0]
    unknown = [c for c in cols if cat.indicator(c) is None]
    if unknown:
        raise ValueError(f"unknown reading columns {unknown}. Known: {cat.columns}")
    start = max(0, i - args.days + 1)
    out = []
    for c in cols:
        ind = series.info.effective(cat.indicator(c))  # type: ignore[arg-type]
        points = []
        for k in range(start, i + 1):
            r = next((x for x in readings_for_day(cat, series, k) if x.ind.col == c), None)
            if r is not None:  # o gün ölçülmediyse nokta yok
                points.append({"day": k + 1, "mission_day": series.days[k].mission_day, **_reading_dict(r, ctx.lang)})
        entry: dict[str, Any] = {"col": c, "label": ind.label.get(ctx.lang), "points": points}  # type: ignore[arg-type]
        if not points:
            entry["status"] = tx(f"absent_{series.info.absent.get(c, 'not_measured')}", ctx.lang)  # type: ignore[arg-type]
        out.append(entry)
    return {"astronaut_id": series.meta.id, "days": args.days, "readings": out}


def get_todo(ctx: ToolContext, session: Session, args: TodoArgs) -> dict[str, Any]:
    cat = load_personal_catalog()
    series = _series(ctx, session)
    day = args.day or len(series.days)
    if not 1 <= day <= len(series.days):
        raise ValueError(f"day must be between 1 and {len(series.days)}")
    v = build_day_view(cat, series, day - 1, ctx.lang)  # type: ignore[arg-type]
    return {
        "astronaut_id": series.meta.id,
        "day": day,
        "todo": [{"code": t.code, "title": t.title, "why": t.why, "steps": t.steps, "contact_ground_if": t.contact_ground_if} for t in v.todo],
        "ground_support": v.ground_text,
        "nothing_to_do": v.calm_text,
    }


def get_selfcare_solutions(ctx: ToolContext, session: Session, args: SolutionArgs) -> dict[str, Any]:  # noqa: ARG001
    cat = load_personal_catalog()
    sols = [s for s in cat.solutions if args.code in (None, s.code)]
    if not sols:
        raise ValueError(f"unknown solution code '{args.code}'. Known: {[s.code for s in cat.solutions]}")
    lang = ctx.lang
    return {
        "note": "Self-care steps are illustrative for a prototype and are not medical guidance.",
        "solutions": [
            {"code": s.code, "title": s.title.get(lang), "when": s.when.get(lang), "steps": s.do_yourself.get(lang),  # type: ignore[arg-type]
             "contact_ground_if": s.contact_ground_if.get(lang), "basis": s.basis.get(lang)}  # type: ignore[arg-type]
            for s in sols
        ],
    }


PERSONAL_TOOLS: list[ToolSpec] = [
    ToolSpec("get_today_summary", "Today's health status of the logged-in astronaut: status, score, out-of-range readings, to-do.",
             NoArgs, get_today_summary),
    ToolSpec("get_recent_readings", "Recent daily readings (evaluated value and level) of the logged-in astronaut.",
             RecentReadingsArgs, get_recent_readings),
    ToolSpec("get_todo", "The to-do (self-care items) of a day with the readings that triggered them and the steps.",
             TodoArgs, get_todo),
    ToolSpec("get_selfcare_solutions", "Self-care solutions (steps, when to contact ground). Optionally one code.",
             SolutionArgs, get_selfcare_solutions),
    ToolSpec("search_docs", "Search onboard reference documents (NASA standards, procedures). Returns file/section references.",
             SearchDocsArgs, search_docs),
]


def personal_registry() -> ToolRegistry:
    return ToolRegistry(PERSONAL_TOOLS)
