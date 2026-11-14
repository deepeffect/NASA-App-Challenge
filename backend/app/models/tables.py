"""SQLModel tabloları.

Zaman damgaları timezone-aware UTC'dir (SQLModel UTCDateTime: SQLite'a UTC yazar, aware okur).
`measurement` tablosu ortak long formattır: (astronaut_id, timestamp, metric, value, unit, source).
"""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Column, Index, UniqueConstraint
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(UTC)


def as_utc(ts: Any) -> datetime:
    """naive (UTC kabul edilir) veya aware datetime/Timestamp → aware UTC datetime."""
    import pandas as pd

    t = pd.Timestamp(ts)
    t = t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")
    return t.to_pydatetime()


class Astronaut(SQLModel, table=True):
    id: str = Field(primary_key=True)
    name: str
    role: str | None = None


class IngestBatch(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    filename: str
    adapter: str
    received_at: datetime = Field(default_factory=utcnow)
    rows_total: int = 0
    rows_accepted: int = 0
    rows_duplicate: int = 0
    rows_rejected: int = 0
    warnings: list[str] = Field(default_factory=list, sa_column=Column(JSON))


class Measurement(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint("astronaut_id", "metric", "timestamp", "source", name="uq_measurement"),
        Index("ix_measurement_astro_metric_ts", "astronaut_id", "metric", "timestamp"),
    )

    id: int | None = Field(default=None, primary_key=True)
    astronaut_id: str = Field(foreign_key="astronaut.id")
    timestamp: datetime
    metric: str
    value: float
    unit: str
    source: str
    batch_id: int | None = Field(default=None, foreign_key="ingestbatch.id")


class Checkin(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    astronaut_id: str = Field(foreign_key="astronaut.id", index=True)
    timestamp: datetime = Field(index=True)
    mood: int
    stress: int
    sleep_quality: int
    note: str | None = None
    share_with_ground: bool = False
    emergency: bool = False


class AlertFeedback(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    event_id: str = Field(index=True)
    verdict: str
    comment: str | None = None
    created_at: datetime = Field(default_factory=utcnow)


class AlertShare(SQLModel, table=True):
    event_id: str = Field(primary_key=True)
    share_with_ground: bool = False
    updated_at: datetime = Field(default_factory=utcnow)


class LLMCache(SQLModel, table=True):
    key: str = Field(primary_key=True)
    kind: str = Field(index=True)
    payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utcnow)
