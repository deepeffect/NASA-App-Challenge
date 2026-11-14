"""API SÖZLEŞMESİ — tüm request/response modelleri (Pydantic v2).

Bu dosya arayüz ekibiyle olan sözleşmedir. Bir alanı değiştirdiğinde:
  1) `python -m app.cli export-openapi`   → docs/openapi.json
  2) docs/API.md'yi güncelle
  3) frontend: `npm run gen:api`          → src/api/types.ts
Analiz motoru olayları (HealthEvent) doğrudan bu modellerle üretir.
"""

import datetime as dt
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

# =============================================================================
# Ortak tipler
# =============================================================================
HealthSystem = Literal["cardiovascular", "musculoskeletal", "immune", "behavioral", "sleep", "radiation"]
HEALTH_SYSTEMS: tuple[str, ...] = (
    "cardiovascular",
    "musculoskeletal",
    "immune",
    "behavioral",
    "sleep",
    "radiation",
)
Severity = Literal["info", "warning", "critical"]
SEVERITY_RANK: dict[str, int] = {"info": 1, "warning": 2, "critical": 3}
EventSource = Literal["rule", "anomaly", "changepoint", "forecast"]
StatusColor = Literal["green", "yellow", "red", "unknown"]
EventStatus = Literal["active", "resolved"]
Verdict = Literal["false_alarm", "useful"]
Lang = Literal["tr", "en"]
GeneratedBy = Literal["llm", "mock", "template_fallback"]
Direction = Literal["up", "down", "both"]
Frequency = Literal["hourly", "daily", "weekly", "event"]
MetricState = Literal["normal", "watch", "alert", "no_data"]


class ErrorResponse(BaseModel):
    detail: str
    code: str | None = Field(None, description="Makine tarafından okunur hata kodu (yeni uçlar), örn. unknown_id")


class DateWindow(BaseModel):
    start: dt.date
    end: dt.date


class ValueRange(BaseModel):
    low: float | None = None
    high: float | None = None


class Thresholds(BaseModel):
    verified: bool = Field(description="false → placeholder, NASA-STD-3001 ile doğrulanmadı")
    source: str = Field("placeholder", description="Eşiğin kaynağı")
    warning: ValueRange | None = None
    critical: ValueRange | None = None


# =============================================================================
# /api/health
# =============================================================================
class DBHealth(BaseModel):
    ok: bool
    astronauts: int = 0
    measurements: int = 0
    latest_date: dt.date | None = None
    error: str | None = None


class LLMHealth(BaseModel):
    provider: Literal["mock", "openai"]
    base_url: str | None = None
    model: str
    reachable: bool = Field(description="LLM sunucusuna erişilebildi mi (GET {base_url}/models)")
    model_available: bool = Field(description="LLM_MODEL sunucuda yüklü mü")
    available_models: list[str] = []
    tool_mode: str
    thinking: bool
    latency_ms: float | None = None
    error: str | None = None
    checked_at: dt.datetime


class RAGHealth(BaseModel):
    backend: Literal["keyword", "embedding", "disabled"]
    ok: bool
    documents: int = 0
    chunks: int = 0
    error: str | None = None


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded", "error"] = Field(
        description="ok: her şey çalışıyor | degraded: LLM/RAG erişilemiyor (kural tabanlı uyarılar çalışır) | error: DB yok"
    )
    version: str
    time: dt.datetime
    db: DBHealth
    llm: LLMHealth
    rag: RAGHealth


# =============================================================================
# /api/metrics/catalog
# =============================================================================
class MetricInfo(BaseModel):
    name: str = Field(examples=["sleep_duration"])
    display_name: str
    display_name_en: str
    unit: str
    system: HealthSystem
    frequency: Frequency
    bad_direction: Direction = Field(description="Hangi yöne değişim kötüleşme sayılır")
    aggregation: str
    normal_range: ValueRange | None = None
    thresholds: Thresholds | None = None
    threshold_verified: bool
    rules: list[str]
    decimals: int


class SystemInfo(BaseModel):
    id: HealthSystem
    display_name: str
    display_name_en: str
    metrics: list[str]


class CatalogResponse(BaseModel):
    systems: list[SystemInfo]
    metrics: list[MetricInfo]


# =============================================================================
# Astronot / görev
# =============================================================================
class AstronautInfo(BaseModel):
    id: str = Field(examples=["AST-02"])
    name: str
    role: str | None = None


