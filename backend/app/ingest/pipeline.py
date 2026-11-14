"""Ingest boru hattı: adaptör seç → ortak formata çevir → doğrula/normalize et → DB'ye yaz → rapor.

Tüm adaptörler için ortak doğrulamalar:
  - astronaut_id yoksa varsayılan (?astronaut_id=) kullanılır, o da yoksa satır reddedilir
  - metrik adı katalog adı veya alias ile çözülür (bilinmeyen → red, raporda listelenir)
  - değer sayısal olmalı
  - zaman damgası ISO-8601 / yaygın formatlar / unix epoch (s veya ms); UTC'ye çevrilir
  - birim boşsa katalog birimi; farklıysa dönüştürülür (°F→°C, lb→kg, ...), dönüşüm yoksa red
"""

import pandas as pd
from sqlmodel import Session

import app.ingest.adapters  # noqa: F401  (yerleşik adaptörleri kaydeder)
from app.analysis.catalog import Catalog, load_catalog
from app.ingest.base import ADAPTERS, LONG_COLUMNS, ParseContext, decode, detect_adapter
from app.ingest.store import ensure_astronauts, insert_measurements
from app.ingest.units import convert, normalize_unit
from app.models.schemas import DateWindow, IngestReport, IngestRowError
from app.models.tables import IngestBatch

MAX_ERROR_SAMPLES = 20


class IngestError(ValueError):
    """Dosya hiç işlenemediğinde (format tanınmadı vb.)."""


def parse_timestamps(raw: pd.Series) -> pd.Series:
    """Karışık formatlı zaman damgalarını naive UTC'ye çevir; çözülemeyen → NaT."""
    s = raw.astype("string").str.strip()
    numeric = pd.to_numeric(s, errors="coerce")
    out = pd.to_datetime(s.where(numeric.isna()), utc=True, errors="coerce", format="ISO8601")
    missing = out.isna() & s.notna() & numeric.isna() & (s != "")
    if missing.any():
        out = out.where(~missing, pd.to_datetime(s.where(missing), utc=True, errors="coerce", format="mixed", dayfirst=False))
    if numeric.notna().any():
        secs = numeric.where(numeric < 1e11, numeric / 1000.0)  # ms epoch → s
        out = out.where(numeric.isna(), pd.to_datetime(secs, unit="s", utc=True, errors="coerce"))
    return out.dt.tz_convert("UTC").dt.tz_localize(None)


def normalize_frame(
    df: pd.DataFrame, catalog: Catalog, default_astronaut: str | None, default_source: str
) -> tuple[pd.DataFrame, list[IngestRowError], dict[str, int], list[str], int]:
    """Doğrula ve normalize et. Dönüş: (geçerli_df, hata_örnekleri, bilinmeyen_metrik_sayıları, uyarılar, red_sayısı)."""
    df = df.copy()
    errors: list[IngestRowError] = []
    warnings: list[str] = []
    reason = pd.Series(pd.NA, index=df.index, dtype="string")

    def reject(mask: pd.Series, why: str, col: str | None = None) -> None:
        nonlocal reason
        newly = mask & reason.isna()
        reason = reason.mask(newly, why)
        for idx in df.index[newly][: max(0, MAX_ERROR_SAMPLES - len(errors))]:
            val = df.at[idx, col] if col else None
            errors.append(IngestRowError(row=int(df.at[idx, "row"]), reason=why, value=None if val is None else str(val)))

    # astronot
    aid = df["astronaut_id"].astype("string").str.strip()
    if default_astronaut:
        aid = aid.mask(aid.isna() | (aid == ""), default_astronaut)
    df["astronaut_id"] = aid
    reject(aid.isna() | (aid == ""), "missing_astronaut")

    # metrik
    raw_metric = df["metric"].astype("string").str.strip()
    resolved = raw_metric.map(lambda m: (catalog.resolve(m).name if catalog.resolve(m) else None) if isinstance(m, str) else None)
    unknown_mask = resolved.isna()
    unknown_counts = raw_metric[unknown_mask & reason.isna()].value_counts().to_dict()
    reject(unknown_mask, "unknown_metric", "metric")
    df["metric"] = resolved

    # değer
    values = pd.to_numeric(df["value"], errors="coerce")
    reject(values.isna(), "invalid_value", "value")
    df["value"] = values

    # zaman
    ts = parse_timestamps(df["timestamp"])
    reject(ts.isna(), "invalid_timestamp", "timestamp")
    df["timestamp"] = ts

    # birim
    units = df["unit"].map(normalize_unit)
    for metric in df.loc[reason.isna(), "metric"].dropna().unique():
        target = catalog.metrics[metric].unit
        m_mask = (df["metric"] == metric) & reason.isna()
        u = units[m_mask].fillna(target)
        for src_unit in u.unique():
            sel = m_mask & (units.fillna(target) == src_unit)
            if src_unit == target:
                continue
            converted = convert(df.loc[sel, "value"], src_unit, target)
            if converted is None:
                reject(sel, "unit_mismatch", "unit")
            else:
                df.loc[sel, "value"] = converted
                warnings.append(f"{metric}: {int(sel.sum())} satır {src_unit} → {target} dönüştürüldü")
        units = units.mask(m_mask, target)
    df["unit"] = units

    # kaynak
    src = df["source"].astype("string").str.strip()
    df["source"] = src.mask(src.isna() | (src == ""), default_source)

    rejected = int(reason.notna().sum())
    valid = df[reason.isna()][LONG_COLUMNS].copy()
    for name, count in unknown_counts.items():
        warnings.append(f"Bilinmeyen metrik atlandı: {name} ({count} satır)")
    return valid, errors, {str(k): int(v) for k, v in unknown_counts.items()}, warnings, rejected


