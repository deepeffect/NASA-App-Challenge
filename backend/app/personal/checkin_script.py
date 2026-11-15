"""Scripted check-in — prototipteki `TOPICS`, `grade`, `assistantTurn` ve `ciSend` akışı birebir.

Sözleşme (prototip):
  ctx = {astronaut: {id, age, sex, mission}, day, status, readings: [{col, label, value, unit, healthy, level}],
         todo: [başlıklar], history: [{who, text}], step, answer}
  → {reply, note: {topic, text, flag, urgent} | null, next: {text, options[]} | null, done}

İngilizce regex'ler ve metinler prototiple aynıdır (golden test). Türkçe cevaplar için eşdeğer
regex'ler Türkçe karakterleri katlanmış metinde ("Kötü" → "kotu") çalışır. Arayüz dilinin kuralı
eşleşmezse (varsayılan dala düşerse) diğer dilin kuralları denenir.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

from app.i18n import Lang
from app.safety.emergency import fold_text

Grade = Literal["good", "mid", "bad", "skip"]
Rule = tuple[re.Pattern[str], Grade]


def _en(p: str) -> re.Pattern[str]:
    return re.compile(p, re.ASCII)  # JS'deki \b ASCII kelime sınırıdır


def _tr(p: str) -> re.Pattern[str]:
    return re.compile(p)


NEG_EN = _en(r"^(no|none|nothing|nope)\b")
NEG_TR = _tr(r"^(yok|hayir|hicbir|hic)\b")

# Acil belirti (sadece belirti sorusunda, cevap "kötü" notlandığında). İki dil her zaman taranır.
URGENT_EN = _en(r"chest|faint|dizz|palpitat|breath|blood")
# TR kalıpları kelime başına bağlı: İngilizce "rates" içindeki "ates" ateş sayılmasın.
URGENT_TR = _tr(r"\b(gogus|gogs|bayil|bas don|basim don|carpinti|carpiyor|nefes|kan\b|kanam|kaniyor|kanli)")
FEVER_EN = _en(r"fever|chills|temperature|hot")
FEVER_TR = _tr(r"\b(ates|titre|usum|usuyor|sicak|harar)")


@dataclass(frozen=True)
class Topic:
    key: str
    name: dict[Lang, str]
    q: dict[Lang, str]
    options: dict[Lang, list[str]]
    rules_en: list[Rule]
    rules_tr: list[Rule]
    default: Grade
    ind: str | None = None
    sol: str | None = None


TOPICS: list[Topic] = [
    Topic(
        key="sleep",
        name={"en": "Sleep", "tr": "Uyku"},
        q={"en": "How did you sleep last night?", "tr": "Dün gece nasıl uyudunuz?"},
        options={"en": ["Well", "OK", "Badly"], "tr": ["İyi", "İdare eder", "Kötü"]},
        rules_en=[
            (_en(r"bad|poor|terribl|awful|barely|hardly|couldn|tired|exhaust|woke|not (very |that |so )?(well|good|great)"), "bad"),
            (_en(r"\bok\b|okay|so-so|average|alright"), "mid"),
            (_en(r"well|good|great|fine|deep"), "good"),
        ],
        rules_tr=[
            (_tr(r"kotu|berbat|az uyu|uyuyama|zor uyu|yorgun|bitkin|uyand|uykusuz|rahatsiz|(iyi|pek) degil|hic uyu"), "bad"),
            (_tr(r"idare|orta|soyle boyle|fena degil|normal|sayilir"), "mid"),
            (_tr(r"\biyi|guzel|harika|derin|mukemmel|dinlen|rahat"), "good"),
        ],
        default="mid",
        ind="beh_sleep_h",
        sol="PROTECT_SLEEP",
    ),
    Topic(
        key="mood",
        name={"en": "Mood", "tr": "Ruh hali"},
        q={"en": "How is your mood today?", "tr": "Bugün ruh haliniz nasıl?"},
        options={"en": ["Good", "So-so", "Low"], "tr": ["İyi", "Şöyle böyle", "Düşük"]},
        rules_en=[
            (_en(r"\blow\b|sad|down|bad|lonely|homesick|irritab|angry|depress|not (very |that |so )?(good|great|well)"), "bad"),
            (_en(r"so-so|\bok\b|okay|average|meh|alright"), "mid"),
            (_en(r"good|great|happy|fine|excellent|well"), "good"),
        ],
        rules_tr=[
            (_tr(r"dusuk|uzgun|kotu|mutsuz|yalniz|ozle|sinirli|gergin|depres|keyifsiz|moralim bozuk|halsiz|(iyi|pek) degil|bunal"), "bad"),
            (_tr(r"soyle boyle|idare|orta|fena degil|\beh\b|normal"), "mid"),
            (_tr(r"\biyi|harika|mutlu|guzel|mukemmel|super|keyifli|neseli"), "good"),
        ],
        default="mid",
        ind="beh_mood_score",
        sol="MOOD_CONNECT",
    ),
    Topic(
        key="stress",
        name={"en": "Stress", "tr": "Stres"},
        q={"en": "Is anything stressing you today?", "tr": "Bugün sizi strese sokan bir şey var mı?"},
        options={"en": ["No", "A little", "A lot"], "tr": ["Hayır", "Biraz", "Çok"]},
        rules_en=[
            (_en(r"^(no|none|nothing|nope|not )"), "good"),
            (_en(r"a lot|lots|high|very|overwhelm|too much|stressed|anxious|yes"), "bad"),
        ],
        rules_tr=[
            (_tr(r"^(hayir|yok|hic\b|hicbir|pek yok|(cok |pek )?degil)"), "good"),
            (_tr(r"\bcok\b|fazla|yogun|bunal|stresli|endise|kaygi|gergin|evet|asiri|baski"), "bad"),
        ],
        default="mid",
        ind="beh_stress_score",
        sol="STRESS_RESET",
    ),
    Topic(
        key="symptoms",
        name={"en": "Symptoms", "tr": "Belirtiler"},
        q={
            "en": "Any symptoms? For example headache, sore throat, rash or a blocked nose.",
            "tr": "Herhangi bir belirtiniz var mı? Örneğin baş ağrısı, boğaz ağrısı, döküntü veya burun tıkanıklığı.",
        },
        options={"en": ["None"], "tr": ["Yok"]},
        rules_en=[(NEG_EN, "good")],
        rules_tr=[(NEG_TR, "good")],
        default="bad",
        ind="imm_symptom_score",
        sol="SYMPTOM_CARE",
    ),
    Topic(
        key="other",
        name={"en": "Other", "tr": "Diğer"},
        q={"en": "Anything else you want noted for today?", "tr": "Bugün için not edilmesini istediğiniz başka bir şey var mı?"},
        options={"en": ["No"], "tr": ["Hayır"]},
        rules_en=[(NEG_EN, "skip")],
        rules_tr=[(NEG_TR, "skip")],
        default="mid",
    ),
]
TOPIC_BY_KEY = {t.key: t for t in TOPICS}

TEXTS: dict[str, dict[Lang, str]] = {
    "noted": {"en": "Noted.", "tr": "Not edildi."},
    "ok": {"en": "OK.", "tr": "Tamam."},
    "urgent": {
        "en": "Noted. Stop what you are doing and rest. The crew medical officer on board is being told now.",
        "tr": "Not edildi. Yaptığınız işi bırakıp dinlenin. Gemideki sağlık sorumlusu şimdi bilgilendiriliyor.",
    },
    "fever": {
        "en": 'Noted. Take your temperature now. See "{title}" under the i button.',
        "tr": 'Not edildi. Şimdi ateşinizi ölçün. i düğmesinin altında "{title}" bölümüne bakın.',
    },
    "noted_fix": {"en": "Noted. {fix}", "tr": "Not edildi. {fix}"},
    "agree": {"en": "Noted. Your readings agree: {seen}. {fix}", "tr": "Not edildi. Ölçümleriniz de bunu gösteriyor: {seen}. {fix}"},
    "watch": {
        "en": 'Noted. Your readings still look normal ({seen}), so I have flagged it to watch. If it is the same tomorrow, try "{title}".',
        "tr": 'Not edildi. Ölçümleriniz hâlâ normal görünüyor ({seen}), bu yüzden izlemek üzere işaretledim. Yarın da aynıysa "{title}" önerisini deneyin.',
    },
    "good_but": {
        "en": "Good to hear. Your readings say otherwise though ({seen}), so keep an eye on it.",
        "tr": "Bunu duyduğuma sevindim. Ancak ölçümleriniz farklı bir şey söylüyor ({seen}); gözünüz üzerinde olsun.",
    },
    "good": {"en": "Good, noted.", "tr": "Güzel, not edildi."},
    "seen": {"en": "{label} is averaging {value}{unit}", "tr": "{label} ortalaması {value}{unit}"},
    # Veri seti ortalama almıyorsa (o günün değeri) "ortalaması" denmez
    "seen_day": {"en": "{label} is {value}{unit}", "tr": "{label} {value}{unit}"},
    "fix_todo": {"en": '"{title}" is on your to-do list.', "tr": '"{title}" yapılacaklar listenizde.'},
    "fix_try": {"en": 'Try "{title}" (see the i button).', "tr": '"{title}" önerisini deneyin (i düğmesine bakın).'},
    "done_flagged": {"en": "Check-in complete. Flagged for today: {topics}.", "tr": "Check-in tamamlandı. Bugün işaretlenenler: {topics}."},
    "done_clear": {"en": "Check-in complete. Nothing flagged.", "tr": "Check-in tamamlandı. İşaretlenen bir şey yok."},
    "failed": {"en": "That did not go through. Please answer again.", "tr": "Bu iletilemedi. Lütfen yeniden cevaplayın."},
}


def tx(key: str, lang: Lang, **kw: object) -> str:
    s = TEXTS[key][lang]
    return s.format(**kw) if kw else s


def lower(s: str, lang: Lang) -> str:
    if lang == "tr":
        s = s.replace("I", "ı").replace("İ", "i")
    return s.lower()


# ============================================================================ notlama
def _apply(rules: list[Rule], s: str) -> Grade | None:
    for pattern, g in rules:
        if pattern.search(s):
            return g
    return None


def grade(topic: Topic, answer: str, lang: Lang) -> Grade:
    """Arayüz dilinin kuralları; eşleşme yoksa diğer dilin kuralları; o da yoksa konunun varsayılanı."""
    s_en = answer.strip().lower()  # JS: ctx.answer.trim().toLowerCase()
    s_tr = fold_text(answer)
    first, second = ((topic.rules_en, s_en), (topic.rules_tr, s_tr)) if lang == "en" else ((topic.rules_tr, s_tr), (topic.rules_en, s_en))
    return _apply(*first) or _apply(*second) or topic.default


def is_urgent(answer: str) -> bool:
    return bool(URGENT_EN.search(answer.strip().lower()) or URGENT_TR.search(fold_text(answer)))


def is_fever(answer: str) -> bool:
    return bool(FEVER_EN.search(answer.strip().lower()) or FEVER_TR.search(fold_text(answer)))


# ============================================================================ tur
def solution_title(ctx: dict[str, Any], code: str) -> str:
    return ctx["solution_titles"][code]


def assistant_turn(ctx: dict[str, Any], lang: Lang) -> dict[str, Any]:
    """Prototipteki assistantTurn(ctx). `ctx["solution_titles"]`: kod → başlık (prototipte SOL)."""
    t = TOPICS[ctx["step"]]
    answer: str = ctx["answer"]
    g = grade(t, answer, lang)
    r = next((x for x in ctx["readings"] if x["col"] == t.ind), None) if t.ind else None
    seen = tx("seen" if r.get("averaged", True) else "seen_day", lang, label=lower(r["label"], lang), value=r["value"], unit=r["unit"]) if r else ""
    fix = ""
    if t.sol:
        title = solution_title(ctx, t.sol)
        fix = tx("fix_todo", lang, title=title) if title in ctx["todo"] else tx("fix_try", lang, title=title)
    reply, flag, urgent = tx("noted", lang), False, False
    if t.key == "other":
        reply = tx("ok", lang) if g == "skip" else tx("noted", lang)
    elif t.key == "symptoms" and g == "bad":
        flag = True
        if is_urgent(answer):
            urgent = True
            reply = tx("urgent", lang)
        elif is_fever(answer):
            reply = tx("fever", lang, title=solution_title(ctx, "REST_AND_ISOLATE"))
        else:
            reply = tx("noted_fix", lang, fix=fix)
    elif g == "bad":
        flag = True
        reply = tx("agree", lang, seen=seen, fix=fix) if r["level"] else tx("watch", lang, seen=seen, title=solution_title(ctx, t.sol))
    elif g == "good":
        reply = tx("good_but", lang, seen=seen) if r["level"] else tx("good", lang)
    nxt = TOPICS[ctx["step"] + 1] if ctx["step"] + 1 < len(TOPICS) else None
    return {
        "reply": reply,
        "note": None if g == "skip" else {"topic": t.name[lang], "topic_key": t.key, "text": answer.strip(), "flag": flag, "urgent": urgent},
        "next": {"text": nxt.q[lang], "options": list(nxt.options[lang])} if nxt else None,
        "done": nxt is None,
    }


# ============================================================================ akış (ciSend)
@dataclass
class FlowState:
    """Prototipteki checkins[key] durumu."""

    step: int = 0
    options: list[str] = field(default_factory=list)
    msgs: list[dict[str, str]] = field(default_factory=list)
    notes: list[dict[str, Any]] = field(default_factory=list)
    done: bool = False
    cmo: bool = False

    @classmethod
    def initial(cls, lang: Lang) -> FlowState:
        t = TOPICS[0]
        return cls(step=0, options=list(t.options[lang]), msgs=[{"who": "bot", "text": t.q[lang]}])


def summary_text(notes: list[dict[str, Any]], lang: Lang) -> str:
    flagged = [lower(n["topic"], lang) for n in notes if n["flag"]]
    return tx("done_flagged", lang, topics=", ".join(flagged)) if flagged else tx("done_clear", lang)


def apply_turn(st: FlowState, text: str, out: dict[str, Any] | None, lang: Lang) -> None:
    """ciSend: cevabı ve asistanın dönüşünü duruma işler. `out=None` → tur başarısız (prototipteki catch)."""
    st.msgs.append({"who": "me", "text": text})
    if out is None:
        st.msgs.append({"who": "bot", "text": tx("failed", lang)})
        return
    st.msgs.append({"who": "bot", "text": out["reply"]})
    if out["note"]:
        st.notes.append(out["note"])
        if out["note"]["urgent"]:
            st.cmo = True
    if out["done"] or not out["next"]:
        st.done = True
        st.msgs.append({"who": "bot", "text": summary_text(st.notes, lang)})
    else:
        st.step += 1
        st.options = list(out["next"]["options"] or [])
        st.msgs.append({"who": "bot", "text": out["next"]["text"]})
