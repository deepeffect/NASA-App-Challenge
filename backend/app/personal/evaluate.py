"""Değerlendirme kuralları — prototipin JavaScript'inden birebir (saf fonksiyonlar, DB'siz).

Prototip karşılıkları (frontend/reference/personal-artifact.html):
  avg3        → avg3(arr, i)            son 3 günün ortalaması (başta pencere daralır)
  level_of    → levelOf(ind, v)         0 sağlıklı · 1 uyarı aralığında · 2 uyarı aralığının dışında
  reading     → reading(a, ind, i)      exposure o günün değeri, diğerleri 3 günlük ortalama
  shown_status→ shown(k)                max(health_status, ground ? 1 : 0)
  todo_items  → render() içindeki items tetikleyici = action == kod VE seviye >= trig
  to_fixed    → Number.prototype.toFixed (yarımda sıfırdan uzağa yuvarlar; Python'un format'ı çifte)
  js_num      → `${sayı}` (JS sayı → metin)

Bilinçli farklar (kullanıcı kararları; golden testte belgelenir):
  - Dünya'da ground her yerde (durum başlığı ve şerit dahil) sadece görünür ölçümlerden hesaplanır.
  - Tetikleyicisi olmayan self-care kodu "veri setinin önerisi" olarak işaretlenir (prototipte boş).
  - Dünya'da (paylaşılmamışsa) çözümü sadece gizli ölçümlere bağlı öneri öğesi de maskelenir.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from app.personal.catalog import Indicator, PersonalCatalog, Solution
from app.personal.dataset import AstronautSeries

# Paylaşım seviyeleri (prototip LEVELS). -1 = o gün tamamlanmış check-in yok.
SHARE_LEVELS: dict[str, int] = {"private": 0, "scores": 1, "full": 2}
NO_CHECKIN = -1


# ============================================================================ sayı biçimi
def to_fixed(v: float, digits: int) -> str:
    """JS `v.toFixed(digits)` ile aynı metin (ondalık nokta)."""
    if v == 0:
        v = 0.0  # JS: (-0).toFixed(1) === "0.0"
    q = Decimal(v).quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP)
    return format(q, "f")


def js_num(v: float | int) -> str:
    """JS'de `${v}` (şablon dizgisi) ile aynı metin: 1.0 → "1", 36.1 → "36.1"."""
    f = float(v)
    if f.is_integer():
        return str(int(f))
    return repr(f)


# ============================================================================ okumalar
def avg3(arr: Sequence[float], i: int) -> float:
    """Son 3 günün ortalaması; JS ile aynı sıra ve toplama (kayan nokta sonucu birebir)."""
    s = 0.0
    n = 0
    for k in range(max(0, i - 2), i + 1):
        s += arr[k]
        n += 1
    return s / n


def level_of(ind: Indicator, v: float) -> int:
    hi = float("inf") if ind.healthy.max is None else ind.healthy.max
    chi = float("inf") if ind.warning.max is None else ind.warning.max
    if ind.healthy.min <= v <= hi:
        return 0
    if ind.warning.min <= v <= chi:
        return 1
    return 2


@dataclass(frozen=True)
class Reading:
    ind: Indicator
    today: float
    used: float
    level: int
    hidden: bool = False

    @property
    def averaged(self) -> bool:
        return self.ind.domain != "exposure"


def reading(series: AstronautSeries, ind: Indicator, i: int, hidden: bool = False) -> Reading:
    arr = [d.values[ind.col] for d in series.days]
    today = arr[i]
    used = today if ind.domain == "exposure" else avg3(arr, i)
    return Reading(ind=ind, today=today, used=used, level=level_of(ind, used), hidden=hidden)


def is_hidden(ind: Indicator, earth: bool, shared: int) -> bool:
    """Prototip: `earth && PRIVATE.has(col) && shared < 1`."""
    return earth and ind.private and shared < SHARE_LEVELS["scores"]


