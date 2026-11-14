"""Golden test: scripted check-in, prototipteki ciSend() + assistantTurn() ile birebir (İngilizce).

Her senaryo prototipte (Node) ve Python'da aynı astronot/gün/cevaplarla oynatılır; mesajlar, notlar,
bitiş, adım, hızlı cevaplar ve CMO bayrağı karşılaştırılır.
"""

import pytest

from app.personal.checkin_context import build_context
from app.personal.checkin_script import FlowState, apply_turn, assistant_turn

from .runner import requires_node, run_prototype

pytestmark = requires_node

ANSWERS = [
    ["Well", "Good", "No", "None", "No"],
    ["Badly", "Low", "A lot", "chest pain", "No"],
    ["OK", "So-so", "A little", "I have a fever and chills", "Need more water"],
    ["terrible, woke up 3 times", "not very good", "yes, overwhelmed", "headache and sore throat", "no"],
    ["slept great", "happy", "nothing", "nope", "nothing else"],
    ["  Not that well ", "meh", "not really", "blocked nose", "I feel dizzy"],
    ["fine", "fine", "very", "dizzy and short of breath", "No"],
    ["deep sleep", "lonely and homesick", "too much work", "my heart rates are high", "Yes, the CO2 scrubber was loud"],
    ["hardly slept", "irritable", "anxious", "nothing", "No", "extra answer after done"],
]
POINTS = [("A000", 29), ("A003", 23), ("A003", 29), ("A021", 24), ("A050", 15), ("A120", 29), ("A139", 23), ("A199", 0)]


def play_python(cat, series, di: int, answers: list[str]) -> FlowState:
    st = FlowState.initial("en")
    for raw in answers:
        text = raw.strip()
        if not text or st.done:  # ciSend: boş cevap veya bitmiş check-in yok sayılır
            continue
        history = [*st.msgs, {"who": "me", "text": text}]
        ctx = build_context(cat, series, di, "en", history, st.step, text)
        apply_turn(st, text, assistant_turn(ctx, "en"), "en")
    return st


@pytest.fixture(scope="module")
def golden(dataset):
    index = {a.meta.id: k for k, a in enumerate(dataset.astronauts)}
    spec = [{"ai": index[aid], "di": di, "answers": ans, "share": None} for aid, di in POINTS for ans in ANSWERS]
    return run_prototype({"checkins": spec})["checkins"]


def test_scripted_checkin_matches_prototype(golden, dataset, catalog) -> None:
    urgent_seen = fever_seen = 0
    for js in golden:
        series = dataset.astronauts[js["ai"]]
        st = play_python(catalog, series, js["di"], js["answers"])
        ref = js["state"]
        where = f"{series.meta.id} gün {js['di'] + 1} {js['answers']}"
        assert st.msgs == ref["msgs"], where
        assert [{k: v for k, v in n.items() if k != "topic_key"} for n in st.notes] == ref["notes"], where
        assert (st.done, st.step, st.options) == (ref["done"], ref["step"], ref["options"]), where
        assert st.cmo == bool(ref.get("cmo")), where
        urgent_seen += st.cmo
        fever_seen += any("Take your temperature" in m["text"] for m in st.msgs)
    assert urgent_seen and fever_seen  # acil ve ateş dalları gerçekten denendi


# ---------------------------------------------------------------- Dünya'nın gördüğü check-in
def _parse_earth(html: str) -> dict:
    import html as htmllib
    import re

    calm = re.match(r'<p class="calm">(.*?)</p>$', html)
    if calm:
        return {"text": calm.group(1), "notes": []}
    head = re.match(r'<p class="muted">(.*?)</p><div class="cinotes">(.*)</div>$', html, re.S)
    notes = [
        (htmllib.unescape(m.group(1)), htmllib.unescape(m.group(2)), bool(m.group(3)))
        for m in re.finditer(r'<div><span class="t">(.*?)</span><span>(.*?)</span>(<span class="glyph g1"[^>]*></span>)?</div>', head.group(2))
    ]
    return {"text": head.group(1), "notes": notes}


@pytest.fixture(scope="module")
def golden_earth(dataset):
    index = {a.meta.id: k for k, a in enumerate(dataset.astronauts)}
    spec = [
        {"ai": index[aid], "di": di, "answers": ans, "share": share}
        for aid, di in POINTS[:3]
        for ans in ANSWERS
        for share in ("private", "scores", "full")
    ]
    return run_prototype({"checkins": spec})["checkins"]


def test_earth_checkin_view_matches_prototype(golden_earth, dataset, catalog) -> None:
    from app.models.tables import CheckinSession
    from app.personal.earth_view import earth_checkin_view
    from app.personal.privacy import earth_checkin

    for js in golden_earth:
        series = dataset.astronauts[js["ai"]]
        st = play_python(catalog, series, js["di"], js["answers"])
        row = CheckinSession(astronaut_id=series.meta.id, day_index=js["di"], mission_day=0, notes=st.notes, done=st.done, share=js["share"])
        view = earth_checkin_view(earth_checkin(row), "en")
        ref = _parse_earth(js["earth"])
        ours_notes = [(n.topic, n.text if js["share"] == "full" else n.flag_text, n.flag) for n in view.notes]
        assert (view.text, ours_notes) == (ref["text"], ref["notes"]), (series.meta.id, js["share"], js["answers"])
