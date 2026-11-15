from datetime import date

import pytest

from app.analysis.detectors import DETECTOR_REGISTRY, build_detectors, register_detector
from app.analysis.episodes import event_status, find_episodes, make_event_id
from app.models.schemas import Contributor, DateWindow, HealthEvent

from .helpers import alt_baseline, day, long_df, run

RULES = ["threshold", "baseline_deviation", "trend", "system_pattern"]


# --------------------------------------------------------------------------- epizotlar
def test_find_episodes_merges_small_gaps():
    levels = [0, 1, 1, 0, 0, 2, 0, 0, 0, 1]
    assert find_episodes(levels, merge_gap=2) == [(1, 5), (9, 9)]
    assert find_episodes(levels, merge_gap=0) == [(1, 2), (5, 5), (9, 9)]
    assert find_episodes([0, 0], 2) == []


def test_event_id_deterministic():
    a = make_event_id("AST-02", "rule", "rule.threshold", "spo2", date(2026, 1, 5))
    assert a == make_event_id("AST-02", "rule", "rule.threshold", "spo2", date(2026, 1, 5))
    assert a != make_event_id("AST-02", "rule", "rule.threshold", "spo2", date(2026, 1, 6))
    assert a.startswith("evt_") and len(a) == 16


def test_event_status_hysteresis():
    assert event_status(date(2026, 1, 10), date(2026, 1, 12), 2) == "active"
    assert event_status(date(2026, 1, 10), date(2026, 1, 13), 2) == "resolved"


# --------------------------------------------------------------------------- eşik
def test_threshold_uses_daily_worst_value_for_mean_metrics():
    values = [[97.5, 97.8]] * 20
    values[16] = [97.5, 89.0, 98.0]  # tek saatlik ölçüm kritik altında, günlük ortalama ~94.8
    res = run([long_df("AST-T", "spo2", values)], ["threshold"])
    (e,) = res.events
    assert (e.severity, e.detector, e.source, e.system) == ("critical", "rule.threshold", "rule", "cardiovascular")
    assert e.window == DateWindow(start=day(16), end=day(16))
    assert e.contributors[0].value == pytest.approx(89.0)
    assert e.contributors[0].threshold_verified is False
    assert e.score == pytest.approx(0.7)  # doğrulanmamış eşik → orta güven
    assert "alt kritik" in e.title
    assert e.status == "resolved"


def test_threshold_on_sum_metric_uses_daily_total():
    values = [[60, 70]] * 15 + [[20, 20]]  # günlük toplam 40 dk < 45 uyarı eşiği
    res = run([long_df("AST-T", "exercise_minutes", values)], ["threshold"])
    (e,) = res.events
    assert e.severity == "warning" and e.contributors[0].value == pytest.approx(40)
    assert e.status == "active"


def test_no_threshold_rule_for_metrics_without_it():
    res = run([long_df("AST-T", "body_mass", [70.0] * 10 + [10.0])], ["threshold"])
    assert res.events == []


# --------------------------------------------------------------------------- sapma
def test_deviation_detects_bad_direction_only():
    drop = alt_baseline(7.0, 0.3) + [5.5] * 10
    res = run([long_df("AST-T", "sleep_duration", drop)], ["baseline_deviation"])
    (e,) = res.events
    assert e.severity == "critical" and e.status == "active"
    assert e.window.start > day(13), "baseline penceresi içinde değerlendirme yapılmaz"
    assert e.contributors[0].z < -3.5
    assert "altında" in e.title

    better = alt_baseline(7.0, 0.3) + [8.8] * 10  # daha çok uyku: iyileşme → olay yok
    assert run([long_df("AST-T", "sleep_duration", better)], ["baseline_deviation"]).events == []


def test_deviation_both_directions():
    up = alt_baseline(36.8, 0.1) + [37.6] * 8
    (e,) = run([long_df("AST-T", "body_temp", up)], ["baseline_deviation"]).events
    assert "üstünde" in e.title and e.system == "immune"


def test_deviation_severity_levels():
    base = alt_baseline(60.0, 2.0)  # std ≈ 2.08
    std = 2.0 * (14 / 13) ** 0.5
    for shift_z, expected in ((1.9, "info"), (2.5, "warning"), (4.0, "critical")):
        values = base + [60.0 + shift_z * std] * 7
        evs = run([long_df("AST-T", "resting_hr", values)], ["baseline_deviation"]).events
        assert [e.severity for e in evs] == [expected], shift_z


