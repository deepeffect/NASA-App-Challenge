from app.analysis.catalog import load_catalog, load_rules
from app.analysis.scoring import score_systems
from app.models.schemas import Contributor, DateWindow, HealthEvent

from .helpers import alt_baseline, long_df, run


def ev(severity, metric="sleep_duration", system="sleep", detector="rule.baseline_deviation", status="active", eid=None):
    return HealthEvent(
        event_id=eid or f"evt_{severity}_{metric}_{detector}", astronaut_id="A", detected_at="2026-01-01T00:00:00Z",
        source="rule", system=system, severity=severity, score=0.5, title="t",
        window=DateWindow(start="2026-01-01", end="2026-01-02"), contributors=[Contributor(metric=metric, weight=1)],
        detector=detector, status=status,
    )


def _sleep_features():
    res = run([long_df("A", "sleep_duration", [7.0] * 20)], [], astronauts=("A",))
    return res.astronauts["A"].features


def _score(events):
    systems, overall = score_systems(events, _sleep_features(), load_catalog(), load_rules())
    return {s.system: s for s in systems}, overall


def test_no_data_is_unknown():
    systems, overall = _score([])
    assert systems["sleep"].status == "green" and systems["sleep"].score == 100
    assert systems["radiation"].status == "unknown" and systems["radiation"].score is None
    assert overall.status == "green" and overall.worst_system is None


def test_info_keeps_green_warning_forces_yellow_critical_forces_red():
    s, _ = _score([ev("info")])
    assert (s["sleep"].status, s["sleep"].score) == ("green", 97)
    s, _ = _score([ev("warning")])
    assert (s["sleep"].status, s["sleep"].score) == ("yellow", 80)
    s, o = _score([ev("critical")])
    assert (s["sleep"].status, s["sleep"].score) == ("red", 55)
    assert o.status == "red" and o.worst_system == "sleep" and o.score == 55


def test_same_metric_penalized_once_with_max():
    s, _ = _score([ev("warning", detector="rule.threshold"), ev("critical")])
    assert s["sleep"].score == 55 and len(s["sleep"].penalties) == 1
    s, _ = _score([ev("warning"), ev("warning", metric="sleep_quality")])
    assert s["sleep"].score == 60


def test_resolved_and_pattern_events_do_not_penalize():
    s, _ = _score([ev("critical", status="resolved")])
    assert s["sleep"].status == "green"
    s, _ = _score([ev("critical", detector="rule.system_pattern")])
    assert s["sleep"].score == 100 and s["sleep"].status == "red"  # renge etki eder, ceza yok


def test_end_to_end_score_drops_with_real_detectors():
    values = alt_baseline(7.0, 0.3) + [5.0] * 10
    res = run([long_df("A", "sleep_duration", values)], ["threshold", "baseline_deviation", "trend", "system_pattern"],
              astronauts=("A",))
    a = res.astronauts["A"]
    sleep = next(s for s in a.systems if s.system == "sleep")
    assert sleep.status == "red" and sleep.score == 55
    assert a.overall.status == "red"
