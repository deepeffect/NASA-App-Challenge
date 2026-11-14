"""Golden test: değerlendirme ve gün görünümü, prototipin JavaScript'iyle birebir.

Prototip (frontend/reference/personal-artifact.html) değiştirilmeden Node'da çalıştırılır; her
astronotun her günü için astronot ve Dünya görünümü Python'la (lang=en) karşılaştırılır.

Bilinçli farklar (kullanıcı kararları) açıkça kontrol edilir:
  D1  Dünya'da durum başlığı ve şerit, ground'u sadece görünür ölçümlerden hesaplar
      (prototip başlıkta veri setindeki ground'u kullanır).
  D2  Tetikleyicisi olmayan self-care kodunda "neden" satırı "Suggested by the dataset"
      (prototipte boş).
  D3  Dünya'da, check-in en az `scores` paylaşılmadıysa davranışsal alan skoru "Not shared";
      ana endişe davranışsalsa "behavioral area (details not shared)".
  D4  Dünya'da (paylaşılmamışsa) çözümü sadece gizli ölçümlere bağlı "veri setinin önerisi" öğesi
      (MOOD_CONNECT, A139 23–24. gün) maskelenir; prototip gösteriyordu. Onaylı karar;
      gizlilik testleri: tests/station/test_sharing_privacy.py (test_d4_*), test_downlink.py.
"""

import pytest

from app.personal.evaluate import shown_status
from app.personal.view import build_day_view, build_strip, share_rank, tx

from .runner import requires_node, run_prototype

pytestmark = requires_node
GROUPS_EN = None


@pytest.fixture(scope="module")
def golden(dataset):
    n = len(dataset.astronauts)
    views = [{"ai": a, "di": d, "role": r, "share": None} for a in range(n) for d in range(30) for r in ("astro", "earth")]
    views += [{"ai": a, "di": 29, "role": "earth", "share": s} for a in range(n) for s in ("private", "scores", "full")]
    strips = [{"ai": a, "role": r} for a in range(n) for r in ("astro", "earth")]
    return run_prototype({"views": views, "strips": strips})


def ours_rows(cat, view):
    rows = []
    for dom, label in cat.domains.items():
        for r in view.readings:
            if r.domain == dom:
                rows.append([label.en, r.label, r.unit, r.value_text, r.healthy_text, r.flag_text])
    return rows


def test_every_day_matches_prototype(golden, dataset, catalog) -> None:
    stats = {"views": 0, "D1": 0, "D2": 0, "D3": 0, "D4": 0}
    for js in golden["views"]:
        series = dataset.astronauts[js["ai"]]
        day = series.days[js["di"]]
        earth = js["role"] == "earth"
        v = build_day_view(catalog, series, js["di"], "en", earth=earth, shared=share_rank(js["share"]), share=js["share"])
        where = f'{series.meta.id} gün {js["di"] + 1} {js["role"]} share={js["share"]}'
        stats["views"] += 1

        todo = js["todo"]
        d4 = []
        if earth and share_rank(js["share"]) < 1:
            d4 = [x for x in todo["items"] if x["why"] == "" and x["title"] == "Reconnect and recharge"]

        # ---- durum başlığı ve alt başlık
        proto_status = shown_status(day.health_status, day.needs_ground_support)
        if earth and v.status != proto_status:  # D1
            stats["D1"] += 1
            assert v.status == shown_status(day.health_status, v.ground), where
        else:
            assert v.status_label == js["state"] and v.status == js["glyph"], where
            if earth and day.main_concern == "behavioral" and v.status and share_rank(js["share"]) < 1:  # D3
                assert v.subtitle == "Main concern: behavioral area (details not shared)", where
                assert js["statesub"] == "Main concern: sleep, mood and stress", where
            elif d4 and not v.status:  # D4: maskelenen öğe "küçük şey" sayısından düşer
                n = len(todo["items"]) - len(d4)
                assert v.subtitle == (f"{n} small thing{'s' if n > 1 else ''} to look at" if n else "Nothing to do today"), where
            else:
                assert v.subtitle == js["statesub"], where
        assert v.score_text == js["score"], where
        assert v.day_label == js["daylabel"], where

        # ---- to-do
        assert v.todo_title == todo["title"], where
        if not d4:
            assert v.calm_text == todo["calm"], where
        assert (None if v.ground_title is None else {"title": v.ground_title, "text": v.ground_text}) == todo["ground"], where
        ref_items = todo["items"]
        if d4:  # D4
            stats["D4"] += len(d4)
            ref_items = [x for x in ref_items if x not in d4]
            assert v.todo_masked_count == len(d4) + (int(todo["masked"].split()[0]) if todo["masked"] else 0), where
        else:
            assert v.todo_masked_text == todo["masked"], where
        assert len(v.todo) == len(ref_items), where
        for ours, ref in zip(v.todo, ref_items, strict=True):
            assert (ours.title, ours.steps, ours.contact_ground_if) == (ref["title"], ref["steps"], ref["contact"]), where
            if ours.source == "dataset":  # D2
                stats["D2"] += 1
                assert ref["why"] == "" and ours.why == "Suggested by the dataset", where
            else:
                assert ours.why == ref["why"], where

        # ---- okumalar ve alan skorları
        assert ours_rows(catalog, v) == js["readings"], where
        for ours, ref in zip(v.areas, js["areas"], strict=True):
            if ours.hidden:  # D3
                stats["D3"] += 1
                assert ours.area == "behavioral" and ours.score_text == "Not shared", where
                assert ref[1] == f"{day.area_scores['behavioral']:.0f}" or ref[1].isdigit(), where
            else:
                assert [ours.label, ours.score_text] == ref[:2], where
            assert ("Main concern" if ours.main_concern else "") == ref[2], where
        assert v.readings_note.endswith(js["privnote"]), where

    assert stats["views"] == len(dataset.astronauts) * 30 * 2 + len(dataset.astronauts) * 3
    # Farkların gerçekten ortaya çıktığını da belgeleyelim (sıfır olsaydı test hiçbir şey kanıtlamazdı)
    assert stats["D2"] > 0 and stats["D3"] > 0 and stats["D4"] == 2, stats
    print("golden:", stats)


def test_strip_matches_prototype(golden, dataset, catalog) -> None:
    for js in golden["strips"]:
        series = dataset.astronauts[js["ai"]]
        earth = js["role"] == "earth"
        ours = build_strip(catalog, series, "en", earth=earth)
        for k, (day, item, (cls, aria)) in enumerate(zip(series.days, ours, js["bars"], strict=True)):
            proto = shown_status(day.health_status, day.needs_ground_support)
            if earth and item.status != proto:  # D1
                continue
            assert (f"s{item.status}", item.label) == (cls, aria), f"{series.meta.id} gün {k + 1} {js['role']}"


def test_turkish_view_has_same_structure(dataset, catalog) -> None:
    series = dataset.by_id()["A003"]
    en = build_day_view(catalog, series, 23, "en")
    tr = build_day_view(catalog, series, 23, "tr")
    assert tr.day_label == "30 günün 24. günü · görev günü 24"
    assert tr.status_label == "Dikkat" and tr.subtitle == "Ana endişe: uyku, ruh hali ve stres"
    assert [t.code for t in tr.todo] == [t.code for t in en.todo]
    assert tr.todo[0].why == "Radyasyon dozu 53,04 mSv/gün, sağlıklı aralık 0–0,5"
    assert tr.threshold_note == "Aralıklar simüle veri setinden alınmıştır, tıbbi doğrulama yapılmamıştır."
    assert tx("why_dataset", "tr") == "Veri setinin önerisi"