class MissionInfo(BaseModel):
    start_date: dt.date | None = Field(None, description="Görevin (verinin) ilk günü")
    latest_date: dt.date | None = Field(None, description="Verideki son gün")
    as_of: dt.date | None = Field(None, description="Bu cevabın hesaplandığı gün (zaman kaydırıcısı)")
    mission_day: int | None = Field(None, description="as_of gününün görev günü (1'den başlar)")
    total_days: int | None = None


# =============================================================================
# Olaylar (kural tabanlı + ML aynı şemayı kullanır)
# =============================================================================
class Contributor(BaseModel):
    metric: str
    value: float | None = None
    baseline: float | None = None
    z: float | None = None
    weight: float = Field(ge=0, le=1, description="Olaya katkı payı; bir olayın katkıları toplamı 1")
    threshold_verified: bool | None = Field(None, description="Metriğin eşiği doğrulandı mı (eşiği yoksa null)")


class ForecastPoint(BaseModel):
    date: dt.date
    value: float
    lower: float | None = None
    upper: float | None = None


class Forecast(BaseModel):
    metric: str
    method: str = Field(examples=["linear", "prophet"])
    horizon_days: int
    points: list[ForecastPoint]


class HealthEvent(BaseModel):
    event_id: str = Field(examples=["evt_3f9a1c2b7d10"], description="Deterministik: astronot+kaynak+dedektör+metrik+başlangıç hash'i")
    astronaut_id: str
    detected_at: dt.datetime
    source: EventSource
    system: HealthSystem
    severity: Severity
    score: float = Field(ge=0, le=1, description="Güven/şiddet 0-1. UI: <0.5 düşük, 0.5-0.75 orta, >0.75 yüksek")
    title: str
    window: DateWindow
    contributors: list[Contributor]
    changepoint_date: dt.date | None = None
    forecast: Forecast | None = None
    share_with_ground: bool = False
    # --- Şemaya eklenen alanlar ---
    status: EventStatus = Field("active", description="active: as_of itibarıyla sürüyor | resolved: bitti")
    detector: str = Field(examples=["rule.threshold", "rule.baseline_deviation", "ml.isolation_forest"])
    description: str | None = Field(None, description="Kural tarafından üretilen, sayıları içeren kısa açıklama")
    feedback: Verdict | None = Field(None, description="Son kullanıcı geri bildirimi")


class EventCounts(BaseModel):
    critical: int = 0
    warning: int = 0
    info: int = 0


# =============================================================================
# /api/crew
# =============================================================================
class CrewMember(AstronautInfo):
    status: StatusColor
    score: float | None = Field(None, description="Genel skor 0-100 (en zayıf sistemin skoru)")
    active_events: EventCounts
    attention_systems: list[HealthSystem] = Field(description="green olmayan sistemler (kötüden iyiye)")
    last_measurement_at: dt.datetime | None = None


class CrewResponse(BaseModel):
    mission: MissionInfo
    astronauts: list[CrewMember]


# =============================================================================
# /api/astronauts/{id}/summary
# =============================================================================
class ScorePenalty(BaseModel):
    event_id: str
    title: str
    metric: str | None = None
    severity: Severity
    penalty: float


class SystemScore(BaseModel):
    system: HealthSystem
    display_name: str
    score: float | None = Field(None, description="0-100; sistemde veri yoksa null")
    status: StatusColor
    metrics: list[str]
    penalties: list[ScorePenalty] = Field(description="Skoru düşüren aktif olaylar (açıklanabilirlik)")


class OverallStatus(BaseModel):
    status: StatusColor
    score: float | None = None
    worst_system: HealthSystem | None = None


class MetricSnapshot(BaseModel):
    metric: str
    display_name: str
    unit: str
    system: HealthSystem
    date: dt.date | None = None
    value: float | None = None
    baseline_mean: float | None = None
    baseline_std: float | None = None
    z: float | None = Field(None, description="Günlük değerin baseline z-skoru")
    z7: float | None = Field(None, description="7 günlük ortalamanın baseline z-skoru")
    slope7: float | None = Field(None, description="Son 7 günün lineer eğimi (birim/gün)")
    threshold_verified: bool
    state: MetricState


class AstronautSummary(BaseModel):
    astronaut: AstronautInfo
    mission: MissionInfo
    overall: OverallStatus
    systems: list[SystemScore]
    latest: list[MetricSnapshot]
    active_events: list[HealthEvent]
    last_measurement_at: dt.datetime | None = None


