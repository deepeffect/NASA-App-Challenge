"""Gün görünümü: değerlendirme + TR/EN metinler → API sözleşmesi (`DayView`, `StripDay`).

İngilizce metinler prototipteki render() çıktısıyla birebir aynıdır (golden test). Türkçe metinler
aynı yapıdadır; sayılarda ondalık virgül kullanılır.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.i18n import Lang
from app.models.schemas import AreaScoreView, DayView, ReadingView, StripDay, TodoItemView
from app.personal.catalog import Indicator, PersonalCatalog
from app.personal.dataset import AstronautSeries, DatasetInfo
from app.personal.derive import derive
from app.personal.evaluate import (
    NO_CHECKIN,
    SHARE_LEVELS,
    DayEvaluation,
    Reading,
    TodoItem,
    absent_indicators,
    evaluate_day,
    js_num,
    readings_for_day,
    shown_status,
    to_fixed,
    visible_ground,
)

TEXTS: dict[str, dict[Lang, str]] = {
    "sub_far_out": {"en": "One reading is far out of range", "tr": "Bir ölçüm aralığın çok dışında"},
    "sub_out": {"en": "One reading is out of range", "tr": "Bir ölçüm aralığın dışında"},
    "sub_concern": {"en": "Main concern: {area}", "tr": "Ana endişe: {area}"},
    "sub_things_1": {"en": "1 small thing to look at", "tr": "Bakılacak 1 küçük şey"},
    "sub_things_n": {"en": "{n} small things to look at", "tr": "Bakılacak {n} küçük şey"},
    "sub_nothing": {"en": "Nothing to do today", "tr": "Bugün yapılacak bir şey yok"},
    "behavioral_unshared": {
        "en": "Behavioral area (details not shared)",
        "tr": "Davranışsal alan (ayrıntı paylaşılmadı)",
    },
    "day_label": {"en": "Day {day} of {n} · mission day {md}", "tr": "{n} günün {day}. günü · görev günü {md}"},
    "strip_label": {"en": "Day {day}: {status}, score {score}", "tr": "Gün {day}: {status}, skor {score}"},
    "strip_label_noscore": {"en": "Day {day}: {status}", "tr": "Gün {day}: {status}"},
    "no_scores": {"en": "This dataset has no scores.", "tr": "Bu veri setinde skor yok."},
    "absent_not_measured": {"en": "Not measured on this mission", "tr": "Bu görevde ölçülmedi"},
    "absent_not_in_file": {"en": "Not in this data file", "tr": "Bu veri dosyasında yok"},
    "why_item_normal": {"en": "{label} {value}{unit}, normal: {normal}", "tr": "{label} {value}{unit}, normal: {normal}"},
    "todo_title_astro": {"en": "To do", "tr": "Yapılacaklar"},
    "todo_title_earth": {"en": "Advice shown to the astronaut", "tr": "Astronota gösterilen öneriler"},
    "calm_astro": {
        "en": "Nothing needed. Carry on with routine exercise, sleep and check-ins.",
        "tr": "Yapılacak bir şey yok. Rutin egzersize, uykuya ve check-in'lere devam edin.",
    },
    "calm_earth": {"en": "Nothing needed on this day.", "tr": "Bu gün için bir şey gerekmiyor."},
    "ground_title_astro": {"en": "Tell ground control.", "tr": "Yer kontrolüne bildirin."},
    "ground_title_earth": {"en": "Flagged for ground support.", "tr": "Yer desteği için işaretlendi."},
    "ground_text": {
        "en": "At least one reading is too far out for self-care alone.",
        "tr": "En az bir ölçüm, yalnızca öz bakımla ele alınamayacak kadar aralığın dışında.",
    },
    "why_item": {"en": "{label} {value}{unit}, healthy {range}", "tr": "{label} {value}{unit}, sağlıklı aralık {range}"},
    "why_dataset": {"en": "Suggested by the dataset", "tr": "Veri setinin önerisi"},
    "masked_1": {
        "en": "1 more item is not shown: based on mood or stress readings the astronaut has not shared.",
        "tr": "1 öğe daha gösterilmiyor: astronotun paylaşmadığı ruh hali veya stres ölçümlerine dayanıyor.",
    },
    "masked_n": {
        "en": "{n} more items are not shown: based on mood or stress readings the astronaut has not shared.",
        "tr": "{n} öğe daha gösterilmiyor: astronotun paylaşmadığı ruh hali veya stres ölçümlerine dayanıyor.",
    },
    "not_shared": {"en": "Not shared", "tr": "Paylaşılmadı"},
    "flag_1": {"en": "Out of range", "tr": "Aralık dışında"},
    "flag_2": {"en": "Far out", "tr": "Çok dışında"},
    "range_open": {"en": "{min} or higher", "tr": "{min} veya üzeri"},
    "range": {"en": "{min} to {max}", "tr": "{min}–{max}"},
    "readings_note": {
        "en": "Health readings show the average of the last 3 days. Radiation and cabin CO2 show that day's value.",
        "tr": "Sağlık ölçümleri son 3 günün ortalamasını gösterir. Radyasyon ve kabin CO2'si o günün değeridir.",
    },
    "privnote_astro": {
        "en": "Mood and stress stay on your device unless you share that day's check-in with Earth.",
        "tr": "Ruh hali ve stres, o günün check-in'ini Dünya ile paylaşmadıkça gemide kalır.",
    },
    "privnote_earth": {
        "en": "Mood and stress show only on days the astronaut shared their check-in.",
        "tr": "Ruh hali ve stres sadece astronotun check-in'ini paylaştığı günlerde görünür.",
    },
}


def tx(key: str, lang: Lang, **kw: object) -> str:
    s = TEXTS[key][lang]
    return s.format(**kw) if kw else s


# ============================================================================ biçimlendirme
def num(v: float, dec: int, lang: Lang) -> str:
    s = to_fixed(v, dec)
    return s.replace(".", ",") if lang == "tr" else s


def num_plain(v: float, lang: Lang) -> str:
    s = js_num(v)
    return s.replace(".", ",") if lang == "tr" else s


def range_text(ind: Indicator, lang: Lang) -> str:
    """Prototip rangeText (sağlıklı aralık)."""
    lo = num_plain(ind.healthy.min, lang)
    if ind.healthy.max is None:
        return tx("range_open", lang, min=lo)
    return tx("range", lang, min=lo, max=num_plain(ind.healthy.max, lang))


def unit_text(ind: Indicator, lang: Lang) -> str:
    """Prototip unitText: rakamla başlayan birim (0-10, 1-10) yazılmaz; TR'de '/saat' boşluksuz."""
    unit = ind.unit.get(lang)
    if unit[:1].isdigit():
        return ""
    if lang == "tr" and unit.startswith("/"):
        return unit
    return " " + unit


