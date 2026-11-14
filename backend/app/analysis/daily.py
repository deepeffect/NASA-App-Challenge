"""Ham long ölçümler → günlük agregasyon (astronot × metrik × gün)."""

import numpy as np
import pandas as pd

from app.analysis.catalog import Catalog

DAILY_COLUMNS = ["astronaut_id", "metric", "day", "value", "min", "max", "n"]


def to_utc_naive(ts: pd.Series) -> pd.Series:
    """aware/naive karışık zaman damgaları → naive UTC datetime64."""
    return pd.to_datetime(ts, utc=True).dt.tz_localize(None)


def to_daily(df: pd.DataFrame, catalog: Catalog) -> pd.DataFrame:
    """Her (astronot, metrik, gün) için katalogdaki agregasyonla günlük değer + gün içi min/max/adet.

    `day` kolonu gece yarısına yuvarlanmış naive UTC datetime64'tür.
    """
    if df.empty:
        return pd.DataFrame(columns=DAILY_COLUMNS)
    d = pd.DataFrame({
        "astronaut_id": df["astronaut_id"].astype(str),
        "metric": df["metric"].astype(str),
        "ts": to_utc_naive(df["timestamp"]),
        "value": pd.to_numeric(df["value"], errors="coerce"),
    }).dropna(subset=["value"])
    d["day"] = d["ts"].dt.floor("D")
    d = d.sort_values("ts", kind="stable")
    agg = (
        d.groupby(["astronaut_id", "metric", "day"], sort=True)["value"]
        .agg(["mean", "sum", "min", "max", "last", "count"])
        .reset_index()
    )
    how = agg["metric"].map({m.name: m.aggregation for m in catalog.metrics.values()}).fillna("mean")
    agg["value"] = np.select(
        [how == "sum", how == "last", how == "max", how == "min"],
        [agg["sum"], agg["last"], agg["max"], agg["min"]],
        default=agg["mean"],
    )
    return agg.rename(columns={"count": "n"})[DAILY_COLUMNS]
