"""Yerleşik adaptörler: final_dataset_long, long_csv, wide_csv, json_records.

Tespit sırası kayıt sırasıdır (önce final dataset, sonra long, sonra wide, sonra JSON).
final_dataset_long, long_csv'nin de tanıyacağı kolonları içerdiği için önce kaydedilir.
"""

import json

import pandas as pd

import app.ingest.final_dataset  # noqa: F401  (FinalDatasetLongAdapter'ı long_csv'den ÖNCE kaydeder)

from app.analysis.catalog import normalize_key
from app.ingest.base import (
    LONG_COLUMNS,
    BaseAdapter,
    ParseContext,
    decode,
    map_columns,
    read_csv,
    register_adapter,
    sniff_sep,
)


def _header(head: str) -> list[str]:
    first = head.splitlines()[0] if head else ""
    return [c.strip().strip('"') for c in first.split(sniff_sep(first))]


def _finish(df: pd.DataFrame, row_offset: int) -> pd.DataFrame:
    for col in LONG_COLUMNS:
        if col not in df.columns:
            df[col] = None
    df["row"] = df.index + row_offset
    return df[[*LONG_COLUMNS, "row"]]


@register_adapter
class LongCsvAdapter(BaseAdapter):
    """Her satır bir ölçüm: astronaut_id,timestamp,metric,value[,unit,source]"""

    name = "long_csv"

    def can_handle(self, filename: str, head: str, ctx: ParseContext) -> bool:
        if filename.lower().endswith(".json") or head.lstrip()[:1] in ("[", "{"):
            return False
        cols = map_columns(_header(head))
        return "metric" in cols and "value" in cols and "timestamp" in cols

    def parse(self, content: bytes, ctx: ParseContext) -> pd.DataFrame:
        raw = read_csv(content)
        cols = map_columns(list(raw.columns))
        df = pd.DataFrame({std: raw[orig] for std, orig in cols.items()})
        return _finish(df, row_offset=2)  # 1. satır başlık


@register_adapter
class WideCsvAdapter(BaseAdapter):
    """Her satır bir zaman noktası, her metrik bir kolon: astronaut_id,timestamp,resting_hr,hrv,..."""

    name = "wide_csv"

    def can_handle(self, filename: str, head: str, ctx: ParseContext) -> bool:
        if filename.lower().endswith(".json") or head.lstrip()[:1] in ("[", "{"):
            return False
        header = _header(head)
        cols = map_columns(header)
        if "timestamp" not in cols or "metric" in cols:
            return False
        return any(ctx.catalog.resolve(h) for h in header if h not in cols.values())

    def parse(self, content: bytes, ctx: ParseContext) -> pd.DataFrame:
        raw = read_csv(content)
        cols = map_columns(list(raw.columns))
        id_cols = [c for c in (cols.get("astronaut_id"), cols.get("timestamp"), cols.get("source")) if c]
        metric_cols = [c for c in raw.columns if c not in id_cols and c not in (cols.get("unit"),)]
        raw = raw.reset_index(names="_row")
        long = raw.melt(id_vars=["_row", *id_cols], value_vars=metric_cols, var_name="metric", value_name="value")
        long = long[long["value"].astype(str).str.strip() != ""]
        df = pd.DataFrame({
            "astronaut_id": long[cols["astronaut_id"]] if "astronaut_id" in cols else None,
            "timestamp": long[cols["timestamp"]],
            "metric": long["metric"],
            "value": long["value"],
            "source": long[cols["source"]] if "source" in cols else None,
        })
        df = _finish(df.reset_index(drop=True), 0)
        df["row"] = long["_row"].to_numpy() + 2
        return df


@register_adapter
class JsonRecordsAdapter(BaseAdapter):
    """JSON: kayıt listesi (long veya wide) ya da {"measurements"|"data"|"records": [...]}."""

    name = "json_records"
    LIST_KEYS = ("measurements", "data", "records", "items", "observations")

    def can_handle(self, filename: str, head: str, ctx: ParseContext) -> bool:
        return filename.lower().endswith(".json") or head.lstrip()[:1] in ("[", "{")

    def parse(self, content: bytes, ctx: ParseContext) -> pd.DataFrame:
        data = json.loads(decode(content))
        top_astronaut = None
        if isinstance(data, dict):
            top_astronaut = next((data[k] for k in data if normalize_key(k) in ("astronaut_id", "astronaut", "subject_id")), None)
            data = next((data[k] for k in self.LIST_KEYS if isinstance(data.get(k), list)), [data])
        if not isinstance(data, list):
            raise ValueError("JSON must be a list of records")
        raw = pd.DataFrame([r for r in data if isinstance(r, dict)])
        if raw.empty:
            return _finish(pd.DataFrame(columns=LONG_COLUMNS), 1)
        cols = map_columns(list(raw.columns))
        if "metric" in cols and "value" in cols:
            df = pd.DataFrame({std: raw[orig] for std, orig in cols.items()})
            df = _finish(df, row_offset=1)
        else:  # wide JSON: anahtarlar metrik adları
            id_cols = [c for c in (cols.get("astronaut_id"), cols.get("timestamp"), cols.get("source")) if c]
            metric_cols = [c for c in raw.columns if c not in id_cols]
            raw = raw.reset_index(names="_row")
            long = raw.melt(id_vars=["_row", *id_cols], value_vars=metric_cols, var_name="metric", value_name="value")
            long = long[long["value"].notna()]
            df = pd.DataFrame({
                "astronaut_id": long[cols["astronaut_id"]] if "astronaut_id" in cols else None,
                "timestamp": long[cols["timestamp"]] if "timestamp" in cols else None,
                "metric": long["metric"],
                "value": long["value"],
                "source": long[cols["source"]] if "source" in cols else None,
            }).reset_index(drop=True)
            rows = long["_row"].to_numpy() + 1
            df = _finish(df, 0)
            df["row"] = rows
        if top_astronaut is not None:
            df["astronaut_id"] = df["astronaut_id"].where(df["astronaut_id"].notna(), top_astronaut)
        return df
