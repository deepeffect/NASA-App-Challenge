"""Veri setinin iç tutarlılığı (veriden okunan alanların bulunan ilişkileri).

Durum, ana endişe, ground ve self-care kodları VERİDEN okunur; bu testler veri setinin bu alanları
beklenen kurallarla ürettiğini doğrular. Kural dışı günler aşağıda tek tek belgelenmiştir.
"""

from app.personal.evaluate import readings_for_day

# Tetikleyicisi olmayan self-care kodu bulunan günler (astronot, 1'den başlayan gün, kod).
# Arayüzde bu öğelerin "neden" satırı "Veri setinin önerisi" olur.
UNTRIGGERED_CODES = {
    ("A005", 14, "RESISTIVE_EXERCISE"),
    ("A038", 9, "STOP_AND_RECORD_HEART"),
    ("A083", 17, "RESISTIVE_EXERCISE"),
    ("A139", 23, "MOOD_CONNECT"),
    ("A139", 24, "MOOD_CONNECT"),
    ("A178", 11, "PROTECT_SLEEP"),
}
# Tetiklenen kod sayısı 3 veya daha az olduğu hâlde veri setinin bir kodu listelemediği günler.
# (A139 23. gün: tetiklenmeyen MOOD_CONNECT, tetiklenen STRESS_RESET'in yerini almış.)
MISSING_CODES = {("A084", 16, "STOP_AND_RECORD_HEART"), ("A139", 23, "STRESS_RESET")}


def _days(dataset):
    for a in dataset.astronauts:
        for i, d in enumerate(a.days):
            yield a, i, d


def test_status_follows_cumulative_score(dataset) -> None:
    """health_status: kümülatif skor ≥ 80 → 0, ≥ 65 → 1, altı → 2 (6000/6000)."""
    for a, i, d in _days(dataset):
        expected = 0 if d.cumulative_score >= 80 else 1 if d.cumulative_score >= 65 else 2
        assert d.health_status == expected, (a.meta.id, i + 1)


def test_main_concern_is_lowest_area(dataset) -> None:
    """Durum 0 → 'none'; aksi halde en düşük alan skoru (eşitlikte eşitlerden biri)."""
    for a, i, d in _days(dataset):
        if d.health_status == 0:
            assert d.main_concern == "none", (a.meta.id, i + 1)
        else:
            low = min(d.area_scores.values())
            assert d.area_scores[d.main_concern] == low, (a.meta.id, i + 1)


def test_ground_flag_is_any_reading_far_out(dataset, catalog) -> None:
    """needs_ground_support ⇔ en az bir ölçüm 2. seviyede (6000/6000).

    Not: 0. adım raporundaki "A021 25. gün" istisnası analizde Python'un telafili `sum()`'ından
    kaynaklanıyordu; prototipteki gibi sırayla toplanınca (avg3) istisna kalmıyor.
    """
    for a, i, d in _days(dataset):
        far = any(r.level == 2 for r in readings_for_day(catalog, a, i))
        assert far == d.needs_ground_support, (a.meta.id, i + 1)


def test_self_care_codes_are_first_three_triggered(dataset, catalog) -> None:
    """self_care = tetiklenen kodlardan en fazla 3'ü (kural dışı günler yukarıda belgeli)."""
    untriggered, missing = set(), set()
    for a, i, d in _days(dataset):
        rd = readings_for_day(catalog, a, i)
        triggered = {r.ind.action for r in rd if r.level >= r.ind.trig}
        assert len(d.self_care) <= 3 and len(set(d.self_care)) == len(d.self_care), (a.meta.id, i + 1)
        for code in d.self_care:
            if code not in triggered:
                untriggered.add((a.meta.id, i + 1, code))
        if len(triggered) <= 3:
            missing |= {(a.meta.id, i + 1, c) for c in triggered - set(d.self_care)}
        else:
            assert len(d.self_care) == 3, (a.meta.id, i + 1)
    assert untriggered == UNTRIGGERED_CODES
    assert missing == MISSING_CODES