# =============================================================================
# /api/astronauts/{id}/metrics
# =============================================================================
class Baseline(BaseModel):
    mean: float
    std: float
    n_days: int
    start: dt.date
    end: dt.date


class DailyPoint(BaseModel):
    date: dt.date
    value: float
    min: float
    max: float
    n: int = Field(description="O gün kaç ham ölçüm var")
    roll7: float | None = None
    z7: float | None = None


class RawPoint(BaseModel):
    timestamp: dt.datetime
    value: float
    source: str | None = None


class MetricSeriesResponse(BaseModel):
    astronaut_id: str
    metric: MetricInfo = Field(description="Birim, normal aralık, eşikler ve threshold_verified dahil")
    as_of: dt.date | None
    resolution: Literal["daily", "raw"]
    baseline: Baseline | None = Field(None, description="Kişisel normal bant: mean ± std")
    daily: list[DailyPoint]
    raw: list[RawPoint] = Field([], description="Sadece resolution=raw iken dolu")
    events: list[HealthEvent] = Field(
        [], description="Bu metriği içeren olaylar (window gölgesi, changepoint_date, forecast çizimi için)"
    )


# =============================================================================
# Check-in
# =============================================================================
class EmergencyProtocol(BaseModel):
    id: str
    title: str
    steps: list[str]
    contacts: list[str]
    verified: bool = Field(description="false → protokol metni placeholder")


class EmergencyNotice(BaseModel):
    triggered: bool = True
    matched_symptoms: list[str] = Field(description="Belirti kimlikleri, örn. chest_pain")
    matched_labels: list[str] = Field(description="Okunur belirti adları")
    matched_terms: list[str]
    protocol: EmergencyProtocol
    message: str


class CheckinRequest(BaseModel):
    astronaut_id: str
    mood: int = Field(ge=1, le=5, description="1 çok kötü … 5 çok iyi")
    stress: int = Field(ge=1, le=5, description="1 çok düşük … 5 çok yüksek")
    sleep_quality: int = Field(ge=1, le=5, description="1 çok kötü … 5 çok iyi")
    note: str | None = Field(None, max_length=2000)
    share_with_ground: bool = False
    timestamp: dt.datetime | None = Field(None, description="Boşsa sunucu zamanı (UTC)")
    lang: Lang = "tr"


class CheckinRecord(BaseModel):
    id: int
    astronaut_id: str
    timestamp: dt.datetime
    mood: int
    stress: int
    sleep_quality: int
    note: str | None = None
    share_with_ground: bool
    emergency: bool = Field(description="Not acil belirti içeriyor muydu")


class CheckinResponse(BaseModel):
    checkin: CheckinRecord
    emergency: EmergencyNotice | None = None


class CheckinListResponse(BaseModel):
    astronaut_id: str
    checkins: list[CheckinRecord]


# =============================================================================
# /api/alerts
# =============================================================================
class AlertListResponse(BaseModel):
    as_of: dt.date | None
    count: int
    events: list[HealthEvent]


class ExplainRequest(BaseModel):
    lang: Lang = "tr"
    as_of: dt.date | None = None
    refresh: bool = Field(False, description="true → cache'i atla, yeniden üret")


class AlertExplanation(BaseModel):
    """LLM'in üretmesi gereken yapılandırılmış çıktı (json_schema)."""

    summary: str
    likely_factors: list[str]
    recommended_actions: list[str]
    escalate_to_ground: bool
    sources: list[str] = Field(description="Kullanılan veri/belge referansları, örn. 'metric:sleep_duration', 'doc:file.md#Bölüm'")
    uncertainty: str | None = Field(None, description="Belirsizlik/veri eksikliği notu")


class DocRef(BaseModel):
    file: str
    section: str | None = None
    page: int | None = None
    snippet: str
    score: float


class ExplainResponse(BaseModel):
    event_id: str
    event: HealthEvent
    explanation: AlertExplanation
    generated_by: GeneratedBy
    model: str | None = None
    cached: bool
    ungrounded_numbers: list[str] = Field([], description="Çıktıda olup bağlam verisinde bulunmayan sayılar (uyarı amaçlı)")
    doc_refs: list[DocRef] = []
    created_at: dt.datetime


class FeedbackRequest(BaseModel):
    verdict: Verdict
    comment: str | None = Field(None, max_length=1000)