def readings_for_day(
    cat: PersonalCatalog, series: AstronautSeries, i: int, earth: bool = False, shared: int = NO_CHECKIN
) -> list[Reading]:
    return [reading(series, ind, i, hidden=is_hidden(ind, earth, shared)) for ind in cat.indicators]


# ============================================================================ durum
def shown_status(health_status: int, ground: bool) -> int:
    return max(health_status, 1 if ground else 0)


def visible_ground(readings: Iterable[Reading]) -> bool:
    """Dünya'nın göreceği ground: görünür ölçümlerden en az biri 2. seviyede."""
    return any(r.level == 2 and not r.hidden for r in readings)


@dataclass
class TodoItem:
    solution: Solution
    triggers: list[Reading] = field(default_factory=list)  # bütün tetikleyiciler
    visible: list[Reading] = field(default_factory=list)  # gizli olmayanlar
    # Dünya + paylaşılmamış + çözüm sadece gizli ölçümlere bağlı (MOOD_CONNECT): tetikleyicisiz
    # "veri setinin önerisi" de maskelenir (D4; prototipte gösteriliyordu)
    private_suggestion: bool = False

    @property
    def code(self) -> str:
        return self.solution.code

    @property
    def masked(self) -> bool:
        """Tetikleyicisi var ama hepsi gizli → Dünya'da sadece sayısı görünür."""
        if not self.triggers:
            return self.private_suggestion
        return not self.visible

    @property
    def from_dataset(self) -> bool:
        """Hiç tetikleyicisi yok: kod veri setinin önerisi (prototipte "neden" satırı boş kalır)."""
        return not self.triggers


def private_only_solution(cat: PersonalCatalog, code: str) -> bool:
    """Çözüm sadece gizli ölçümlerle ilişkili mi (örn. MOOD_CONNECT → sadece ruh hali)."""
    inds = [i for i in cat.indicators if i.action == code]
    return bool(inds) and all(i.private for i in inds)


def todo_items(
    cat: PersonalCatalog, codes: Sequence[str], readings: Sequence[Reading], hide_private: bool = False
) -> list[TodoItem]:
    items = []
    for code in codes:
        sol = cat.solution(code)
        if sol is None:
            continue
        trig = [r for r in readings if r.ind.action == code and r.level >= r.ind.trig]
        items.append(
            TodoItem(
                solution=sol,
                triggers=trig,
                visible=[r for r in trig if not r.hidden],
                private_suggestion=hide_private and not trig and private_only_solution(cat, code),
            )
        )
    return items


@dataclass
class DayEvaluation:
    """Bir astronotun bir günü, bir izleyici (astronot / Dünya) için."""

    index: int
    earth: bool
    shared: int
    readings: list[Reading]
    items: list[TodoItem]
    ground: bool
    status: int  # gösterilen durum
    health_status: int
    main_concern: str
    behavioral_hidden: bool  # Dünya: davranışsal alan skoru gizli (check-in en az `scores` paylaşılmadı)
    extra_masked: int = 0  # Dünya kaydından kurulurken: maskeli öğeler kodlarıyla gelmez, sadece sayıları

    @property
    def visible_items(self) -> list[TodoItem]:
        return [x for x in self.items if not x.masked]

    @property
    def masked_count(self) -> int:
        return len(self.items) - len(self.visible_items) + self.extra_masked


def evaluate_day(
    cat: PersonalCatalog, series: AstronautSeries, i: int, earth: bool = False, shared: int = NO_CHECKIN
) -> DayEvaluation:
    day = series.days[i]
    rd = readings_for_day(cat, series, i, earth, shared)
    ground = visible_ground(rd) if earth else day.needs_ground_support
    return DayEvaluation(
        index=i,
        earth=earth,
        shared=shared,
        readings=rd,
        items=todo_items(cat, day.self_care, rd, hide_private=earth and shared < SHARE_LEVELS["scores"]),
        ground=ground,
        status=shown_status(day.health_status, ground),
        health_status=day.health_status,
        main_concern=day.main_concern,
        behavioral_hidden=earth and shared < SHARE_LEVELS["scores"],
    )
