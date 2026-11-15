"""AST görev verisini panelin `astronaut_health` biçimine çevirir (seviyesi veriden gelen format).

Kaynak: veri ekibinin v3.1 paketindeki LLM payload dosyaları (Türkçe ve İngilizce eşi; aynı kayıtlar):
    data/raw/ast/payloads_tr_mission_iss180.jsonl   · data/raw/ast/payloads_mission_iss180.jsonl
Çıktı:  data/raw/astronaut_health_ast.json  (DATASET_PATH ile seçilir)

Kullanım (backend/ içinde):
    python -m app.cli convert-ast [--source ../data/raw/ast] [--out ../data/raw/astronaut_health_ast.json]
                                  [--first-day 149] [--last-day 178]

HİÇBİR DEĞER ÜRETİLMEZ:
  - Ölçüm değeri, birim, seviye (`durum`) ve normal metni kaynaktan aynen alınır; ölçek dönüştürülmez
    (ruh hali ve stres 1–5 olarak kalır).
  - Kaynakta olmayan ölçüm kayda yazılmaz; panel "Bu görevde ölçülmedi" / "Bu veri dosyasında yok" gösterir.
  - Skor (alan, günlük, kümülatif) kaynakta yoktur ve üretilmez; panel "Bu veri setinde skor yok" gösterir.
  - Kaynakta olmayan dört alan (durum, ana endişe, öz bakım, yer desteği) seviyelerden, belgeli kurallarla
    türetilir: app/personal/derive.py. Yaş / cinsiyet / VKİ / desen kaynakta yoktur, boş kalır.
İki dosya gösterge gösterge karşılaştırılır; değer, birim ya da seviye farklıysa dönüştürme durur.
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.personal.catalog import PersonalCatalog, load_personal_catalog
from app.personal.dataset import FORMAT_LEVELS, parse_dataset
from app.personal.derive import derive

SOURCE_TR = "payloads_tr_mission_iss180.jsonl"
SOURCE_EN = "payloads_mission_iss180.jsonl"
PACKAGE = "ai_gambit_final_dataset_v3_1"
MISSION = "ISS_LEO"  # kaynak: mission_iss180 (ISS, 180 gün)

LEVEL_TR = {"YEŞİL": 0, "SARI": 1, "KIRMIZI": 2}
LEVEL_EN = {"GREEN": 0, "YELLOW": 1, "RED": 2}

# panel kolonu → (kaynaktaki Türkçe ad, İngilizce ad, kaynak birim)
SOURCE_INDICATORS: dict[str, tuple[str, str, str]] = {
    "exp_radiation_mSv_day": ("Habitat radyasyonu (doz eşdeğeri, tahmini)", "Habitat radiation, dose equivalent (estimated)", "mSv/day"),
    "exp_cabin_co2_mmHg": ("Kabin CO2", "Cabin CO2", "mmHg"),
    "imm_body_temp_C": ("Vücut sıcaklığı", "Body temperature", "degC"),
    "cv_systolic_bp_mmHg": ("Kan basıncı", "Blood pressure", "mmHg"),  # kaynak "sistolik/diyastolik" yazar
    "cv_resting_hr_bpm": ("Dinlenik nabız", "Resting heart rate", "bpm"),
    "cv_hrv_ms": ("Kalp hızı değişkenliği (HRV)", "Heart rate variability (HRV)", "ms"),
    "bone_bmd_change_pct": ("Kemik yoğunluğu değişimi", "Bone density change", "%"),
    "bone_exercise_min": ("Egzersiz süresi", "Exercise duration", "min"),
    "beh_sleep_h": ("Uyku süresi", "Sleep duration", "h"),
    "beh_mood_score": ("Ruh hali", "Mood", "score_1_5"),
    "beh_stress_score": ("Stres", "Stress", "score_1_5"),
}
# Kaynak pakette hiç ölçülmeyen panel ölçümleri
NOT_MEASURED = (
    "cv_ectopic_beats_per_h", "imm_symptom_score", "imm_lymphocytes_e9L",
    "bone_urine_calcium_mg_day", "beh_attention_lapses", "imm_cortisol_nmolL",
)
# Pakette ayda bir ölçülüyor (daily_wide.csv) ama bu payload dosyasında yok
NOT_IN_FILE = ("bone_muscle_strength_change_pct",)
# Kaynağın 1–5 öz bildirim ölçeği (score_1_5): panelde dönüştürülmeden "3/5" yazılır
SCALE_1_5 = ("beh_mood_score", "beh_stress_score")

NOTES: dict[str, dict[str, str]] = {
    "source_note": {
        "tr": "Veri: ISS 180 günlük görev, veri seti v3.1 (görev günü {first}–{last}). Radyasyon: NASA RadLab DOSTEL-2 "
              "ölçümü (doz eşdeğeri tahmindir). Diğer ölçümler sentetiktir, yayımlanmış uzay çalışmalarına kalibre "
              "edilmiştir. Klinik karar için değildir.",
        "en": "Data: ISS 180-day mission, dataset v3.1 (mission days {first}–{last}). Radiation: NASA RadLab DOSTEL-2 "
              "measurement (dose equivalent is an estimate). All other readings are synthetic, calibrated to published "
              "spaceflight studies. Not for clinical decisions.",
    },
    "readings_note": {
        "tr": "Değerler o günün ölçümüdür; kemik yoğunluğu değişimi son haftalık ölçümden taşınır. Renk, veri setindeki "
              "kural motorunun o gün verdiği işarettir: sarı = uyarı, kırmızı = kritik; yeşil, işaret olmadığı anlamına gelir.",
        "en": "Values are that day's measurements; bone density change is carried from the latest weekly scan. The colour is "
              "the flag the dataset's rule engine raised on that day: yellow = warning, red = critical; green means no flag.",
    },
    "threshold_note": {
        "tr": "Normal sütunu kişisel tabanı ya da NASA / klinik referansını gösterir; referans çizgisi tek başına alarm "
              "değildir. Öz bakım önerileri panelin kataloğundandır, tıbbi doğrulama yapılmamıştır.",
        "en": "The Normal column shows the personal baseline or a NASA / clinical reference; a reference line alone is not "
              "an alarm. Self-care suggestions come from the panel's catalog and have not been medically validated.",
    },
    "range_label": {"tr": "Normal (kişisel taban ya da referans)", "en": "Normal (personal baseline or reference)"},
}

RULES_TR = [
    "Ölçüm değeri, seviye (durum: YEŞİL=0, SARI=1, KIRMIZI=2) ve normal metni kaynak dosyadan aynen alınmıştır.",
    "Kan basıncı kaynakta 'sistolik/diyastolik' yazılır: sayı olarak sistolik, ekranda kaynaktaki yazılış kullanılır.",
    "Durum = o günkü en kötü seviye (0 Normal, 1 Dikkat, 2 Rahatsız).",
    "Yer desteği = en az bir gösterge kırmızı.",
    "Ana endişe = en kötü seviyedeki ilk göstergenin (panel kataloğu sırası) alanı; sadece ortam ölçümüyse 'none'.",
    "Öz bakım = seviyesi katalogdaki tetik eşiğine ulaşan göstergenin katalogdaki önerisi (önce kırmızılar).",
    "Skor yoktur. Yaş, cinsiyet, VKİ ve desen kaynakta olmadığı için boştur.",
]


class ConvertError(ValueError):
    """Kaynak dosyalar beklenen biçimde değil ya da birbiriyle tutarsız."""


def _load(path: Path) -> dict[tuple[str, int], dict[str, dict[str, Any]]]:
    """(astronot, görev günü) → {gösterge adı: gösterge kaydı}."""
    if not path.exists():
        raise ConvertError(f"Kaynak dosya yok: {path}")
    out: dict[tuple[str, int], dict[str, dict[str, Any]]] = {}
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            r = json.loads(line)
            key = (str(r["astronot_id"]), int(r["gorev_gunu"]))
            if key in out:
                raise ConvertError(f"{path.name}: aynı astronot ve gün iki kez: {key}")
            out[key] = {g["ad"]: g for g in r["gostergeler"]}
    return out


def _number(raw: Any) -> float:
    """Kaynaktaki değer → sayı. 'sistolik/diyastolik' yazılışında sistolik (ilk sayı)."""
    if isinstance(raw, str):
        raw = raw.split("/")[0]
    return float(raw)


def _decimals(v: float) -> int:
    """Sayıyı kayıpsız yazmak için gereken ondalık basamak (50.0 → 0, 21.4 → 1, -3.06 → 2)."""
    return max(0, -int(Decimal(repr(v)).normalize().as_tuple().exponent))


def _sha256(path: Path) -> str:
    """Kaynak dosyanın özeti, satır sonundan bağımsız (paketteki dosyalar LF'dir; git CRLF'ye çevirmiş olabilir)."""
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def convert(source_dir: Path, first_day: int, last_day: int, cat: PersonalCatalog | None = None) -> dict[str, Any]:
    """Kaynak klasör → `astronaut_health+levels/1` belgesi (dict)."""
    cat = cat or load_personal_catalog()
    tr_path, en_path = source_dir / SOURCE_TR, source_dir / SOURCE_EN
    tr, en = _load(tr_path), _load(en_path)
    if set(tr) != set(en):
        raise ConvertError("Türkçe ve İngilizce dosyanın (astronot, gün) kümeleri farklı")
    unknown = [c for c in (*SOURCE_INDICATORS, *NOT_MEASURED, *NOT_IN_FILE) if cat.indicator(c) is None]
    if unknown or sorted((*SOURCE_INDICATORS, *NOT_MEASURED, *NOT_IN_FILE)) != sorted(cat.columns):
        raise ConvertError(f"Eşleme panel kataloğuyla aynı kolonları kapsamıyor (bilinmeyen: {unknown})")

    astronauts = sorted({aid for aid, _ in tr})
    days = list(range(first_day, last_day + 1))
    records: list[dict[str, Any]] = []
    need_dec: dict[str, int] = dict.fromkeys(SOURCE_INDICATORS, 0)
    for aid in astronauts:
        for day in days:
            if (aid, day) not in tr:
                raise ConvertError(f"{aid} görev günü {day}: kaynakta kayıt yok")
            g_tr, g_en = tr[(aid, day)], en[(aid, day)]
            rec: dict[str, Any] = {"astronaut_id": aid, "mission_day": day}
            levels: dict[str, int] = {}
            normal: dict[str, dict[str, str]] = {}
            display: dict[str, str] = {}
            for col, (name_tr, name_en, unit) in SOURCE_INDICATORS.items():
                x, y = g_tr.get(name_tr), g_en.get(name_en)
                where = f"{aid} görev günü {day} · {name_tr}"
                if x is None or y is None or x["deger"] is None:
                    raise ConvertError(f"{where}: kaynakta yok (sessiz boşluk bırakılmaz)")
                if x["deger"] != y["deger"] or x["birim"] != y["birim"]:
                    raise ConvertError(f"{where}: Türkçe ve İngilizce dosyada değer/birim farklı")
                if x["birim"] != unit:
                    raise ConvertError(f"{where}: beklenen birim {unit}, kaynakta {x['birim']}")
                if x["durum"] not in LEVEL_TR or LEVEL_TR[x["durum"]] != LEVEL_EN.get(y["durum"]):
                    raise ConvertError(f"{where}: seviye tanınmadı ya da iki dosyada farklı ({x['durum']} / {y['durum']})")
                value = _number(x["deger"])
                rec[col] = value
                levels[col] = LEVEL_TR[x["durum"]]
                need_dec[col] = max(need_dec[col], _decimals(value))
                if x.get("normal") or y.get("normal"):
                    normal[col] = {"tr": x.get("normal") or y["normal"], "en": y.get("normal") or x["normal"]}
                if isinstance(x["deger"], str):
                    display[col] = x["deger"]  # kaynaktaki yazılış, örn. "116/82"
            d = derive(cat, levels)
            rec["levels"] = levels
            rec["normal"] = normal
            if display:
                rec["display"] = display
            rec["health_status"] = d.health_status
            rec["main_concern"] = d.main_concern
            rec["self_care_actions"] = d.self_care
            rec["needs_ground_support"] = d.needs_ground_support
            records.append(rec)

    # Kataloğu ezen alanlar: kaynaktaki ad, ölçek (1–5) ve kaynağın ondalık hassasiyeti
    overrides: dict[str, dict[str, Any]] = {}
    for col in SOURCE_INDICATORS:
        ind = cat.indicator(col)
        assert ind is not None
        ov: dict[str, Any] = {}
        if need_dec[col] != ind.dec:
            ov["dec"] = need_dec[col]
        if col in SCALE_1_5:
            ov["unit"] = {"tr": "1-5", "en": "1-5"}
            ov["scale_max"] = 5
        # Ölçümün adı kaynaktaki addır: panel, asistan ve tahmin aynı ölçüme aynı adı söyler
        ov["label"] = {"tr": SOURCE_INDICATORS[col][0], "en": SOURCE_INDICATORS[col][1]}
        overrides[col] = ov

    fmt = {"first": first_day, "last": last_day}
    doc: dict[str, Any] = {
        "format": FORMAT_LEVELS,
        "_source": {
            "package": PACKAGE,
            "files": {
                "tr": {"name": SOURCE_TR, "sha256": _sha256(tr_path)},
                "en": {"name": SOURCE_EN, "sha256": _sha256(en_path)},
            },
            "script": "backend/app/personal/ast_convert.py (python -m app.cli convert-ast)",
            "window": {"first_mission_day": first_day, "last_mission_day": last_day},
            "rules": RULES_TR,
        },
        "dataset": {
            "levels_from_data": True,
            "averaged": False,
            "has_scores": False,
            "indicators": overrides,
            "absent": {**dict.fromkeys(NOT_MEASURED, "not_measured"), **dict.fromkeys(NOT_IN_FILE, "not_in_file")},
            **{k: {lang: text.format(**fmt) for lang, text in v.items()} for k, v in NOTES.items()},
        },
        "astronauts": [{"astronaut_id": aid, "mission": MISSION} for aid in astronauts],
        "records": records,
    }
    parse_dataset(doc, cat=cat)  # panelin okuyacağı biçimde geçerli mi (katalogla tutarlılık dahil)
    return doc


def write(doc: dict[str, Any], out_path: Path) -> None:
    """Aynı kaynak → bayt bayt aynı dosya (anahtar sırası sabit, zaman damgası yok)."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