def area_label(cat: PersonalCatalog, area: str, lang: Lang) -> str:
    return cat.domains[area].get(lang)


def lower(s: str, lang: Lang) -> str:
    if lang == "tr":
        s = s.replace("I", "ı").replace("İ", "i")
    return s.lower()


# ============================================================================ parçalar
def subtitle(cat: PersonalCatalog, ev: DayEvaluation, lang: Lang, engine_levels: bool = False) -> str:
    if ev.status:
        if ev.main_concern == "none":
            # Seviyesi veriden gelen veri setinde ana endişesiz "Dikkat" bir ortam ölçümünün SARI olmasıdır:
            # "çok dışında" denmez (o metin kırmızı / yer desteği içindir)
            if engine_levels and not any(r.level == 2 and not r.hidden for r in ev.readings):
                return tx("sub_out", lang)
            return tx("sub_far_out", lang)
        return tx("sub_concern", lang, area=lower(concern_label(cat, ev, lang), lang))
    n = len(ev.visible_items)
    if n == 0:
        return tx("sub_nothing", lang)
    return tx("sub_things_1", lang) if n == 1 else tx("sub_things_n", lang, n=n)


def concern_label(cat: PersonalCatalog, ev: DayEvaluation, lang: Lang) -> str:
    if ev.main_concern == "behavioral" and ev.behavioral_hidden:
        return tx("behavioral_unshared", lang)
    return area_label(cat, ev.main_concern, lang)


def value_text(r: Reading, lang: Lang) -> str:
    """Değerin ekrandaki yazılışı: verideki yazılış (ör. "116/82") > ölçekli ("3/5") > biçimli sayı."""
    if r.text is not None:
        return r.text
    s = num(r.used, r.ind.dec, lang)
    return f"{s}/{r.ind.scale_max}" if r.ind.scale_max else s


def normal_text(r: Reading, lang: Lang) -> str:
    """Aralık sütunu: verideki normal metni (kişisel taban ya da referans); yoksa katalogdaki sağlıklı aralık."""
    if r.normal is not None:
        return r.normal.get(lang) or r.normal.get("en") or ""
    return range_text(r.ind, lang)


def why_text(item: TodoItem, lang: Lang) -> str:
    if item.from_dataset:
        return tx("why_dataset", lang)
    return " · ".join(
        tx(
            "why_item_normal" if r.normal is not None else "why_item",
            lang,
            label=r.ind.label.get(lang),
            value=value_text(r, lang),
            unit=unit_text(r.ind, lang),
            range=range_text(r.ind, lang),
            normal=normal_text(r, lang),
        )
        for r in item.visible
    )


