"""Veri endpoint'leri: gerçek DB + analiz motoru (seed=42 demo senaryosu)."""

from app.models.schemas import AlertListResponse, AstronautSummary, CrewResponse, MetricSeriesResponse


def test_crew_end_state(client):
    crew = CrewResponse.model_validate(client.get("/api/crew").json())
    assert crew.mission.mission_day == 180 and crew.mission.total_days == 180
    status = {a.id: a.status for a in crew.astronauts}
    assert status == {"AST-01": "green", "AST-02": "red", "AST-03": "green", "AST-04": "green"}
    a2 = next(a for a in crew.astronauts if a.id == "AST-02")
    assert a2.active_events.critical > 0
    assert {"sleep", "behavioral", "cardiovascular"} <= set(a2.attention_systems)


def test_crew_time_slider(client):
    crew = CrewResponse.model_validate(client.get("/api/crew", params={"as_of": "2026-10-10"}).json())
    assert crew.mission.as_of.isoformat() == "2026-10-10"
    assert crew.mission.mission_day == 145
    assert {a.status for a in crew.astronauts} == {"green"}
    # aralık dışı tarih görev sınırlarına sıkıştırılır
    late = CrewResponse.model_validate(client.get("/api/crew", params={"as_of": "2030-01-01"}).json())
    assert late.mission.as_of == late.mission.latest_date


def test_summary(client):
    s = AstronautSummary.model_validate(client.get("/api/astronauts/AST-02/summary").json())
    assert s.overall.status == "red"
    assert len(s.systems) == 6
    assert s.active_events and all(e.status == "active" for e in s.active_events)
    snap = {m.metric: m for m in s.latest}
    assert snap["sleep_duration"].state == "alert"
    assert snap["sleep_duration"].baseline_mean > snap["sleep_duration"].value
    assert snap["radiation_cumulative"].state == "normal"
    sleep = next(x for x in s.systems if x.system == "sleep")
    assert sleep.penalties and sleep.score < 80


def test_metric_series(client):
    r = client.get("/api/astronauts/AST-02/metrics", params={"metric": "sleep_duration", "days": 30})
    m = MetricSeriesResponse.model_validate(r.json())
    assert 25 <= len(m.daily) <= 30
    assert m.baseline is not None and m.baseline.n_days >= 10
    assert m.metric.thresholds.warning.low == 6.0 and m.metric.threshold_verified is False
    assert any(e.detector == "rule.baseline_deviation" for e in m.events)
    assert all(any(c.metric == "sleep_duration" for c in e.contributors) for e in m.events)

    raw = MetricSeriesResponse.model_validate(client.get(
        "/api/astronauts/AST-01/metrics", params={"metric": "heart_rate", "days": 1, "resolution": "raw"}).json())
    assert 18 <= len(raw.raw) <= 24
    assert raw.raw[0].timestamp.tzinfo is not None


def test_alerts_filters(client):
    all_ = AlertListResponse.model_validate(client.get("/api/alerts", params={"status": "all"}).json())
    active = AlertListResponse.model_validate(client.get("/api/alerts").json())
    assert all_.count >= active.count > 0
    assert all(e.status == "active" for e in active.events)
    ranks = [{"critical": 3, "warning": 2, "info": 1}[e.severity] for e in active.events]
    assert ranks == sorted(ranks, reverse=True)

    crit = client.get("/api/alerts", params={"min_severity": "critical", "astronaut_id": "AST-02"}).json()
    assert crit["count"] > 0 and {e["severity"] for e in crit["events"]} == {"critical"}
    sev = client.get("/api/alerts", params=[("severity", "warning"), ("severity", "critical"), ("astronaut_id", "AST-01")]).json()
    assert sev["count"] == 0
    met = client.get("/api/alerts", params={"metric": "resting_hr", "astronaut_id": "AST-02"}).json()
    assert met["count"] > 0
    sys_ = client.get("/api/alerts", params={"system": "behavioral", "source": "rule"}).json()
    assert all(e["system"] == "behavioral" for e in sys_["events"])


def test_feedback_share_and_ground_report(client):
    ev = client.get("/api/alerts", params={"astronaut_id": "AST-02", "min_severity": "critical"}).json()["events"][0]
    eid = ev["event_id"]
    assert ev["feedback"] is None and ev["share_with_ground"] is False

    assert client.post(f"/api/alerts/{eid}/feedback", json={"verdict": "useful", "comment": "doğru"}).status_code == 200
    assert client.get(f"/api/alerts/{eid}").json()["feedback"] == "useful"
    assert client.put(f"/api/alerts/{eid}/share", json={"share_with_ground": True}).json()["share_with_ground"] is True
    assert client.get(f"/api/alerts/{eid}").json()["share_with_ground"] is True

    g = client.get("/api/ground-report", params={"days": 7}).json()
    a2 = next(m for m in g["crew"] if m["astronaut"]["id"] == "AST-02")
    assert eid in {e["event_id"] for e in a2["shared_events"]}
    assert all(c["share_with_ground"] for m in g["crew"] for c in m["shared_checkins"])
    assert g["period"]["end"] == "2026-11-14"

    client.put(f"/api/alerts/{eid}/share", json={"share_with_ground": False})
    assert client.post("/api/alerts/evt_000000000000/feedback", json={"verdict": "useful"}).status_code == 404


def test_checkins_list_and_create(client):
    lst = client.get("/api/astronauts/AST-02/checkins", params={"days": 7}).json()["checkins"]
    assert 5 <= len(lst) <= 8
    ts = [c["timestamp"] for c in lst]
    assert ts == sorted(ts, reverse=True)

    body = {"astronaut_id": "AST-03", "mood": 2, "stress": 5, "sleep_quality": 2, "note": "Nefes darlığı var",
            "share_with_ground": True}
    r = client.post("/api/checkin", json=body)
    assert r.status_code == 201
    data = r.json()
    assert data["emergency"]["matched_symptoms"] == ["breathing"]
    assert data["checkin"]["emergency"] is True
    recent = client.get("/api/astronauts/AST-03/checkins", params={"days": 3}).json()["checkins"]
    assert data["checkin"]["id"] in {c["id"] for c in recent}


def test_ingest_endpoint(client):
    csv = "astronaut_id,timestamp,metric,value,unit\nAST-04,2026-11-14T10:00:00Z,body_temp,98.9,F\n"
    r = client.post("/api/ingest", files={"file": ("t.csv", csv, "text/csv")})
    assert r.status_code == 200
    rep = r.json()
    assert (rep["adapter"], rep["rows_accepted"]) == ("long_csv", 1)
    bad = client.post("/api/ingest", files={"file": ("x.txt", "hello\nworld\n", "text/plain")})
    assert bad.status_code == 400


def test_404s(client):
    assert client.get("/api/astronauts/AST-99/summary").status_code == 404
    assert client.get("/api/astronauts/AST-01/metrics", params={"metric": "nope"}).status_code == 404
    assert client.get("/api/alerts", params={"astronaut_id": "AST-99"}).status_code == 404
    assert client.get("/api/alerts/evt_nope").status_code == 404
