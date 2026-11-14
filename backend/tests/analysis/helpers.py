"""Analiz testleri için el yapımı seri üreticileri."""

from collections.abc import Sequence
from datetime import date, datetime, time, timedelta

import pandas as pd

from app.analysis.catalog import load_catalog
from app.analysis.engine import AnalysisEngine
from app.models.schemas import AstronautInfo

START = date(2026, 1, 1)


def alt_baseline(mean: float, amp: float, n: int = 14) -> list[float]:
    """Deterministik 'gürültülü' baseline: mean ± amp dönüşümlü."""
    return [mean + (amp if i % 2 else -amp) for i in range(n)]


def long_df(aid: str, metric: str, values: Sequence[float | None | Sequence[float]], start: date = START) -> pd.DataFrame:
    """Günlük değer listesi → long DataFrame. Eleman liste ise o gün için saatlik çoklu ölçüm."""
    unit = load_catalog().metrics[metric].unit
    rows = []
    for i, v in enumerate(values):
        if v is None:
            continue
        day = start + timedelta(days=i)
        vals = v if isinstance(v, (list, tuple)) else [v]
        for h, x in enumerate(vals):
            rows.append((aid, datetime.combine(day, time(8 + h % 12)), metric, float(x), unit, "test"))
    return pd.DataFrame(rows, columns=["astronaut_id", "timestamp", "metric", "value", "unit", "source"])


def run(frames: list[pd.DataFrame], detectors: list[str], as_of: date | None = None, astronauts=("AST-T",)):
    eng = AnalysisEngine(detectors=detectors)
    df = pd.concat(frames, ignore_index=True)
    return eng.run(df, [AstronautInfo(id=a, name=a) for a in astronauts], as_of)


def day(i: int) -> date:
    return START + timedelta(days=i)