def reading_view(r: Reading, lang: Lang) -> ReadingView:
    ind = r.ind
    return ReadingView(
        col=ind.col,
        domain=ind.domain,
        label=ind.label.get(lang),
        unit=ind.unit.get(lang),
        dec=ind.dec,
        value=None if r.hidden else r.used,
        today=None if r.hidden else r.today,
        value_text=tx("not_shared", lang) if r.hidden else value_text(r, lang),
        # Gizli bir ölçümün kişisel tabanı da gizlidir (verideki normal metni); katalog aralığı herkese açıktır
        healthy_text="" if r.hidden and r.normal is not None else normal_text(r, lang),
        level=None if r.hidden else r.level,
        flag_text="" if r.hidden or r.level == 0 else tx(f"flag_{r.level}", lang),
        averaged=r.averaged,
        private=ind.private,
        hidden=r.hidden,
    )


def absent_view(ind: Indicator, reason: str, lang: Lang) -> ReadingView:
    """Bu veri setinde olmayan ölçüm: değer ve seviye yok, nedenini metin söyler (kırmızıya dönüşmez)."""
    return ReadingView(
        col=ind.col,
        domain=ind.domain,
        label=ind.label.get(lang),
        unit=ind.unit.get(lang),
        dec=ind.dec,
        value=None,
        today=None,
        value_text=tx(f"absent_{reason}", lang),
        healthy_text="",
        level=None,
        flag_text="",
        averaged=False,
        private=ind.private,
        hidden=False,
        measured=False,
    )


def todo_view(item: TodoItem, lang: Lang, done: bool = False) -> TodoItemView:
    sol = item.solution
    return TodoItemView(
        code=sol.code,
        title=sol.title.get(lang),
        why=why_text(item, lang),
        source="dataset" if item.from_dataset else "readings",
        triggers=[r.ind.col for r in item.visible],
        steps=sol.do_yourself.get(lang),
        when=sol.when.get(lang),
        contact_ground_if=sol.contact_ground_if.get(lang),
        basis=sol.basis.get(lang),
        done=done,
    )


def status_label(cat: PersonalCatalog, status: int, lang: Lang) -> str:
    return cat.statuses[status].get(lang)


# ============================================================================ görünümler
@dataclass(frozen=True)
class DayFacts:
    """Görünümün veriden okunan kısmı (gemide veri setinden, Dünya'da downlink kaydından)."""

    astronaut_id: str
    index: int
    n_days: int
    mission_day: int
    health_status: int
    cumulative_score: float | None
    daily_score: float | None
    main_concern: str
    area_scores: dict[str, float]  # Dünya'da paylaşılmamış davranışsal alan yoktur
    info: DatasetInfo = field(default_factory=DatasetInfo)
    absent: dict[str, str] = field(default_factory=dict)  # bu günde olmayan kolon → neden


def build_day_view(
    cat: PersonalCatalog,
    series: AstronautSeries,
    i: int,
    lang: Lang,
    earth: bool = False,
    shared: int = NO_CHECKIN,
    share: str | None = None,
    done_codes: frozenset[str] = frozenset(),
) -> DayView:
    ev = evaluate_day(cat, series, i, earth=earth, shared=shared)
    day = series.days[i]
    facts = DayFacts(
        astronaut_id=series.meta.id, index=i, n_days=len(series.days), mission_day=day.mission_day,
        # Durum ve ana endişe değerlendirmeden: Dünya görünümünde sadece görünür ölçümlerden türetilmiş olabilir
        health_status=ev.health_status, cumulative_score=day.cumulative_score, daily_score=day.daily_score,
        main_concern=ev.main_concern, area_scores=day.area_scores,
        info=series.info, absent=absent_indicators(cat, series, i),
    )
    return render_day_view(cat, facts, ev, lang, share=share, done_codes=done_codes)


