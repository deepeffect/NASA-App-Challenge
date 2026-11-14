"""Sözleşme testleri: her endpoint cevap veriyor ve response modeline uyuyor."""

import json

from app.models.schemas import (
    SSE_MODELS,
    AlertListResponse,
    AstronautSummary,
    BriefingResponse,
    CatalogResponse,
    CheckinListResponse,
    CheckinResponse,
    CrewResponse,
    ExplainResponse,
    GroundReport,
    HealthResponse,
    MetricSeriesResponse,
)


def parse_sse(text: str) -> list[tuple[str, dict]]:
    events, name, data = [], None, []
    for line in text.splitlines():
        if line.startswith("event:"):
            name = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            data.append(line.split(":", 1)[1].strip())
        elif not line.strip() and name:
            events.append((name, json.loads("\n".join(data))))
            name, data = None, []
    if name:
        events.append((name, json.loads("\n".join(data))))
    return events


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    h = HealthResponse.model_validate(r.json())
    assert h.db.ok
    assert h.llm.provider == "mock" and h.llm.reachable


def test_catalog(client):
    c = CatalogResponse.model_validate(client.get("/api/metrics/catalog").json())
    names = {m.name for m in c.metrics}
    assert {"sleep_duration", "hrv_rmssd", "resting_hr", "radiation_cumulative"} <= names
    assert all(not m.threshold_verified for m in c.metrics), "eşikler placeholder olmalı"
    assert {s.id for s in c.systems} == {
        "cardiovascular", "musculoskeletal", "immune", "behavioral", "sleep", "radiation",
    }


def test_crew_and_summary(client):
    crew = CrewResponse.model_validate(client.get("/api/crew").json())
    assert len(crew.astronauts) >= 4
    assert crew.mission.as_of is not None
    aid = crew.astronauts[1].id
    s = AstronautSummary.model_validate(client.get(f"/api/astronauts/{aid}/summary").json())
    assert len(s.systems) == 6


def test_summary_404(client):
    assert client.get("/api/astronauts/NOPE/summary").status_code == 404


def test_metric_series(client):
    aid = client.get("/api/crew").json()["astronauts"][0]["id"]
    r = client.get(f"/api/astronauts/{aid}/metrics", params={"metric": "sleep_duration", "days": 30})
    assert r.status_code == 200
    m = MetricSeriesResponse.model_validate(r.json())
    assert 1 <= len(m.daily) <= 30
    assert m.metric.threshold_verified is False
    assert client.get(f"/api/astronauts/{aid}/metrics", params={"metric": "nope"}).status_code == 404


def test_metric_series_raw(client):
    aid = client.get("/api/crew").json()["astronauts"][0]["id"]
    r = client.get(f"/api/astronauts/{aid}/metrics", params={"metric": "heart_rate", "days": 2, "resolution": "raw"})
    assert r.status_code == 200
    assert len(MetricSeriesResponse.model_validate(r.json()).raw) > 0


def test_alerts_filters_and_actions(client):
    all_ = AlertListResponse.model_validate(client.get("/api/alerts", params={"status": "all"}).json())
    assert all_.count == len(all_.events)
    crit = client.get("/api/alerts", params={"min_severity": "warning"}).json()
    assert all(e["severity"] in ("warning", "critical") for e in crit["events"])
    if not all_.events:
        return
    ev = all_.events[0]
    assert client.get(f"/api/alerts/{ev.event_id}").status_code == 200
    r = client.post(f"/api/alerts/{ev.event_id}/explain", json={"lang": "en"})
    assert r.status_code == 200
    ExplainResponse.model_validate(r.json())
    r = client.post(f"/api/alerts/{ev.event_id}/feedback", json={"verdict": "false_alarm"})
    assert r.status_code == 200 and r.json()["verdict"] == "false_alarm"
    r = client.put(f"/api/alerts/{ev.event_id}/share", json={"share_with_ground": True})
    assert r.status_code == 200 and r.json()["share_with_ground"] is True
    assert client.post("/api/alerts/evt_doesnotexist/explain", json={}).status_code == 404


def test_briefing(client):
    aid = client.get("/api/crew").json()["astronauts"][1]["id"]
    r = client.get(f"/api/astronauts/{aid}/briefing", params={"lang": "en"})
    assert r.status_code == 200
    BriefingResponse.model_validate(r.json())


def test_checkin_and_emergency(client):
    aid = client.get("/api/crew").json()["astronauts"][0]["id"]
    body = {"astronaut_id": aid, "mood": 4, "stress": 2, "sleep_quality": 4, "note": "Feeling fine", "share_with_ground": True}
    r = client.post("/api/checkin", json=body)
    assert r.status_code == 201
    assert CheckinResponse.model_validate(r.json()).emergency is None

    body["note"] = "Had CHEST PAIN since this morning"
    em = CheckinResponse.model_validate(client.post("/api/checkin", json=body).json()).emergency
    assert em is not None and "chest_pain" in em.matched_symptoms

    assert client.post("/api/checkin", json={**body, "mood": 9}).status_code == 422
    lst = CheckinListResponse.model_validate(client.get(f"/api/astronauts/{aid}/checkins").json())
    assert lst.checkins


def test_chat_sse(client):
    aid = client.get("/api/crew").json()["astronauts"][1]["id"]
    body = {"astronaut_id": aid, "messages": [{"role": "user", "content": "How am I today?"}]}
    with client.stream("POST", "/api/chat", json=body) as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        text = "".join(r.iter_text())
    events = parse_sse(text)
    names = [n for n, _ in events]
    assert names[0] == "meta" and names[-1] == "done"
    assert "token" in names and "tool_call" in names and "tool_result" in names
    for name, payload in events:
        SSE_MODELS[name].model_validate(payload)


def test_chat_emergency_event(client):
    aid = client.get("/api/crew").json()["astronauts"][0]["id"]
    body = {"astronaut_id": aid, "messages": [{"role": "user", "content": "I can't breathe properly"}]}
    with client.stream("POST", "/api/chat", json=body) as r:
        events = parse_sse("".join(r.iter_text()))
    assert "emergency" in [n for n, _ in events]


def test_chat_validation(client):
    body = {"astronaut_id": "AST-01", "messages": [{"role": "assistant", "content": "hi"}]}
    assert client.post("/api/chat", json=body).status_code == 422


def test_ingest_accepts_upload(client):
    csv = "astronaut_id,timestamp,metric,value,unit\nAST-01,2026-11-14T08:00:00Z,resting_hr,61,bpm\n"
    r = client.post("/api/ingest", files={"file": ("x.csv", csv, "text/csv")})
    assert r.status_code == 200
    assert r.json()["rows_total"] >= 1


def test_ground_report(client):
    g = GroundReport.model_validate(client.get("/api/ground-report").json())
    assert g.crew


def test_openapi_contains_sse_models(client):
    schemas = client.get("/openapi.json").json()["components"]["schemas"]
    for name in ("SSEToken", "SSEToolCall", "SSEToolResult", "SSEDone", "EmergencyNotice", "HealthEvent", "ChatEventName"):
        assert name in schemas


def test_cors_preflight(client):
    r = client.options(
        "/api/crew",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"},
    )
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"