class FeedbackResponse(BaseModel):
    feedback_id: int
    event_id: str
    verdict: Verdict
    comment: str | None = None
    created_at: dt.datetime


class ShareRequest(BaseModel):
    share_with_ground: bool


class ShareResponse(BaseModel):
    event_id: str
    share_with_ground: bool
    updated_at: dt.datetime


# =============================================================================
# /api/astronauts/{id}/briefing
# =============================================================================
class DailyBriefing(BaseModel):
    """LLM'in üretmesi gereken yapılandırılmış çıktı (json_schema)."""

    summary: str
    highlights: list[str] = Field(description="Olumlu/normal giden noktalar")
    concerns: list[str] = Field(description="warning/critical olaylar")
    recommended_actions: list[str]
    info_notes: list[str] = Field(description="info seviyesindeki olaylar (sadece brifingde gösterilir)")
    escalate_to_ground: bool
    sources: list[str]
    uncertainty: str | None = None


class BriefingResponse(BaseModel):
    astronaut_id: str
    as_of: dt.date | None
    lang: Lang
    briefing: DailyBriefing
    generated_by: GeneratedBy
    model: str | None = None
    cached: bool
    ungrounded_numbers: list[str] = []
    info_events: list[HealthEvent] = []
    created_at: dt.datetime


# =============================================================================
# /api/chat (SSE)
# =============================================================================
class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=8000)


class ChatRequest(BaseModel):
    astronaut_id: str
    messages: list[ChatMessage] = Field(min_length=1, max_length=50)
    as_of: dt.date | None = None
    lang: Lang | None = Field(None, description="Boşsa kullanıcının dilinden tahmin edilir")

    @model_validator(mode="after")
    def _last_is_user(self) -> "ChatRequest":
        if self.messages[-1].role != "user":
            raise ValueError("son mesaj 'user' rolünde olmalı")
        return self


ChatEventName = Literal["meta", "token", "thinking", "tool_call", "tool_result", "emergency", "done", "error"]


class SSEMeta(BaseModel):
    request_id: str
    provider: str
    model: str
    tool_mode: str
    astronaut_id: str
    as_of: dt.date | None = None


class SSEToken(BaseModel):
    text: str


class SSEThinking(BaseModel):
    text: str


class SSEToolCall(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any]


class SSEToolResult(BaseModel):
    id: str
    name: str
    ok: bool
    duration_ms: float
    preview: str = Field(description="Sonucun kısaltılmış JSON'u (≤500 karakter)")
    error: str | None = None


class SSEDone(BaseModel):
    message: str = Field(description="Asistanın tam cevabı")
    finish_reason: Literal["stop", "max_steps", "error", "llm_unavailable"]
    steps: int
    tool_calls: int
    ungrounded_numbers: list[str] = []
    doc_refs: list[DocRef] = []
    degraded: bool = Field(False, description="true → LLM yok, kural tabanlı yedek cevap")


class SSEError(BaseModel):
    code: str
    message: str


SSE_MODELS: dict[str, type[BaseModel]] = {
    "meta": SSEMeta,
    "token": SSEToken,
    "thinking": SSEThinking,
    "tool_call": SSEToolCall,
    "tool_result": SSEToolResult,
    "emergency": EmergencyNotice,
    "done": SSEDone,
    "error": SSEError,
}


# =============================================================================
# /api/ingest
# =============================================================================
class IngestRowError(BaseModel):
    row: int
    reason: str
    value: str | None = None


class IngestReport(BaseModel):
    batch_id: int | None = None
    filename: str
    adapter: str
    rows_total: int
    rows_accepted: int
    rows_duplicate: int
    rows_rejected: int
    unknown_metrics: list[str] = []
    astronauts: list[str] = []
    date_range: DateWindow | None = None
    warnings: list[str] = []
    errors_sample: list[IngestRowError] = Field([], description="İlk 20 reddedilen satır")


# =============================================================================
# /api/ground-report
# =============================================================================
class GroundReportMember(BaseModel):
    astronaut: AstronautInfo
    status: StatusColor
    score: float | None = None
    shared_checkins: list[CheckinRecord]
    shared_events: list[HealthEvent]


class GroundReport(BaseModel):
    generated_at: dt.datetime
    as_of: dt.date | None
    period: DateWindow | None
    crew: list[GroundReportMember]
    note: str


