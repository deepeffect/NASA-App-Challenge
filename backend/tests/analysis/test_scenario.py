"""Demo senaryosu testleri: AST-02 kırmızıya döner, diğerleri yeşil kalır.

Kural parametrelerini (rules.yaml) değiştirdiğinde bu testler geçmeli.
"""

from datetime import date, timedelta

import pytest

from app.analysis.engine import AnalysisEngine
from app.data.synthetic import SyntheticConfig, generate
from app.models.schemas import SEVERITY_RANK, AstronautInfo

START = date(2026, 5, 19)
NORMALS = ("AST-01", "AST-03", "AST-04")


def mission_day(n: int) -> date:
    return START + timedelta(days=n - 1)


def _setup(seed: int):
    d = generate(SyntheticConfig(seed=seed))
    return AnalysisEngine(), d.measurements, [AstronautInfo(id=a["id"], name=a["name"]) for a in d.astronauts]


@pytest.fixture(scope="module")
def scenario():
    return _setup(42)


def test_end_state(scenario):
    eng, df, astros = scenario
    r = eng.run(df, astros)
    assert r.mission().mission_day == 180
    a2 = r.astronauts["AST-02"]
    assert a2.overall.status == "red"
    red = {s.system for s in a2.systems if s.status == "red"}
    assert {"sleep", "behavioral", "cardiovascular"} <= red
    for aid in NORMALS:
        a = r.astronauts[aid]
        assert a.overall.status == "green", aid
        noisy = [e for e in a.events if e.severity != "info"]
        assert noisy == [], (aid, [(e.detector, e.title) for e in noisy])


def test_everyone_green_before_scenario(scenario):
    eng, df, astros = scenario
    r = eng.run(df, astros, mission_day(140))
    for aid, a in r.astronauts.items():
        assert a.overall.status == "green", aid
        assert not [e for e in a.active_events if SEVERITY_RANK[e.severity] >= 2], aid


def test_escalation_timeline(scenario):
    eng, df, astros = scenario
    status = {n: eng.run(df, astros, mission_day(n)).astronauts["AST-02"].overall.status for n in (149, 153, 160)}
    assert status[149] == "green"
    assert status[153] in ("yellow", "red")
    assert status[160] == "red"


def test_cascade_order(scenario):
    """Uyku → (stres, HRV) → istirahat nabzı sırasıyla tespit edilir."""
    eng, df, astros = scenario
    events = [e for e in eng.run(df, astros).astronauts["AST-02"].events
              if e.severity != "info" and e.window.start >= mission_day(145) and len(e.contributors) == 1]
    first = {}
    for e in events:
        m = e.contributors[0].metric
        first[m] = min(first.get(m, e.window.start), e.window.start)
    assert first["sleep_duration"] < first["stress"] <= first["resting_hr"]
    assert first["sleep_duration"] < first["hrv_rmssd"] <= first["resting_hr"]


def test_event_ids_stable_over_time_slider(scenario):
    eng, df, astros = scenario
    early = {e.event_id for e in eng.run(df, astros, mission_day(165)).astronauts["AST-02"].events
             if e.detector == "rule.baseline_deviation" and e.contributors[0].metric == "sleep_duration"}
    late = {e.event_id for e in eng.run(df, astros).astronauts["AST-02"].events
            if e.detector == "rule.baseline_deviation" and e.contributors[0].metric == "sleep_duration"}
    assert early and early <= late


@pytest.mark.parametrize("seed", [1, 2])
def test_robust_across_seeds(seed):
    eng, df, astros = _setup(seed)
    r = eng.run(df, astros)
    assert r.astronauts["AST-02"].overall.status == "red"
    for aid in NORMALS:
        a = r.astronauts[aid]
        assert a.overall.status == "green", aid
        assert len([e for e in a.events if e.severity == "warning"]) <= 1
        assert not [e for e in a.events if e.severity == "critical"]


def test_spe_raises_radiation_events():
    d = generate(SyntheticConfig(seed=42, spe_day=120))
    eng = AnalysisEngine()
    r = eng.run(d.measurements, [AstronautInfo(id=a["id"], name=a["name"]) for a in d.astronauts], mission_day(121))
    for aid, a in r.astronauts.items():
        rad = [e for e in a.active_events if e.system == "radiation" and e.severity != "info"]
        assert rad, aid
        assert any(e.detector == "rule.threshold" for e in rad)
