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


# =============================================================================
# YENİ MİMARİ (DATA_SOURCE=astronaut_health) — veri seti tabloları
# =============================================================================
class StationKV(SQLModel, table=True):
    """İstasyonun küçük durum değerleri: veri seti parmak izi, imza anahtarı, gemi dönemi vb."""

    key: str = Field(primary_key=True)
    value: Any = Field(default=None, sa_column=Column(JSON))
    updated_at: datetime = Field(default_factory=utcnow)


class CrewProfile(SQLModel, table=True):
    """Veri setindeki astronot (A000 …). `first/last_mission_day`: verideki 30 günlük pencere."""

    id: str = Field(primary_key=True)
    age: int
    sex: str
    bmi: float
    mission: str
    profile: str = Field(description="Simülasyon deseni (healthy, acute_episode …)")
    first_mission_day: int
    last_mission_day: int
    n_days: int


class DayRecord(SQLModel, table=True):
    """Bir astronotun bir günü. `day_index` 0'dan başlar; son indeks = "bugün"."""

    astronaut_id: str = Field(foreign_key="crewprofile.id", primary_key=True)
    day_index: int = Field(primary_key=True)
    mission_day: int
    values: dict[str, float] = Field(default_factory=dict, sa_column=Column(JSON))
    area_scores: dict[str, float] = Field(default_factory=dict, sa_column=Column(JSON))
    daily_score: float
    cumulative_score: float
    health_status: int
    main_concern: str
    self_care: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    needs_ground_support: bool


class CheckinSession(SQLModel, table=True):
    """Bir günün check-in'i (prototipteki checkins[id:gün]). Sadece bugün için yazılır."""

    astronaut_id: str = Field(foreign_key="crewprofile.id", primary_key=True)
    day_index: int = Field(primary_key=True)
    mission_day: int
    lang: str = "tr"
    step: int = 0
    options: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    messages: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    notes: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    modes: list[str] = Field(default_factory=list, sa_column=Column(JSON))  # tur başına scripted | llm
    done: bool = False
    cmo: bool = False
    share: str | None = Field(default=None, description="private | scores | full; sadece artar")
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    completed_at: datetime | None = None
    shared_at: datetime | None = None


class CmoNotification(SQLModel, table=True):
    """Gemideki sağlık sorumlusuna (CMO) bildirim. SADECE gemide; Dünya'ya asla gönderilmez."""

    id: int | None = Field(default=None, primary_key=True)
    astronaut_id: str = Field(index=True)
    day_index: int
    mission_day: int
    source: str = Field(description="checkin | chat")
    topic: str | None = None
    text: str
    created_at: datetime = Field(default_factory=utcnow)