# #############################################################################
# YENİ MİMARİ: GEMİ / DÜNYA İSTASYONLARI (feat/foundation)
# Kurallar için tek doğru kaynak: frontend/reference/personal-artifact.html
# #############################################################################
StationRole = Literal["ship", "earth"]


# =============================================================================
# /api/station
# =============================================================================
class StationInfo(BaseModel):
    role: StationRole = Field(description="ship: gemi bilgisayarı | earth: Dünya üssü (salt okunur)")
    version: str
    home_path: str = Field(description="Bu istasyonun ana ekranı: ship → /me, earth → /monitor")
    read_only: bool = Field(description="true → bu istasyonda yazma (POST/PUT/DELETE) 403 döner (Dünya)")
    data_source: Literal["astronaut_health", "synthetic"]
    legacy_enabled: bool = Field(description="true → eski ekranlar (/legacy) ve eski API açık (gemi + synthetic)")


# =============================================================================
# Kişisel sağlık görünümü (gemi /api/me/*, Dünya /api/monitor/*)
# =============================================================================
Viewer = Literal["astronaut", "earth"]
ShareLevel = Literal["private", "scores", "full"]


class ReadingView(BaseModel):
    col: str
    domain: str
    label: str
    unit: str
    dec: int
    value: float | None = Field(description="Değerlendirilen değer (3 günlük ortalama; exposure → o günün değeri). Gizliyse null")
    today: float | None = Field(description="O günün ham değeri. Gizliyse null")
    value_text: str = Field(description="Biçimli değer veya 'Paylaşılmadı'")
    healthy_text: str = Field(description="Sağlıklı aralık metni, örn. '7–9' / '7 to 9'")
    level: int | None = Field(description="0 sağlıklı · 1 uyarı aralığında · 2 uyarı aralığının dışında. Gizliyse null")
    flag_text: str = Field(description="'' | 'Aralık dışında' | 'Çok dışında'")
    averaged: bool = Field(description="true → son 3 günün ortalaması, false → o günün değeri")
    private: bool = Field(description="Ruh hali / stres: Dünya sadece paylaşılırsa görür")
    hidden: bool = Field(description="Bu izleyiciden gizli (Dünya, paylaşılmadı)")


class AreaScoreView(BaseModel):
    area: str
    label: str
    score: float | None = Field(description="0–100. Dünya'da davranışsal alan paylaşılmadıysa null")
    score_text: str
    hidden: bool
    main_concern: bool


class TodoItemView(BaseModel):
    code: str
    title: str
    why: str = Field(description="Tetikleyen ölçümler; tetikleyici yoksa 'Veri setinin önerisi'")
    source: Literal["readings", "dataset"] = Field(description="dataset → veri seti önerdi, eşleşen ölçüm yok")
    triggers: list[str] = Field(description="Görünür tetikleyici ölçüm kolonları")
    steps: list[str]
    when: str
    contact_ground_if: str
    basis: str
    done: bool = Field(False, description="Astronot 'yaptım' olarak işaretledi")


class StripDay(BaseModel):
    day: int = Field(description="1'den başlar (30 günün kaçıncısı)")
    mission_day: int
    status: int = Field(description="Gösterilen durum 0/1/2 (bu izleyiciye göre)")
    status_label: str
    score: float = Field(description="Kümülatif sağlık skoru")
    score_text: str
    label: str = Field(description="Erişilebilir etiket, örn. 'Gün 3: Dikkat, skor 74'")


class DayView(BaseModel):
    astronaut_id: str
    viewer: Viewer
    day: int = Field(description="1'den başlar")
    n_days: int
    mission_day: int
    is_today: bool = Field(description="Son kayıt (check-in sadece bugün yapılabilir)")
    day_label: str = Field(description="'30 günün 30. günü · görev günü 155'")
    status: int = Field(description="Gösterilen durum = max(health_status, ground ? 1 : 0)")
    status_label: str = Field(description="Normal / Dikkat / Rahatsız")
    health_status: int = Field(description="Veri setindeki durum (ground hariç)")
    ground: bool = Field(description="Yer desteği gerekli. Dünya'da sadece görünür ölçümlerden hesaplanır")
    subtitle: str
    score: float = Field(description="Kümülatif sağlık skoru (her zaman görünür)")
    score_text: str
    daily_score: float
    main_concern: str = Field(description="none | immune | bone_muscle | cardiovascular | behavioral")
    main_concern_label: str | None
    areas: list[AreaScoreView]
    readings: list[ReadingView] = Field(description="Katalog sırasında; grup sırası `domains`")
    todo_title: str
    todo: list[TodoItemView] = Field(description="Görünür to-do öğeleri, veri setindeki sırayla")
    todo_masked_count: int = Field(description="Dünya: tetikleyicisi sadece gizli ölçümler olan öğe sayısı")
    todo_masked_text: str | None
    calm_text: str | None = Field(description="Yapılacak bir şey yoksa")
    ground_title: str | None
    ground_text: str | None
    readings_note: str
    threshold_note: str = Field(description="Tek dipnot: aralıklar simüle veri setinden, doğrulanmadı")
    share: ShareLevel | None = Field(None, description="Bu günün check-in paylaşım seviyesi (tamamlandıysa)")


