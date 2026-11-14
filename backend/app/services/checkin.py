"""Check-in servisi (gemi): tur, durum, baştan başla, CMO bildirimi.

Check-in sadece bugün (son kayıt) için yapılır; geçmiş günler salt okunur. Mod: CHECKIN_MODE
(scripted | llm | auto). LLM katmanındaki bir hata akışı asla kilitlemez (auto → scripted).
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from sqlmodel import Session

from app.config import Settings
from app.errors import ApiError
from app.i18n import Lang, t
from app.models.schemas import CheckinMessage, CheckinNext, CheckinNote, CheckinState, CheckinTurnResponse, CmoNotice
from app.models.tables import CheckinSession, CmoNotification, utcnow
from app.personal.catalog import load_personal_catalog
from app.personal.checkin_context import build_context
from app.personal.checkin_script import TOPICS, FlowState, apply_turn, assistant_turn
from app.personal.dataset import AstronautSeries

log = logging.getLogger(__name__)


def load_session(db: Session, astronaut_id: str, day_index: int) -> CheckinSession | None:
    return db.get(CheckinSession, (astronaut_id, day_index))


def share_of(row: CheckinSession | None) -> str | None:
    """Prototip shareOf(): tamamlanmış check-in yoksa None, varsa seviye (varsayılan private)."""
    if row is None or not row.done:
        return None
    return row.share or "private"


def _flow(row: CheckinSession | None, lang: Lang) -> FlowState:
    if row is None:
        return FlowState.initial(lang)
    return FlowState(step=row.step, options=list(row.options), msgs=list(row.messages), notes=list(row.notes), done=row.done, cmo=row.cmo)


def state_view(series: AstronautSeries, day_index: int, row: CheckinSession | None, lang: Lang) -> CheckinState:
    st = _flow(row, lang)
    day = series.days[day_index]
    is_today = day_index == series.today_index
    share = share_of(row)
    return CheckinState(
        astronaut_id=series.meta.id,
        day=day_index + 1,
        mission_day=day.mission_day,
        is_today=is_today,
        editable=is_today and not st.done,
        started=row is not None,
        step=st.step,
        options=[] if st.done or not is_today else st.options,
        messages=[CheckinMessage(**m) for m in st.msgs] if (row is not None or is_today) else [],
        notes=[CheckinNote(**n) for n in st.notes],
        done=st.done,
        share=share,  # type: ignore[arg-type]
        can_reset=is_today and len(st.msgs) > 1 and (share or "private") == "private",
        cmo_notified=st.cmo,
        cmo_notice=CmoNotice(title=t("cmo_title", lang), text=t("cmo_text", lang)) if st.cmo else None,
        completed_at=row.completed_at if row else None,
    )


# auto modda devre kesici: LLM bir kez başarısız olunca bu süre boyunca doğrudan scripted
AUTO_LLM_COOLDOWN_S = 60.0
_llm_down_until: dict[str, float] = {}


async def run_mode(settings: Settings, ctx: dict[str, Any], lang: Lang) -> tuple[dict[str, Any] | None, str]:
    """(tur çıktısı | None, kullanılan mod). None → prototipteki 'That did not go through'."""
    mode = settings.checkin_mode
    if mode == "scripted":
        return assistant_turn(ctx, lang), "scripted"
    key = f"{settings.llm_provider}:{settings.llm_base_url}"
    if mode == "auto" and _llm_down_until.get(key, 0.0) > time.monotonic():
        return assistant_turn(ctx, lang), "scripted"
    from app.llm.client import get_llm_client
    from app.personal.checkin_llm import llm_turn

    try:
        out = await asyncio.wait_for(llm_turn(get_llm_client(settings), ctx, lang), timeout=settings.llm_timeout)
        _llm_down_until.pop(key, None)
        return out, "llm"
    except Exception as e:  # noqa: BLE001 — LLM hatası check-in'i asla kilitlemez
        log.warning("LLM check-in turu başarısız (%s): %s", mode, e)
        if mode == "auto":
            _llm_down_until[key] = time.monotonic() + AUTO_LLM_COOLDOWN_S
            return assistant_turn(ctx, lang), "scripted"
        return None, "llm"


def record_cmo(db: Session, series: AstronautSeries, day_index: int, source: str, topic: str | None, text: str) -> None:
    db.add(
        CmoNotification(
            astronaut_id=series.meta.id,
            day_index=day_index,
            mission_day=series.days[day_index].mission_day,
            source=source,
            topic=topic,
            text=text,
        )
    )


async def turn(db: Session, settings: Settings, series: AstronautSeries, answer: str, lang: Lang) -> CheckinTurnResponse:
    i = series.today_index
    text = answer.strip()
    if not text:
        raise ApiError(400, "empty_answer", t("empty_answer", lang))
    row = load_session(db, series.meta.id, i)
    if row is not None and row.done:
        raise ApiError(409, "checkin_done", t("checkin_done", lang))
    st = _flow(row, lang)
    cat = load_personal_catalog()
    ctx = build_context(cat, series, i, lang, [*st.msgs, {"who": "me", "text": text}], st.step, text)
    out, mode = await run_mode(settings, ctx, lang)
    was_done = st.done
    apply_turn(st, text, out, lang)

    if row is None:
        row = CheckinSession(astronaut_id=series.meta.id, day_index=i, mission_day=series.days[i].mission_day, lang=lang)
    row.step, row.options, row.messages, row.notes = st.step, st.options, st.msgs, st.notes
    row.done, row.cmo = st.done, st.cmo
    row.modes = [*row.modes, mode]
    row.updated_at = utcnow()
    if out and out["note"] and out["note"]["urgent"]:
        record_cmo(db, series, i, "checkin", out["note"]["topic_key"], text)
    if st.done and not was_done:
        row.completed_at = utcnow()
    db.add(row)
    db.flush()
    if st.done and not was_done:
        on_checkin_completed(db, series, row)
    db.commit()
    db.refresh(row)

    if out is None:
        reply, note, nxt, done = st.msgs[-1]["text"], None, CheckinNext(text=TOPICS[st.step].q[lang], options=st.options), False
    else:
        reply = out["reply"]
        note = CheckinNote(**out["note"]) if out["note"] else None
        nxt = CheckinNext(**out["next"]) if out["next"] else None
        done = out["done"]
    return CheckinTurnResponse(reply=reply, note=note, next=nxt, done=done, checkin=state_view(series, i, row, lang))


def reset(db: Session, series: AstronautSeries, lang: Lang) -> CheckinState:
    """'Baştan başla': sadece paylaşım private iken (prototip). CMO kayıtları silinmez."""
    i = series.today_index
    row = load_session(db, series.meta.id, i)
    if row is not None:
        if (share_of(row) or "private") != "private":
            raise ApiError(409, "reset_locked", t("reset_locked", lang))
        was_done = row.done
        db.delete(row)
        db.flush()
        if was_done:
            on_checkin_reset(db, series, i)
        db.commit()
    return state_view(series, i, None, lang)


# ---------------------------------------------------------------- downlink kancaları (7. bölüm)
def on_checkin_completed(db: Session, series: AstronautSeries, row: CheckinSession) -> None:
    """Check-in tamamlandı: Dünya'ya gidecek olay (gizlilik filtresinden geçmiş) outbox'a yazılır."""


def on_checkin_reset(db: Session, series: AstronautSeries, day_index: int) -> None:
    """Tamamlanmış (private) check-in silindi: Dünya görünümü güncellenir."""
