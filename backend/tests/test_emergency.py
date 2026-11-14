from app.safety.emergency import detect_emergency, fold_text


def test_fold_text_case_space_and_accents():
    assert fold_text("CHEST  Pain") == "chest pain"
    assert fold_text("  Café   NAÏVE ") == "cafe naive"
    assert fold_text("can’t breathe") == "can't breathe"


def test_detects_case_insensitive_with_protocol():
    em = detect_emergency("Had CHEST PAIN since this morning")
    assert em is not None
    assert em.matched_symptoms == ["chest_pain"]
    assert em.matched_labels == ["Chest pain"]
    assert em.protocol.verified is False
    assert em.protocol.steps and em.protocol.title.startswith("Possible emergency")


def test_detects_common_phrasings():
    em = detect_emergency("My chest hurts and I cant breathe")
    assert em is not None and set(em.matched_symptoms) == {"chest_pain", "breathing"}
    em = detect_emergency("I think I passed out for a second", lang="en")
    assert em is not None and "altered_consciousness" in em.matched_symptoms
    assert em.message.startswith("Possible emergency")


def test_no_false_positive_on_normal_text():
    assert detect_emergency("Feeling fine today, a bit tired.") is None
    assert detect_emergency("") is None
    assert detect_emergency(None) is None