def ingest_bytes(
    session: Session,
    filename: str,
    content: bytes,
    adapter_name: str | None = None,
    default_astronaut: str | None = None,
    catalog: Catalog | None = None,
) -> IngestReport:
    catalog = catalog or load_catalog()
    ctx = ParseContext(filename=filename, catalog=catalog, default_astronaut=default_astronaut,
                       default_source=f"ingest:{filename}")
    if adapter_name:
        adapter = ADAPTERS.get(adapter_name)
        if adapter is None:
            raise IngestError(f"Bilinmeyen adaptör: {adapter_name}. Seçenekler: {', '.join(ADAPTERS)}")
    else:
        adapter = detect_adapter(filename, decode(content[:4096]), ctx)
        if adapter is None:
            raise IngestError(
                "Dosya formatı tanınmadı. Long CSV (metric,value kolonları), wide CSV (metrik kolonları) "
                "veya JSON kayıt listesi bekleniyor; ya da ?adapter= ile zorlayın."
            )
    try:
        raw = adapter.parse(content, ctx)
    except Exception as e:  # noqa: BLE001
        raise IngestError(f"{adapter.name} dosyayı okuyamadı: {e}") from e

    valid, errors, unknown, warnings, rejected = normalize_frame(raw, catalog, default_astronaut, ctx.default_source)

    batch = IngestBatch(filename=filename, adapter=adapter.name, rows_total=len(raw))
    session.add(batch)
    session.flush()
    created = ensure_astronauts(session, valid["astronaut_id"].unique())
    if created:
        warnings.append(f"Yeni astronot kaydı oluşturuldu: {', '.join(created)}")
    inserted = insert_measurements(session, valid, batch.id)
    duplicates = len(valid) - inserted

    batch.rows_accepted = inserted
    batch.rows_duplicate = duplicates
    batch.rows_rejected = rejected
    batch.warnings = warnings
    session.add(batch)
    session.commit()

    date_range = None
    if not valid.empty:
        date_range = DateWindow(start=valid["timestamp"].min().date(), end=valid["timestamp"].max().date())
    return IngestReport(
        batch_id=batch.id,
        filename=filename,
        adapter=adapter.name,
        rows_total=len(raw),
        rows_accepted=inserted,
        rows_duplicate=duplicates,
        rows_rejected=rejected,
        unknown_metrics=sorted(unknown),
        astronauts=sorted(valid["astronaut_id"].unique().tolist()),
        date_range=date_range,
        warnings=warnings,
        errors_sample=errors,
    )