# --------------------------------------------------------------------------- trend
def test_trend_catches_rapid_worsening_that_deviation_misses():
    """İyileşmiş bir değer hızla geri bozuluyor: z7 henüz sapma eşiğinde değil ama trend yakalar."""
    values = alt_baseline(60.0, 1.0) + [58.0, 58.2] * 5 + [58.5, 59.2, 60.0, 60.8, 61.5, 62.2, 62.8, 63.2]
    res = run([long_df("AST-T", "resting_hr", values)], ["baseline_deviation", "trend"])
    assert [e.detector for e in res.events] == ["rule.trend"]
    (t,) = res.events
    assert "artış" in t.title and t.status == "active"


def test_trend_suppressed_while_deviation_warning():
    import numpy as np

    from app.analysis.catalog import load_catalog, load_rules
    from app.analysis.detectors.rules import deviation_levels

    values = alt_baseline(60.0, 1.0) + [60.0 + 0.9 * i for i in range(1, 15)]
    res = run([long_df("AST-T", "resting_hr", values)], ["baseline_deviation", "trend"])
    sf = res.astronauts["AST-T"].features["resting_hr"]
    dev_level, _ = deviation_levels(sf, load_catalog().metrics["resting_hr"], load_rules())
    warn_days = {d.date() for d in sf.frame.index[np.flatnonzero(dev_level >= 2)]}
    assert warn_days
    for e in res.events:
        if e.detector == "rule.trend":
            assert e.window.end not in warn_days and e.window.start not in warn_days


def test_trend_ignores_flat_noise():
    noise = [60.0, 61.5, 59.0, 60.5, 58.8, 61.2, 60.1] * 8
    assert run([long_df("AST-T", "resting_hr", noise)], ["trend"]).events == []


# --------------------------------------------------------------------------- örüntü
def test_system_pattern_multi_contributor_without_penalty():
    rhr = alt_baseline(60.0, 1.0) + [66.0] * 10
    hrv = alt_baseline(55.0, 3.0) + [40.0] * 10
    res = run([long_df("AST-T", "resting_hr", rhr), long_df("AST-T", "hrv_rmssd", hrv)], RULES)
    pattern = [e for e in res.events if e.detector == "rule.system_pattern"]
    assert len(pattern) == 1
    p = pattern[0]
    assert p.system == "cardiovascular" and len(p.contributors) == 2
    assert sum(c.weight for c in p.contributors) == pytest.approx(1.0, abs=0.01)
    assert {c.metric for c in p.contributors} == {"resting_hr", "hrv_rmssd"}
    cv = next(s for s in res.astronauts["AST-T"].systems if s.system == "cardiovascular")
    assert all(pen.event_id != p.event_id for pen in cv.penalties)


# --------------------------------------------------------------------------- registry
def test_unknown_detector_rejected():
    with pytest.raises(ValueError, match="Bilinmeyen"):
        build_detectors(["threshold", "nope"])


def test_custom_ml_detector_plugs_in():
    @register_detector("_test_anomaly")
    class FakeAnomaly:
        name = "ml.fake"

        def detect(self, ctx):
            return [HealthEvent(
                event_id=make_event_id("AST-T", "anomaly", self.name, "sleep", ctx.as_of), astronaut_id="AST-T",
                detected_at="2026-01-20T00:00:00Z", source="anomaly", system="sleep", severity="warning", score=0.8,
                title="test", window=DateWindow(start=ctx.as_of, end=ctx.as_of), detector=self.name,
                contributors=[Contributor(metric="sleep_duration", weight=0.7), Contributor(metric="sleep_quality", weight=0.3)],
            )]

    try:
        res = run([long_df("AST-T", "sleep_duration", [7.0] * 20)], ["threshold", "_test_anomaly"])
        assert [e.source for e in res.events] == ["anomaly"]
        sleep = next(s for s in res.astronauts["AST-T"].systems if s.system == "sleep")
        assert sleep.status == "yellow" and sleep.penalties[0].metric == "sleep_duration"
    finally:
        DETECTOR_REGISTRY.pop("_test_anomaly")


def test_example_detectors_produce_changepoint_and_forecast():
    values = alt_baseline(7.2, 0.3) + [7.2, 6.9, 7.4, 7.1] * 5 + [5.6, 5.4, 5.5, 5.2, 5.3, 5.1, 5.2, 5.0, 4.9, 5.0, 4.8, 4.7]
    res = run([long_df("AST-T", "sleep_duration", values)],
              ["threshold", "baseline_deviation", "trend", "example_changepoint", "example_forecast"])
    cp = [e for e in res.events if e.source == "changepoint"]
    fc = [e for e in res.events if e.source == "forecast"]
    assert cp and cp[0].changepoint_date == day(34)
    assert fc and len(fc[0].forecast.points) == 7
    assert fc[0].forecast.points[0].date == day(len(values))
