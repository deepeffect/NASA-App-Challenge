from app.safety.emergency import detect_emergency, fold_text


def test_fold_text_turkish():
    assert fold_text("Göğüs AĞRISI") == "gogus agrisi"
    assert fold_text("İNTİHAR") == "intihar"
    assert fold_text("  çok   ŞİDDETLİ ") == "cok siddetli"


def test_detects_without_turkish_chars():
    em = detect_emergency("gogus agrisi var biraz")
    assert em is not None
    assert em.matched_symptoms == ["chest_pain"]
    assert em.protocol.verified is False
    assert em.protocol.steps


def test_detects_english_and_lang():
    em = detect_emergency("I think I passed out for a second", lang="en")
    assert em is not None and "altered_consciousness" in em.matched_symptoms
    assert em.message.startswith("Possible emergency")


def test_no_false_positive_on_normal_text():
    assert detect_emergency("Bugün iyiyim, biraz yorgunum.") is None
    assert detect_emergency("") is None
    assert detect_emergency(None) is None


def test_emergency_check_endpoint(client):
    """Legacy sohbet harici asistana gidince de acil tarama kural tabanlı çalışır (LLM'siz)."""
    r = client.post("/api/emergency/check", json={"text": "I have severe chest pain", "lang": "en"})
    assert r.status_code == 200
    n = r.json()["notice"]
    assert n and "chest_pain" in n["matched_symptoms"]
    r = client.post("/api/emergency/check", json={"text": "Göğsümde ağrı var"})
    assert r.status_code == 200 and r.json()["notice"]
    r = client.post("/api/emergency/check", json={"text": "How is my sleep?", "lang": "en"})
    assert r.status_code == 200 and r.json()["notice"] is None