# =============================================================================
# /api/auth
# =============================================================================
PrincipalKind = Literal["astronaut", "earth"]


class LoginRequest(BaseModel):
    id: str = Field("", max_length=64, description="Astronot kimliği (A000 …) veya EARTH; büyük/küçük harf duyarsız")
    password: str = Field("", max_length=256)


class LoginResponse(BaseModel):
    token: str = Field(description="Authorization: Bearer <token>")
    kind: PrincipalKind
    subject: str = Field(description="A003 | EARTH")
    astronaut_id: str | None = Field(None, description="Astronot girişinde kendi kimliği; token sadece bu astronota erişir")
    station: StationRole
    home_path: str
    expires_at: dt.datetime


class AccountRange(BaseModel):
    first_id: str
    last_id: str
    count: int


class AuthHint(BaseModel):
    station: StationRole
    astronauts: AccountRange | None = Field(description="Bu istasyonda giriş yapabilen astronot hesapları (sadece gemi)")
    earth_id: str | None = Field(description="Dünya üssü hesabı (sadece Dünya istasyonu)")
    text: str = Field(description="Giriş kartında gösterilecek ipucu")


class PrincipalInfo(BaseModel):
    kind: PrincipalKind
    subject: str
    astronaut_id: str | None
    station: StationRole
    read_only: bool


# =============================================================================
# /api/me, /api/personal/{id} (gemi) ve /api/catalog
# =============================================================================
class CrewInfo(BaseModel):
    id: str
    age: int
    sex: str
    bmi: float
    mission: str
    mission_label: str
    profile: str = Field(description="Veri setindeki simülasyon deseni")
    profile_label: str
    first_mission_day: int
    last_mission_day: int
    n_days: int


class PersonalOverview(BaseModel):
    astronaut: CrewInfo
    today: int = Field(description="Bugünün gün numarası (= n_days; son kayıt)")
    n_days: int
    strip: list[StripDay]
    threshold_note: str


class CatalogRange(BaseModel):
    min: float
    max: float | None


class CatalogIndicator(BaseModel):
    col: str
    domain: str
    domain_label: str
    label: str
    unit: str
    dec: int
    healthy: CatalogRange
    warning: CatalogRange
    healthy_text: str
    action: str
    trig: int
    private: bool
    averaged: bool


class CatalogSolution(BaseModel):
    code: str
    domain: str
    title: str
    when: str
    steps: list[str]
    contact_ground_if: str
    basis: str


class CatalogDomain(BaseModel):
    id: str
    label: str


class PersonalCatalogResponse(BaseModel):
    statuses: list[str] = Field(description="Durum etiketleri, indeks = seviye")
    domains: list[CatalogDomain]
    areas: list[str]
    indicators: list[CatalogIndicator]
    solutions: list[CatalogSolution]
    threshold_source: str
    verified: bool
    threshold_note: str


# =============================================================================
# /api/checkin (gemi) — prototipin assistantTurn sözleşmesi
# =============================================================================
CheckinMode = Literal["scripted", "llm", "auto"]


class CheckinMessage(BaseModel):
    who: Literal["bot", "me"]
    text: str


class CheckinNote(BaseModel):
    topic: str = Field(description="Konu adı (yazıldığı dilde)")
    topic_key: str = Field(description="sleep | mood | stress | symptoms | other")
    text: str = Field(description="Astronotun cevabı (aynen)")
    flag: bool
    urgent: bool = Field(description="Acil belirti → gemideki CMO bilgilendirildi (Dünya'ya gitmez)")


class CheckinNext(BaseModel):
    text: str
    options: list[str]


