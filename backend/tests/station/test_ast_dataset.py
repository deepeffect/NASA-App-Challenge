"""AST görev verisi (seviyesi veriden gelen veri seti): dönüştürücü, panel görünümü ve gizlilik.

Kaynak: data/raw/ast/ (veri ekibinin v3.1 payload dosyaları) → data/raw/astronaut_health_ast.json.
Varsayılan veri seti (data/raw/astronaut_health.json) bu testlerden etkilenmez; onun testleri ayrıdır.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.config import Settings
from app.models.tables import CheckinSession, OutboxEvent
from app.personal.ast_convert import LEVEL_TR, NOT_IN_FILE, NOT_MEASURED, SOURCE_INDICATORS, SOURCE_TR, convert
from app.personal.catalog import load_personal_catalog
from app.personal.dataset import load_dataset_file
from app.personal.derive import derive
from app.personal.evaluate import evaluate_day
from app.personal.privacy import earth_day
from app.personal.view import build_day_view, build_strip

from .conftest import login, sqlite_url

REPO = Path(__file__).resolve().parents[3]
SOURCE = REPO / "data" / "raw" / "ast"
AST_FILE = REPO / "data" / "raw" / "astronaut_health_ast.json"
FIRST, LAST = 149, 178
PRIVATE = ("beh_mood_score", "beh_stress_score")
PRIVATE_ONLY_CODES = {"MOOD_CONNECT", "STRESS_RESET"}  # bu veri setinde sadece ruh hali / stres tetikler (kortizol ölçülmüyor)


@pytest.fixture(scope="module")
def cat():
    return load_personal_catalog()


@pytest.fixture(scope="module")
def ast(cat):
    return load_dataset_file(AST_FILE, cat)


@pytest.fixture(scope="module")
def raw() -> dict:
    return json.loads(AST_FILE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def source() -> dict[tuple[str, int], dict[str, dict]]:
    out = {}
    for line in (SOURCE / SOURCE_TR).open(encoding="utf-8"):
        if line.strip():
            r = json.loads(line)
            out[(r["astronot_id"], r["gorev_gunu"])] = {g["ad"]: g for g in r["gostergeler"]}
    return out


def by_mission_day(series, mission_day: int) -> int:
    return next(i for i, d in enumerate(series.days) if d.mission_day == mission_day)


def unshared_private_worse(cat, series, i) -> bool:
    """Bu günde gizli bir ölçümün (ruh hali / stres) seviyesi görünür bütün ölçümlerden kötü mü."""
    levels = series.days[i].levels
    hidden = max(levels[c] for c in PRIVATE)
    return hidden > max(v for c, v in levels.items() if c not in PRIVATE)


# ---------------------------------------------------------------- dönüştürücü: hiçbir değer uydurulmaz
def test_committed_file_is_exactly_what_the_converter_produces(raw) -> None:
    assert convert(SOURCE, FIRST, LAST) == raw


def test_every_value_level_and_normal_text_equals_the_source(raw, source) -> None:
    checked = 0
    for rec in raw["records"]:
        src = source[(rec["astronaut_id"], rec["mission_day"])]
        for col, (name_tr, _name_en, unit) in SOURCE_INDICATORS.items():
            g = src[name_tr]
            assert g["birim"] == unit
            first_number = float(str(g["deger"]).split("/")[0])  # kan basıncı "sistolik/diyastolik" yazılır
            assert rec[col] == first_number, (rec["astronaut_id"], rec["mission_day"], col)
            assert rec["levels"][col] == LEVEL_TR[g["durum"]]
            assert rec["normal"][col]["tr"] == g["normal"]
            if isinstance(g["deger"], str):
                assert rec["display"][col] == g["deger"]
            checked += 1
    assert checked == 4 * 30 * 11


def test_nothing_is_added_beyond_the_source_and_the_documented_derivations(raw) -> None:
    allowed = {"astronaut_id", "mission_day", *SOURCE_INDICATORS, "levels", "normal", "display",
               "health_status", "main_concern", "self_care_actions", "needs_ground_support"}
    for rec in raw["records"]:
        assert set(rec) <= allowed, set(rec) - allowed
        assert set(rec["levels"]) == set(SOURCE_INDICATORS)
        assert not any(c in rec for c in (*NOT_MEASURED, *NOT_IN_FILE))  # ölçülmeyen kolon kayıtta YOK (0 ya da boş değil)
    score_keys = {"immune_score", "bone_muscle_score", "cardiovascular_score", "behavioral_score",
                  "daily_health_score", "cumulative_health_score"}
    assert not any(score_keys & set(rec) for rec in raw["records"])  # skor üretilmez
    assert all(set(a) == {"astronaut_id", "mission"} for a in raw["astronauts"])  # yaş / cinsiyet / VKİ / desen yok
    assert raw["dataset"]["absent"] == {**dict.fromkeys(NOT_MEASURED, "not_measured"), **dict.fromkeys(NOT_IN_FILE, "not_in_file")}
    assert raw["dataset"]["has_scores"] is False and raw["dataset"]["averaged"] is False


def test_derived_fields_follow_the_documented_rules(ast, cat) -> None:
    for a in ast.astronauts:
        for d in a.days:
            want = derive(cat, d.levels)
            assert (d.health_status, d.main_concern, d.self_care, d.needs_ground_support) == (
                want.health_status, want.main_concern, want.self_care, want.needs_ground_support)
            assert d.health_status == max(d.levels.values())
            assert d.needs_ground_support == (2 in d.levels.values())


def test_crew_is_ast_01_to_04_on_the_same_mission_days(ast) -> None:
    assert [a.meta.id for a in ast.astronauts] == ["AST-01", "AST-02", "AST-03", "AST-04"]
    for a in ast.astronauts:
        assert [d.mission_day for d in a.days] == list(range(FIRST, LAST + 1))
        assert a.meta.mission == "ISS_LEO" and a.meta.age is None and a.meta.profile is None


# ---------------------------------------------------------------- panel görünümü
def test_story_days_match_the_data_team_numbers(ast, cat) -> None:
    """AST-02: görev günü 178 → dinlenik nabız 50, KIRMIZI; 164 → 54, SARI (asistanın söylediği sayılar)."""
    a = ast.by_id()["AST-02"]
    today = build_day_view(cat, a, a.today_index, "tr")
    rows = {r.col: r for r in today.readings}
    assert today.mission_day == 178 and today.is_today and today.status == 2 and today.status_label == "Rahatsız" and today.ground
    hr = rows["cv_resting_hr_bpm"]
    assert (hr.label, hr.value_text, hr.level, hr.healthy_text, hr.averaged) == ("Dinlenik nabız", "50", 2, "45±2", False)
    d164 = build_day_view(cat, a, by_mission_day(a, 164), "tr")
    hr164 = next(r for r in d164.readings if r.col == "cv_resting_hr_bpm")
    assert (hr164.value_text, hr164.level) == ("54", 1)
    en = {r.col: r for r in build_day_view(cat, a, a.today_index, "en").readings}["cv_resting_hr_bpm"]
    assert en.label == "Resting heart rate" and "personal baseline" in en.healthy_text


def test_mood_and_stress_keep_their_own_1_to_5_scale(ast, cat) -> None:
    a = ast.by_id()["AST-02"]
    rows = {r.col: r for r in build_day_view(cat, a, a.today_index, "tr").readings}
    for col in PRIVATE:
        assert rows[col].unit == "1-5" and rows[col].value_text.endswith("/5") and rows[col].value in (1, 2, 3, 4, 5)
    assert rows["beh_stress_score"].value_text == "3/5" and rows["beh_stress_score"].healthy_text == "1.3±0.5"
    assert rows["cv_systolic_bp_mmHg"].value_text == "116/82"  # kaynaktaki yazılış


def test_absent_readings_say_why_and_never_turn_red(ast, cat) -> None:
    for a in ast.astronauts:
        for i in range(len(a.days)):
            v = build_day_view(cat, a, i, "tr")
            assert [r.col for r in v.readings] == cat.columns  # 18 satır, katalog sırasıyla
            absent = [r for r in v.readings if not r.measured]
            assert {r.col for r in absent} == {*NOT_MEASURED, *NOT_IN_FILE}
            for r in absent:
                want = "Bu veri dosyasında yok" if r.col in NOT_IN_FILE else "Bu görevde ölçülmedi"
                assert (r.value_text, r.value, r.today, r.level, r.flag_text, r.hidden) == (want, None, None, None, "", False)
    assert build_day_view(cat, a, 0, "en").readings[2].value_text == "Not measured on this mission"


def test_no_scores_only_a_note(ast, cat) -> None:
    a = ast.by_id()["AST-02"]
    v = build_day_view(cat, a, a.today_index, "tr")
    assert (v.score, v.score_text, v.daily_score, v.areas, v.scores_note) == (None, "", None, [], "Bu veri setinde skor yok.")
    strip = build_strip(cat, a, "tr")
    assert all(s.score is None and s.daily_score is None and s.score_text == "" for s in strip)
    assert strip[-1].label == "Gün 30: Rahatsız" and v.source_note and "DOSTEL-2" in v.source_note


def test_environment_only_warning_is_not_called_far_out(ast, cat) -> None:
    """AST-01 gün 178: sadece kabin CO2 SARI → 'Dikkat', ana endişe yok, yer desteği yok, metin 'çok dışında' demez."""
    a = ast.by_id()["AST-01"]
    v = build_day_view(cat, a, a.today_index, "tr")
    assert (v.status, v.main_concern, v.ground, v.subtitle) == (1, "none", False, "Bir ölçüm aralığın dışında")
    assert [t.code for t in v.todo] == ["FIX_CABIN_AIR"]


# ---------------------------------------------------------------- gizlilik: Dünya sadece görünür ölçümleri bilir
def test_earth_record_is_derived_from_visible_readings_only(ast, cat) -> None:
    """Paylaşılmamış her günde Dünya kaydı (durum, ana endişe, yer desteği, yapılacaklar) yalnızca görünür
    ölçümlerden türetilir; ruh hali / stres ne değer, ne kod, ne sayı olarak gider."""
    for a in ast.astronauts:
        for i, day in enumerate(a.days):
            rec = earth_day(cat, a, i)
            visible = {c: lv for c, lv in day.levels.items() if c not in PRIVATE}
            want = derive(cat, visible)
            assert set(rec.readings) == set(visible)
            assert (rec.health_status, rec.main_concern, rec.ground) == (want.health_status, want.main_concern, want.needs_ground_support)
            assert rec.status == want.health_status
            assert [t.code for t in rec.todo] == want.self_care
            assert rec.todo_masked_count == 0 and not rec.behavioral_hidden and rec.area_scores == {} and rec.cumulative_score is None
            blob = rec.model_dump_json()
            assert not any(col in blob for col in PRIVATE), (a.meta.id, i)
            assert not any(code in blob for code in PRIVATE_ONLY_CODES), (a.meta.id, i)


def test_unshared_red_stress_cannot_be_inferred_on_earth(ast, cat) -> None:
    """Stres KIRMIZI / SARI iken görünür ölçümler daha iyiyse: gemi görür, Dünya hiçbir yerden anlayamaz."""
    a = ast.by_id()["AST-02"]
    days = [i for i in range(len(a.days)) if unshared_private_worse(cat, a, i)]
    assert days, "veride böyle bir gün olmalı (AST-02'nin stresi nabızdan önce yükselir)"
    assert any(a.days[i].levels["beh_stress_score"] == 2 for i in days)  # stres KIRMIZI, görünürler en çok SARI
    # Kurgulanmış en uç durum (veride yok): aynı serinin bir gününde görünür HER ŞEY yeşil, yalnız stres KIRMIZI.
    # Türetilmiş alanlar dönüştürücünün yaptığı gibi bütün seviyelerden yeniden kurulur.
    a = a.model_copy(deep=True)
    lonely = a.days[0]
    lonely.levels = {c: (2 if c == "beh_stress_score" else 0) for c in lonely.levels}
    full = derive(cat, lonely.levels)
    lonely.health_status, lonely.main_concern, lonely.self_care, lonely.needs_ground_support = (
        full.health_status, full.main_concern, full.self_care, full.needs_ground_support)
    assert (lonely.health_status, lonely.main_concern, lonely.self_care, lonely.needs_ground_support) == (2, "behavioral", ["STRESS_RESET"], True)
    days = [0, *days]
    earth_strip = build_strip(cat, a, "tr", earth=True)
    for i in days:
        ship = build_day_view(cat, a, i, "tr")
        earth = build_day_view(cat, a, i, "tr", earth=True)
        visible_worst = max(v for c, v in a.days[i].levels.items() if c not in PRIVATE)
        assert ship.status > visible_worst and "STRESS_RESET" in [t.code for t in ship.todo]  # astronot kendi ekranında görür
        assert earth.status == visible_worst == earth.health_status == earth_strip[i].status
        assert earth.ground == (visible_worst == 2)
        assert not PRIVATE_ONLY_CODES & {t.code for t in earth.todo}
        assert earth.todo_masked_count == 0 and earth.todo_masked_text is None
        hidden = [r for r in earth.readings if r.hidden]
        assert {r.col for r in hidden} == set(PRIVATE)
        assert all((r.value, r.level, r.value_text, r.healthy_text, r.flag_text) == (None, None, "Paylaşılmadı", "", "") for r in hidden)
        if visible_worst == 0:  # görünür her şey yeşil: Dünya ekranı "Normal, yapılacak bir şey yok" der
            assert (earth.status_label, earth.main_concern, earth.main_concern_label, earth.todo) == ("Normal", "none", None, [])
            assert earth.calm_text and "paylaşılmadı" not in earth.subtitle.lower()
        text = earth.model_dump_json()
        assert "Stres seviyenizi" not in text and "1.3±0.5" not in text  # öneri başlığı ve stresin kişisel tabanı da gitmez


def test_shared_checkin_reveals_what_the_astronaut_chose_to_share(ast, cat) -> None:
    a = ast.by_id()["AST-02"]
    i = next(i for i in range(len(a.days)) if unshared_private_worse(cat, a, i) and a.days[i].levels["beh_stress_score"] == 2)
    row = CheckinSession(astronaut_id=a.meta.id, day_index=i, mission_day=a.days[i].mission_day, notes=[], done=True, share="scores")
    rec = earth_day(cat, a, i, row)
    assert rec.readings["beh_stress_score"].level == 2 and rec.status == 2 and rec.ground
    assert "STRESS_RESET" in [t.code for t in rec.todo]
    assert evaluate_day(cat, a, i, earth=True, shared=1).health_status == a.days[i].health_status


# ---------------------------------------------------------------- uçtan uca: DATASET_PATH ile gemi
@pytest.fixture(scope="module")
def ast_ship(tmp_path_factory: pytest.TempPathFactory):
    from app.main import create_app

    db = tmp_path_factory.mktemp("ast_ship") / "ship.db"
    settings = Settings(station_role="ship", data_source="astronaut_health", dataset_path=AST_FILE, database_url=sqlite_url(db),
                        earth_link_token="t")
    app = create_app(settings)
    with TestClient(app) as c:
        yield c, app


def test_ship_serves_the_selected_dataset(ast_ship) -> None:
    c, _app = ast_ship
    hint = c.get("/api/auth/hint").json()
    assert (hint["astronauts"]["first_id"], hint["astronauts"]["last_id"], hint["astronauts"]["count"]) == ("AST-01", "AST-04", 4)
    h = login(c, "AST-02")
    ov = c.get("/api/me", headers=h).json()
    assert (ov["n_days"], ov["astronaut"]["mission"], ov["astronaut"]["age"]) == (30, "ISS_LEO", None)
    assert ov["scores_note"] == "Bu veri setinde skor yok." and "ISS 180" in ov["source_note"]
    day = c.get(f"/api/me/days/{ov['today']}", headers=h).json()
    assert day["mission_day"] == 178 and len(day["readings"]) == 18 and day["range_label"].startswith("Normal")
    assert c.get("/api/personal/AST-01", headers=h).status_code == 403  # başkasının verisi yine kapalı


def test_marking_a_hidden_item_done_tells_earth_nothing(ast_ship) -> None:
    """Astronot stres kaynaklı öneriyi 'yaptım' diye işaretlerse Dünya'ya olay gitmez (maskeli olay da gitmez)."""
    c, app = ast_ship
    h = login(c, "AST-02")

    def action_events() -> list[dict]:
        with Session(app.state.engine) as db:
            return [e.payload for e in db.exec(select(OutboxEvent).where(OutboxEvent.type == "action.done")).all()]

    assert c.post("/api/actions/done", headers=h, json={"code": "STRESS_RESET", "done": True}).status_code == 200
    assert action_events() == []
    assert c.post("/api/actions/done", headers=h, json={"code": "HEART_RECOVERY_DAY", "done": True}).status_code == 200
    events = action_events()
    assert [(e["code"], e["masked"]) for e in events] == [("HEART_RECOVERY_DAY", False)]
    assert not any(code in json.dumps(events) for code in PRIVATE_ONLY_CODES)
    snap = c.get("/api/downlink/snapshot", headers={"Authorization": "Bearer t"}).json()
    blob = json.dumps(snap)
    assert not any(col in blob for col in PRIVATE) and not any(code in blob for code in PRIVATE_ONLY_CODES)


def test_default_dataset_and_database_stay_the_default() -> None:
    """DATASET_PATH ayarsızken hiçbir şey değişmez; başka veri seti kendi DB dosyasına yüklenir."""
    base = {"_env_file": None, "data_source": "astronaut_health", "database_url": None}  # test ortamındaki DATABASE_URL'i ez
    assert Settings(station_role="ship", **base).database_url_resolved.endswith("/processed/ship.db")
    other = Settings(station_role="ship", dataset_path=AST_FILE, **base)
    assert other.database_url_resolved.endswith("/processed/ship.astronaut_health_ast.db")
    assert Settings(station_role="earth", dataset_path=AST_FILE, **base).database_url_resolved.endswith("/processed/earth.db")
