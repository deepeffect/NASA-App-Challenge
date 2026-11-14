"""Dil seçimi ve kullanıcıya dönen kısa metinler (TR/EN).

Öncelik: açık `lang` parametresi (sorgu veya gövde) > `Accept-Language` başlığı > Türkçe.
Frontend dil seçimini her zaman `lang` ile açıkça gönderir; başlık sadece yedektir.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import Depends, Query, Request

Lang = Literal["tr", "en"]
SUPPORTED: tuple[Lang, ...] = ("tr", "en")
DEFAULT_LANG: Lang = "tr"


def parse_accept_language(header: str | None) -> Lang | None:
    """`en-US,en;q=0.9,tr;q=0.8` → desteklenen en yüksek ağırlıklı dil (yoksa None)."""
    if not header:
        return None
    best: tuple[float, int, Lang] | None = None
    for pos, part in enumerate(header.split(",")):
        piece = part.strip()
        if not piece:
            continue
        tag, _, params = piece.partition(";")
        q = 1.0
        for p in params.split(";"):
            k, _, v = p.strip().partition("=")
            if k == "q":
                try:
                    q = float(v)
                except ValueError:
                    q = 0.0
        primary = tag.strip().lower().split("-")[0]
        if primary in SUPPORTED and q > 0:
            cand = (q, -pos, primary)  # eşit ağırlıkta önce yazılan kazanır
            if best is None or cand > best:
                best = cand  # type: ignore[assignment]
    return best[2] if best else None


def resolve_lang(explicit: str | None, accept_language: str | None) -> Lang:
    if explicit:
        e = explicit.strip().lower().split("-")[0]
        if e in SUPPORTED:
            return e  # type: ignore[return-value]
    return parse_accept_language(accept_language) or DEFAULT_LANG


def get_lang(
    request: Request,
    lang: Annotated[Lang | None, Query(description="Cevap dili; boşsa Accept-Language, o da yoksa tr")] = None,
) -> Lang:
    """FastAPI dependency: `?lang=` > Accept-Language > tr."""
    return resolve_lang(lang, request.headers.get("accept-language"))


LangDep = Annotated[Lang, Depends(get_lang)]


# ----------------------------------------------------------------------------- metinler
MESSAGES: dict[str, dict[Lang, str]] = {
    "earth_read_only": {
        "tr": "Dünya üssü salt okunurdur; bu istasyonda değişiklik yapılamaz.",
        "en": "The Earth base is read-only; nothing can be changed at this station.",
    },
    "not_on_station": {
        "tr": "Bu özellik bu istasyonda yok.",
        "en": "This feature is not available at this station.",
    },
    # ---- giriş (prototip metinlerinden)
    "login_empty_id": {"tr": "Bir kimlik girin.", "en": "Enter an ID."},
    "login_unknown_id_ship": {
        "tr": "{id} kimlikli bir hesap yok. Astronot kimlikleri {first} ile {last} arasındadır.",
        "en": "No account has the ID {id}. Astronaut IDs run from {first} to {last}.",
    },
    "login_unknown_id_earth": {
        "tr": "{id} kimlikli bir hesap yok. Dünya üssü hesabı: {earth}.",
        "en": "No account has the ID {id}. The Earth base account is {earth}.",
    },
    "login_wrong_password": {
        "tr": "Şifre yanlış. Bu demoda şifre kimlikle aynıdır.",
        "en": "Wrong password. In this demo the password is the same as the ID.",
    },
    "login_wrong_password_earth": {"tr": "Dünya üssü şifresi yanlış.", "en": "Wrong password for the Earth base."},
    "login_earth_on_ship": {
        "tr": "Dünya üssü hesabı gemide kullanılmaz; Dünya üssü istasyonundan giriş yapın.",
        "en": "The Earth base account is not used on the ship. Log in at the Earth base station.",
    },
    "login_astronaut_on_earth": {
        "tr": "Astronot hesapları gemi bilgisayarındadır; bu istasyon Dünya üssüdür.",
        "en": "Astronaut accounts are on the ship computer. This station is the Earth base.",
    },
    "hint_ship": {
        "tr": "Astronotlar: {first} – {last} ({count} hesap); şifre kimlikle aynıdır.",
        "en": "Astronauts: {first} to {last} ({count} accounts); the password is the same as the ID.",
    },
    "hint_ship_empty": {"tr": "Gemide henüz astronot verisi yok.", "en": "No astronaut data on the ship yet."},
    "hint_earth": {"tr": "Dünya üssü: {earth}, şifre {password}.", "en": "Earth base: {earth}, password {password}."},
    "hint_earth_custom": {
        "tr": "Dünya üssü: {earth}; şifre EARTH_PASSWORD ile ayarlanır.",
        "en": "Earth base: {earth}; the password is set with EARTH_PASSWORD.",
    },
    "auth_required": {"tr": "Önce giriş yapın.", "en": "Log in first."},
    "auth_invalid": {
        "tr": "Oturumunuz geçerli değil; yeniden giriş yapın.",
        "en": "Your session is not valid. Log in again.",
    },
    "forbidden_other_astronaut": {
        "tr": "Sadece kendi verinizi görebilirsiniz.",
        "en": "You can only see your own data.",
    },
    "forbidden_kind": {"tr": "Bu hesap bu işlemi yapamaz.", "en": "This account cannot do that."},
    "unknown_astronaut": {"tr": "Astronot bulunamadı: {id}", "en": "Astronaut not found: {id}"},
    "unknown_day": {"tr": "Geçersiz gün: {day} (1–{n})", "en": "Invalid day: {day} (1–{n})"},
    # ---- check-in
    "empty_answer": {"tr": "Bir cevap yazın.", "en": "Type an answer."},
    "checkin_done": {"tr": "Bugünün check-in'i tamamlandı.", "en": "Today's check-in is complete."},
    "checkin_not_done": {"tr": "Önce bugünün check-in'ini tamamlayın.", "en": "Finish today's check-in first."},
    "reset_locked": {
        "tr": "Dünya ile paylaşılmış bir check-in baştan başlatılamaz.",
        "en": "A check-in shared with Earth cannot be started over.",
    },
    "share_downgrade": {
        "tr": "Paylaşım geri alınamaz; daha düşük bir seviye seçilemez.",
        "en": "Sharing cannot be undone; a lower level cannot be chosen.",
    },
    "share_label_private": {"tr": "Gizli tut", "en": "Keep private"},
    "share_label_scores": {"tr": "Sadece skorlar", "en": "Scores only"},
    "share_label_full": {"tr": "Her şey", "en": "Everything"},
    "share_desc_private": {
        "tr": "Dünya sadece check-in yaptığınızı görür.",
        "en": "Earth sees only that you completed a check-in.",
    },
    "share_desc_scores": {
        "tr": "Dünya ruh hali ve stres skorlarınızı ve hangi konuların işaretlendiğini görür; sözlerinizi görmez.",
        "en": "Earth sees your mood and stress scores and which topics were flagged, not your words.",
    },
    "share_desc_full": {
        "tr": "Dünya ruh hali ve stres skorlarınızı ve cevaplarınızı yazdığınız gibi görür.",
        "en": "Earth sees your mood and stress scores and your answers as written.",
    },
    "share_irreversible": {"tr": "Paylaşım geri alınamaz.", "en": "Sharing cannot be undone."},
    "share_cmo_note": {
        "tr": "Bir cevap acil bir tıbbi soruna işaret ederse, kayıt gizli olsa bile gemideki sağlık sorumlusu "
        "bilgilendirilir. Bu bilgi yine de Dünya'ya gönderilmez.",
        "en": "If an answer points to an urgent medical problem, the crew medical officer on board is told even "
        "when the entry is private. It is still not sent to Earth.",
    },
    "cmo_title": {"tr": "Gemideki sağlık sorumlusu bilgilendirildi.", "en": "Crew medical officer told."},
    "cmo_text": {
        "tr": "Belirti cevabınız gemideki sağlık sorumlusuna iletildi. Dünya'ya gönderilmedi.",
        "en": "Your symptom answer went to the medical officer on board. It was not sent to Earth.",
    },
}


def t(key: str, lang: Lang, **kwargs: object) -> str:
    """Anahtardan metin; bilinmeyen anahtar → anahtarın kendisi (testte yakalanır)."""
    entry = MESSAGES.get(key)
    if entry is None:
        return key
    text = entry.get(lang) or entry[DEFAULT_LANG]
    return text.format(**kwargs) if kwargs else text