class CmoNotice(BaseModel):
    title: str
    text: str


class CheckinState(BaseModel):
    astronaut_id: str
    day: int
    mission_day: int
    is_today: bool
    editable: bool = Field(description="true → bugün ve bitmemiş (cevap verilebilir)")
    started: bool
    step: int
    options: list[str] = Field(description="Hızlı cevaplar")
    messages: list[CheckinMessage]
    notes: list[CheckinNote]
    done: bool
    share: ShareLevel | None = Field(description="Tamamlandıysa paylaşım seviyesi (varsayılan private)")
    can_reset: bool = Field(description="'Baştan başla': sadece paylaşım private iken")
    cmo_notified: bool
    cmo_notice: CmoNotice | None = Field(description="'Gemideki sağlık sorumlusu bilgilendirildi'")
    completed_at: dt.datetime | None = None
    share_options: list["ShareOption"] = Field([], description="Sadece tamamlanmış check-in'de")
    share_note: str | None = Field(None, description="Seçili seviyenin açıklaması + 'paylaşım geri alınamaz'")
    share_cmo_note: str | None = Field(None, description="Acil durumda CMO'ya bildirim (kayıt gizli olsa da), Dünya'ya gitmez")


class CheckinTurnRequest(BaseModel):
    answer: str = Field(max_length=2000)


class CheckinTurnResponse(BaseModel):
    """Prototipin assistantTurn çıktısı aynen + güncel durum (`checkin`, ek alan)."""

    reply: str
    note: CheckinNote | None
    next: CheckinNext | None
    done: bool
    checkin: CheckinState


# =============================================================================
# Paylaşım ve Dünya'ya giden (gizlilik filtresinden geçmiş) kayıtlar
# =============================================================================
class ShareOption(BaseModel):
    level: ShareLevel
    label: str
    description: str
    selected: bool
    enabled: bool = Field(description="false → mevcut seviyeden düşük (paylaşım geri alınamaz)")


class CheckinShareRequest(BaseModel):
    level: ShareLevel


class EarthReading(BaseModel):
    today: float
    used: float = Field(description="Değerlendirilen değer (3 günlük ortalama veya o günün değeri)")
    level: int


class EarthTodo(BaseModel):
    code: str
    triggers: list[str] = Field(description="Görünür tetikleyici kolonlar; boş → veri setinin önerisi")
    done: bool = False


class EarthCheckinNote(BaseModel):
    topic_key: str
    flag: bool
    text: str | None = Field(None, description="Sadece `full` paylaşımda")


class EarthCheckin(BaseModel):
    share: ShareLevel
    notes: list[EarthCheckinNote] = Field(description="private → boş; scores → konu + flag; full → + metin")


class EarthAstronaut(BaseModel):
    id: str
    age: int
    sex: str
    bmi: float
    mission: str
    profile: str
    first_mission_day: int
    last_mission_day: int
    n_days: int


class EarthDay(BaseModel):
    """Bir günün Dünya'ya giden hali. Gizlilik filtresi GEMİDE uygulanır; bu kayıtta gizli ölçümler,
    maskeli to-do kodları, paylaşılmamış davranışsal skor, check-in mesajları ve CMO bilgisi YOKTUR."""

    astronaut_id: str
    day_index: int
    mission_day: int
    n_days: int
    health_status: int
    ground: bool = Field(description="Sadece görünür ölçümlerden")
    status: int = Field(description="max(health_status, ground ? 1 : 0)")
    cumulative_score: float
    daily_score: float
    main_concern: str
    behavioral_hidden: bool
    area_scores: dict[str, float]
    readings: dict[str, EarthReading]
    todo: list[EarthTodo]
    todo_masked_count: int
    checkin: EarthCheckin | None


class EarthCheckinNoteView(BaseModel):
    topic: str
    text: str | None
    flag: bool
    flag_text: str = Field(description="scores: 'İşaretlendi' / 'İşaret yok'; full: ''")


class EarthCheckinView(BaseModel):
    share: ShareLevel | None
    text: str = Field(description="'Tamamlanmış check-in yok' / 'gizli tutuldu' / 'Astronotun paylaştığı: …'")
    notes: list[EarthCheckinNoteView]


CheckinState.model_rebuild()


# =============================================================================
# /api/actions (gemi): to-do öğesini işaretle
# =============================================================================
class ActionDoneRequest(BaseModel):
    code: str = Field(description="Bugünün to-do öğesinin self-care kodu")
    done: bool = True


