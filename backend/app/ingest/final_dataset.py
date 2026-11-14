"""AI Gambit final dataset v1 adaptörü ve yükleyicisi.

Dataset klasörü (zip açılmış hali):
    <kök>/crew_profiles.csv
    <kök>/<senaryo>/daily_long.csv    astronaut_id,date,metric,value,unit,source,is_synthetic,n,quality_flag
    <kök>/<senaryo>/checkins.csv      astronaut_id,timestamp,mission_day,mood,stress,sleep_quality,note,...
Senaryolar: mission_iss180 (demo), control_iss180 (olay yok, yanlış alarm sayımı), mission_mars860.

Bu modülün yaptığı dönüşümler (hepsi ŞEKİL dönüşümü; değerler değişmez):
  1. Kimlikler: A1..A4 (ISS) ve M1..M4 (Mars) → AST-01..AST-04. Aynı dört kurgusal kişi; böylece
     arayüz, testler ve LLM prompt'larındaki AST-xx kimlikleri aynen çalışır.
  2. `quality_flag = missing` / boş değer satırları atlanır (veri boşluğu = ölçüm yok).
  3. `habitat` satırları astronot DEĞİLDİR. Radyasyon dozu (aynı araçtaki herkes için ortak ortam ölçümü)
     her mürettebat üyesine kopyalanır; ISS'te bunlar GERÇEK RadLab (DOSTEL-2) değerleridir, kaynak etiketi
     korunur. Kabin CO2, gürültü, yerçekimi, iletişim gecikmesi gibi bağlam metrikleri şimdilik yüklenmez:
     API şemasında ortam/habitat kavramı yok (HealthSystem listesi sabit). Atlananlar raporda listelenir.
  4. Metrik adları ve birimler `config/metrics.yaml` alias'larıyla çözülür (pipeline.normalize_frame).

Kullanım:
    python -m app.cli seed --final-dataset [KLASÖR] [--part mission_iss180]
    POST /api/ingest  (daily_long.csv yüklenirse bu adaptör otomatik seçilir)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from app.analysis.catalog import Catalog, load_catalog
from app.ingest.base import LONG_COLUMNS, BaseAdapter, ParseContext, read_csv, register_adapter

PARTS = ("mission_iss180", "control_iss180", "mission_mars860")
DATASET_DIRNAME = "ai_gambit_final_dataset_v1"
HABITAT_ID = "habitat"

# habitat satırlarından her mürettebat üyesine kopyalanan ortak ortam ölçümleri
HABITAT_SHARED_METRICS = frozenset({
    "estimated_daily_dose_equivalent",  # ISS: RadLab soğurulan doz × 2.26 (doz eşdeğeri, mSv/gün)
    "daily_radiation_dose",             # Mars/diğer: doz eşdeğeri, mSv/gün
    "cumulative_radiation_dose",        # mSv
})

_REQUIRED_HEADER = {"astronaut_id", "date", "metric", "value", "quality_flag", "is_synthetic"}
_CREW_ID = re.compile(r"^[AaMm](\d{1,2})$")


def map_crew_id(raw: object) -> str:
    """'A2' / 'M2' → 'AST-02'. Tanınmayan kimlik olduğu gibi döner (boşluklar kırpılır)."""
    s = str(raw).strip()
    m = _CREW_ID.match(s)
    return f"AST-{int(m.group(1)):02d}" if m else s


@dataclass
class FinalLongStats:
    rows_in_file: int = 0
    missing_rows_dropped: int = 0
    habitat_rows_shared: int = 0
    habitat_metrics_skipped: dict[str, int] = field(default_factory=dict)
    crew: list[str] = field(default_factory=list)


def to_long(raw: pd.DataFrame, stats: FinalLongStats | None = None) -> pd.DataFrame:
    """Dataset'in daily_long tablosu (tümü str) → LONG_COLUMNS + 'row'."""
    stats = stats if stats is not None else FinalLongStats()
    df = raw.copy()
    df["row"] = df.index + 2  # 1. satır başlık
    stats.rows_in_file = len(df)

    value = df["value"].astype("string").str.strip()
    flag = df["quality_flag"].astype("string").str.strip().str.lower()
    gap = value.isna() | (value == "") | (flag == "missing")
    stats.missing_rows_dropped = int(gap.sum())
    df = df[~gap]

    is_habitat = df["astronaut_id"].astype("string").str.strip().str.lower() == HABITAT_ID
    crew = df[~is_habitat].copy()
    crew["astronaut_id"] = crew["astronaut_id"].map(map_crew_id)
    crew_ids = sorted(crew["astronaut_id"].unique().tolist())
    stats.crew = crew_ids

    hab = df[is_habitat]
    shared_mask = hab["metric"].astype("string").str.strip().isin(HABITAT_SHARED_METRICS)
    stats.habitat_metrics_skipped = {str(k): int(v) for k, v in hab.loc[~shared_mask, "metric"].value_counts().items()}
    shared = hab[shared_mask]
    copies = [shared.assign(astronaut_id=aid) for aid in crew_ids]
    stats.habitat_rows_shared = int(sum(len(c) for c in copies))

    out = pd.concat([crew, *copies], ignore_index=True)
    out = out.rename(columns={"date": "timestamp"})
    for col in LONG_COLUMNS:
        if col not in out.columns:
            out[col] = None
    return out[[*LONG_COLUMNS, "row"]].reset_index(drop=True)