def render_day_view(
    cat: PersonalCatalog,
    facts: DayFacts,
    ev: DayEvaluation,
    lang: Lang,
    share: str | None = None,
    done_codes: frozenset[str] = frozenset(),
) -> DayView:
    i, n = facts.index, facts.n_days
    info = facts.info
    visible = ev.visible_items
    masked = ev.masked_count
    who = "earth" if ev.earth else "astro"
    areas = []
    for area in cat.areas if info.has_scores else ():
        hidden = area == "behavioral" and ev.behavioral_hidden
        score = None if hidden else facts.area_scores[area]
        areas.append(
            AreaScoreView(
                area=area,
                label=area_label(cat, area, lang),
                score=score,
                score_text=tx("not_shared", lang) if score is None else num(score, 0, lang),
                hidden=hidden,
                main_concern=facts.main_concern == area,
            )
        )
    # Ölçümler katalog sırasıyla: ölçülenler + bu veri setinde olmayanlar (nedeniyle)
    by_col = {r.ind.col: r for r in ev.readings}
    readings = []
    for ind in cat.indicators:
        if ind.col in by_col:
            readings.append(reading_view(by_col[ind.col], lang))
        elif ind.col in facts.absent:
            readings.append(absent_view(info.effective(ind), facts.absent[ind.col], lang))
    return DayView(
        astronaut_id=facts.astronaut_id,
        viewer="earth" if ev.earth else "astronaut",
        day=i + 1,
        n_days=n,
        mission_day=facts.mission_day,
        is_today=i == n - 1,
        day_label=tx("day_label", lang, day=i + 1, n=n, md=facts.mission_day),
        status=ev.status,
        status_label=status_label(cat, ev.status, lang),
        health_status=facts.health_status,
        ground=ev.ground,
        subtitle=subtitle(cat, ev, lang, engine_levels=info.levels_from_data),
        score=facts.cumulative_score,
        score_text=score_text(facts.cumulative_score, lang),
        daily_score=facts.daily_score,
        main_concern=facts.main_concern,
        main_concern_label=None if facts.main_concern == "none" else concern_label(cat, ev, lang),
        areas=areas,
        readings=readings,
        todo_title=tx(f"todo_title_{who}", lang),
        todo=[todo_view(x, lang, x.code in done_codes) for x in visible],
        todo_masked_count=masked,
        todo_masked_text=None if not masked else (tx("masked_1", lang) if masked == 1 else tx("masked_n", lang, n=masked)),
        calm_text=tx(f"calm_{who}", lang) if not visible and not masked else None,
        ground_title=tx(f"ground_title_{who}", lang) if ev.ground else None,
        ground_text=tx("ground_text", lang) if ev.ground else None,
        readings_note=(info.readings_note.get(lang) if info.readings_note else tx("readings_note", lang)) + " " + tx(f"privnote_{who}", lang),
        threshold_note=(info.threshold_note or cat.threshold_note).get(lang),
        share=share,  # type: ignore[arg-type]
        scores_note=scores_note(info, lang),
        range_label=info.range_label.get(lang) if info.range_label else None,
        source_note=info.source_note.get(lang) if info.source_note else None,
    )


def score_text(score: float | None, lang: Lang) -> str:
    return "" if score is None else num(score, 0, lang)


def scores_note(info: DatasetInfo, lang: Lang) -> str | None:
    """Skoru olmayan veri setinde skor grafiğinin yerine gösterilen not."""
    return None if info.has_scores else tx("no_scores", lang)


def strip_label(day: int, status: str, score: str, lang: Lang) -> str:
    if not score:
        return tx("strip_label_noscore", lang, day=day, status=status)
    return tx("strip_label", lang, day=day, status=status, score=score)


def strip_status(cat: PersonalCatalog, series: AstronautSeries, k: int, earth: bool, shared: int) -> int:
    day = series.days[k]
    if not earth:
        return shown_status(day.health_status, day.needs_ground_support)
    rd = readings_for_day(cat, series, k, earth=True, shared=shared)
    health_status = day.health_status
    if series.info.levels_from_data:  # türetilmiş durum: Dünya için sadece görünür ölçümlerden (bkz. evaluate_day)
        health_status = derive(cat, {r.ind.col: r.level for r in rd if not r.hidden}).health_status
    return shown_status(health_status, visible_ground(rd))


def build_strip(
    cat: PersonalCatalog, series: AstronautSeries, lang: Lang, earth: bool = False, shared_by_day: dict[int, int] | None = None
) -> list[StripDay]:
    shared_by_day = shared_by_day or {}
    out = []
    for k, day in enumerate(series.days):
        st = strip_status(cat, series, k, earth, shared_by_day.get(k, NO_CHECKIN))
        label = status_label(cat, st, lang)
        score = score_text(day.cumulative_score, lang)
        out.append(
            StripDay(
                day=k + 1,
                mission_day=day.mission_day,
                status=st,
                status_label=label,
                score=day.cumulative_score,
                score_text=score,
                daily_score=day.daily_score,
                label=strip_label(k + 1, label, score, lang),
            )
        )
    return out


def share_rank(level: str | None) -> int:
    """Paylaşım seviyesi → sayı (tamamlanmış check-in yoksa -1)."""
    return NO_CHECKIN if level is None else SHARE_LEVELS[level]