class ActionDoneResponse(BaseModel):
    code: str
    done: bool
    day: DayView


# =============================================================================
# /api/downlink (gemi → Dünya; EARTH_LINK_TOKEN ile korunur)
# =============================================================================
DownlinkEventType = Literal["checkin.completed", "checkin.shared", "action.done", "day.snapshot", "link.heartbeat"]


class DownlinkPayload(BaseModel):
    """Olay yükü: her olay ilgili günün filtrelenmiş güncel halini (`day`) taşır."""

    day: EarthDay
    share: ShareLevel | None = Field(None, description="checkin.*: paylaşım seviyesi")
    code: str | None = Field(None, description="action.done: kod (Dünya'da maskeliyse null)")
    masked: bool = Field(False, description="action.done: öğe Dünya'da maskeli")
    done: bool | None = Field(None, description="action.done: işaretlendi / kaldırıldı")


class DownlinkEvent(BaseModel):
    seq: int = Field(description="Gemideki sıra numarası (artan, boşluksuz yayın)")
    type: DownlinkEventType
    epoch: str = Field(description="Gemi DB dönemi; değişirse Dünya baştan senkronize olur")
    astronaut_id: str | None = None
    day_index: int | None = None
    ship_time: dt.datetime
    publish_time: dt.datetime = Field(description="ship_time + DOWNLINK_DELAY_SECONDS")
    earth_received_time: dt.datetime | None = Field(None, description="Dünya'nın aldığı an (Dünya doldurur)")
    simulated_light_delay_minutes: float = Field(description="Gerçek ışık gecikmesi etiketi (simülasyon, bekletmez)")
    payload: DownlinkPayload


class DownlinkHeartbeat(BaseModel):
    epoch: str
    ship_time: dt.datetime
    last_seq: int = Field(description="Yayınlanmış son seq")
    pending: int = Field(description="Gecikme nedeniyle henüz yayınlanmamış olay sayısı")
    delay_seconds: float
    simulated_light_delay_minutes: float


class DownlinkSnapshot(BaseModel):
    epoch: str
    seq: int = Field(description="Bu snapshot'ın içerdiği son seq; stream since=seq ile devam eder")
    generated_at: dt.datetime
    simulated_light_delay_minutes: float
    astronauts: list[EarthAstronaut]
    days: list[EarthDay]


# =============================================================================
# Dünya üssü: /api/link/status, /api/monitor/*, /api/stream/monitor
# =============================================================================
class LinkStatus(BaseModel):
    configured: bool = Field(description="SHIP_URL ve EARTH_LINK_TOKEN ayarlı mı")
    connected: bool
    ship_url: str | None
    epoch: str | None
    last_contact: dt.datetime | None = Field(description="Gemiden son olay veya heartbeat")
    last_event_at: dt.datetime | None
    last_seq: int = Field(description="Dünya'nın işlediği son seq")
    ship_last_seq: int | None = Field(description="Gemide yayınlanmış son seq (heartbeat)")
    pending_on_ship: int | None = Field(description="Kuyruktaki olay: gemide gecikme nedeniyle bekleyen")
    behind: int | None = Field(description="Yayınlanmış ama Dünya'ya henüz ulaşmamış olay sayısı")
    events_received: int
    snapshot_at: dt.datetime | None
    last_error: str | None
    delay_seconds: float | None
    simulated_light_delay_minutes: float | None


class MonitorCrewMember(BaseModel):
    astronaut: CrewInfo
    today: int
    mission_day: int
    status: int
    status_label: str
    subtitle: str
    score: float
    score_text: str
    ground: bool
    share: ShareLevel | None = Field(description="Bugünün check-in'i (tamamlandıysa)")
    checkin_text: str


class MonitorCrewResponse(BaseModel):
    link: LinkStatus
    astronauts: list[MonitorCrewMember]


class MonitorDay(BaseModel):
    view: DayView
    checkin: EarthCheckinView
    updated_seq: int
    received_at: dt.datetime | None


class MonitorStreamEvent(BaseModel):
    kind: Literal["event", "link"]
    type: str | None = None
    seq: int | None = None
    astronaut_id: str | None = None
    day_index: int | None = None
    ship_time: dt.datetime | None = None
    earth_received_time: dt.datetime | None = None
    link: LinkStatus | None = None