@register_adapter
class FinalDatasetLongAdapter(BaseAdapter):
    """AI Gambit final dataset v1 daily_long.csv. long_csv'den ÖNCE kayıtlıdır (aynı kolonları da içerir)."""

    name = "final_dataset_long"

    def can_handle(self, filename: str, head: str, ctx: ParseContext) -> bool:
        if not head or head.lstrip()[:1] in ("[", "{"):
            return False
        first = head.splitlines()[0].lstrip("﻿")
        cols = {c.strip().strip('"').lower() for c in first.split(",")}
        return _REQUIRED_HEADER <= cols

    def parse(self, content: bytes, ctx: ParseContext) -> pd.DataFrame:
        return to_long(read_csv(content))


# ----------------------------------------------------------------------------- klasörden yükleme (seed)
@dataclass
class FinalDataset:
    part: str
    root: Path
    astronauts: list[dict]
    measurements: pd.DataFrame  # LONG_COLUMNS, normalize edilmiş (katalog adı + birimi, naive UTC)
    checkins: list[dict]
    stats: FinalLongStats
    rejected: int
    unknown_metrics: dict[str, int]
    warnings: list[str]


def resolve_root(path: str | Path, part: str = PARTS[0]) -> Path:
    """Klasörü bul: <path>/<part> ya da zip'ten çıkan iç içe <path>/ai_gambit_final_dataset_v1/<part>."""
    p = Path(path)
    for cand in (p, p / DATASET_DIRNAME):
        if (cand / part / "daily_long.csv").is_file():
            return cand
    raise FileNotFoundError(
        f"Final dataset bulunamadı: '{p}' altında '{part}/daily_long.csv' yok. "
        f"Zip'i data/raw/ altına açın (data/raw/{DATASET_DIRNAME}/{part}/...) veya --final-dataset ile klasörü verin."
    )


def _crew_info(root: Path) -> dict[str, dict]:
    f = root / "crew_profiles.csv"
    if not f.is_file():
        return {}
    prof = pd.read_csv(f, dtype=str, keep_default_na=False)
    out: dict[str, dict] = {}
    for r in prof.itertuples(index=False):
        aid = map_crew_id(r.astronaut_id)
        out[aid] = {"id": aid, "name": r.name or aid, "role": r.role or None}
    return out


def _checkins(root: Path, part: str) -> list[dict]:
    from app.safety.emergency import detect_emergency

    f = root / part / "checkins.csv"
    if not f.is_file():
        return []
    raw = pd.read_csv(f, dtype=str, keep_default_na=False)
    ts = pd.to_datetime(raw["timestamp"], utc=True, errors="coerce")
    out: list[dict] = []
    for r, t in zip(raw.itertuples(index=False), ts, strict=True):
        if pd.isna(t):
            continue
        note = r.note.strip() or None
        out.append({
            "astronaut_id": map_crew_id(r.astronaut_id),
            "timestamp": t.to_pydatetime(),
            "mood": int(float(r.mood)),
            "stress": int(float(r.stress)),
            "sleep_quality": int(float(r.sleep_quality)),
            "note": note,
            "share_with_ground": r.share_with_ground.strip().lower() == "true",
            # POST /api/checkin ile aynı kural: not acil belirti içeriyorsa işaretle (LLM'siz)
            "emergency": detect_emergency(note, "en") is not None,
        })
    return out


def load_final_dataset(path: str | Path, part: str = PARTS[0], catalog: Catalog | None = None) -> FinalDataset:
    from app.ingest.pipeline import normalize_frame

    if part not in PARTS:
        raise ValueError(f"Bilinmeyen senaryo: {part}. Seçenekler: {', '.join(PARTS)}")
    catalog = catalog or load_catalog()
    root = resolve_root(path, part)
    stats = FinalLongStats()
    raw = to_long(read_csv((root / part / "daily_long.csv").read_bytes()), stats)
    valid, _errors, unknown, warnings, rejected = normalize_frame(raw, catalog, None, f"final_dataset:{part}")

    info = _crew_info(root)
    ids = sorted(valid["astronaut_id"].unique().tolist())
    astronauts = [info.get(aid, {"id": aid, "name": aid, "role": None}) for aid in ids]
    checkins = [c for c in _checkins(root, part) if c["astronaut_id"] in set(ids)]
    if stats.habitat_metrics_skipped:
        warnings.append("Habitat bağlam metrikleri yüklenmedi (şemada ortam yok): "
                        + ", ".join(f"{k} ({v})" for k, v in sorted(stats.habitat_metrics_skipped.items())))
    return FinalDataset(part=part, root=root, astronauts=astronauts, measurements=valid.reset_index(drop=True),
                        checkins=checkins, stats=stats, rejected=rejected, unknown_metrics=unknown, warnings=warnings)
