from __future__ import annotations

import types
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.domain import LiveTravelRequest, ToolResult, ToolStatus, leg_key, utc_now
from app.live import build_live_run
from app.main import create_app

NAMES = ["故宫博物院", "景山公园", "天安门广场"]


class FakeAdapter:
    def __init__(self, mode: str = "ok"):
        self.mode = mode
        self.calls = 0

    def resolve_origin(self, address: str):
        city = "天津" if self.mode == "origin_cross_city" else "北京"
        return ToolResult(status=ToolStatus.VALID, source_ref="fake:origin", fetched_at=utc_now(),
                          payload={"poi": {"name": address, "city": city,
                                           "coordinates": {"lon": 116.4, "lat": 39.9}}})

    def poi_lookup(self, key: str, selected_poi_id: str | None = None):
        self.calls += 1
        if self.mode == "ambiguous" and key == "景山公园":
            if selected_poi_id:
                return ToolResult(status=ToolStatus.VALID, source_ref=f"fake:poi:{key}",
                                  fetched_at=utc_now(),
                                  payload={"match_status": "matched", "selected_by_user": True,
                                           "poi": {"provider_poi_id": selected_poi_id, "name": key,
                                                   "city": "北京",
                                                   "coordinates": {"lon": 116.4, "lat": 39.9}}})
            return ToolResult(status=ToolStatus.VALID, source_ref=f"fake:poi:{key}", fetched_at=utc_now(),
                              payload={"match_status": "ambiguous",
                                       "options": [{"provider_poi_id": "A", "name": key},
                                                   {"provider_poi_id": "B", "name": key}]})
        if self.mode == "provider_error" and key == "景山公园":
            return ToolResult(status=ToolStatus.PROVIDER_ERROR, source_ref=f"fake:poi:{key}",
                              fetched_at=utc_now(), error_code="TOOL_PROVIDER_ERROR",
                              message="fake provider error")
        city = "天津" if self.mode == "cross_city" and key == "景山公园" else "北京"
        return ToolResult(status=ToolStatus.VALID, source_ref=f"fake:poi:{key}", fetched_at=utc_now(),
                          payload={"match_status": "matched",
                                   "poi": {"provider_poi_id": key, "name": key, "city": city,
                                           "coordinates": {"lon": 116.4, "lat": 39.9}}})

    def weather(self, date: str):
        return ToolResult(status=ToolStatus.VALID, source_ref="fake:weather", fetched_at=utc_now(),
                          payload={"date": date, "summary": "晴"})

    def hours(self):
        if self.mode == "hours_empty":
            return ToolResult(status=ToolStatus.EMPTY, source_ref="fake:hours",
                              fetched_at=utc_now(), message="no hours")
        return ToolResult(status=ToolStatus.VALID, source_ref="fake:hours", fetched_at=utc_now(),
                          payload={"windows": {name: ["09:00", "17:00"] for name in NAMES}})

    def matrix(self, pairs):
        matrix = {}
        for a, b in pairs:
            matrix[leg_key(a, b)] = {"duration_seconds": 600, "distance_meters": 1000,
                                     "source_ref": "fake:route", "fetched_at": utc_now()}
        return ToolResult(status=ToolStatus.VALID, source_ref="fake:routes", fetched_at=utc_now(),
                          payload={"matrix": matrix})


class CountingAdapter(FakeAdapter):
    """Fake adapter whose client reports several HTTP calls per method."""

    def __init__(self, mode: str = "ok"):
        super().__init__(mode)
        self.client = types.SimpleNamespace(calls=0)

    def resolve_origin(self, address):
        self.client.calls += 1
        return super().resolve_origin(address)

    def poi_lookup(self, key, selected_poi_id=None):
        self.client.calls += 1
        return super().poi_lookup(key, selected_poi_id)

    def weather(self, date):
        self.client.calls += 1
        return super().weather(date)

    def hours(self):
        self.client.calls += 2
        return super().hours()

    def matrix(self, pairs):
        self.client.calls += len(pairs)
        return super().matrix(pairs)


def live_body() -> dict:
    return {
        "mode": "live", "city": "北京", "date": "2026-11-09", "timezone": "Asia/Shanghai",
        "origin": "北京站",
        "time_window": {"start": "2026-11-09T09:00:00+08:00",
                        "end": "2026-11-09T18:00:00+08:00"},
        "transport": "walking",
        "candidates": [{"name": name, "stay_seconds": 3600} for name in NAMES],
    }


@pytest.fixture
def live_client(store, worker):
    adapter = FakeAdapter()
    app = create_app(store=store, worker=worker, manual_drain=True,
                     live_adapter_factory=lambda city, transport: adapter)
    with TestClient(app) as client:
        yield client, adapter


def test_live_run_is_not_replay_worker_runnable(store):
    request = LiveTravelRequest.model_validate(live_body())
    store.create_run(build_live_run(request))
    assert store.list_runnable() == []


def test_live_run_success(live_client):
    client, adapter = live_client
    response = client.post("/api/v1/travel/live-runs", json=live_body(),
                           headers={"Idempotency-Key": "live-ok"})
    assert response.status_code == 202, response.text
    data = response.json()
    assert data["mode"] == "live"
    assert data["status"] == "completed"
    assert data["quality_status"] == "verified_feasible"
    assert len(data["result"]["visits"]) == 3
    assert data["budget"]["tool_calls"] == 7
    assert adapter.calls == 3


def test_live_ambiguous_needs_input(live_client):
    client, _ = live_client
    client.app.state.live_adapter_factory = lambda city, transport: FakeAdapter("ambiguous")
    response = client.post("/api/v1/travel/live-runs", json=live_body(),
                           headers={"Idempotency-Key": "live-ambiguous"})
    data = response.json()
    assert data["status"] == "needs_input"
    assert data["quality_status"] == "partially_verified"
    assert data["candidates_for_input"][0]["candidate"] == "景山公园"


def test_live_ambiguous_can_be_revised(live_client):
    client, _ = live_client
    client.app.state.live_adapter_factory = lambda city, transport: FakeAdapter("ambiguous")
    first = client.post("/api/v1/travel/live-runs", json=live_body(),
                        headers={"Idempotency-Key": "live-ambiguous-rev"})
    assert first.status_code == 202
    parent = first.json()
    assert parent["status"] == "needs_input"
    assert parent["candidates_for_input"][0]["candidate"] == "景山公园"

    revised = client.post(f"/api/v1/travel/runs/{parent['run_id']}/revisions",
                          json={"selected_poi_ids": {"景山公园": "B"},
                                "reason": "选择第二个候选"},
                          headers={"Idempotency-Key": "live-revision-1"})
    assert revised.status_code == 202, revised.text
    child = revised.json()
    assert child["mode"] == "live"
    assert child["parent_run_id"] == parent["run_id"]
    assert child["revision"] == 2
    assert child["result"]["revision"] == 2
    assert child["status"] == "completed"
    assert len(child["versions"]) == 2
    events_before = len(client.app.state.store.get_events(child["run_id"]))
    replay = client.post(f"/api/v1/travel/runs/{parent['run_id']}/revisions",
                         json={"selected_poi_ids": {"景山公园": "B"},
                               "reason": "选择第二个候选"},
                         headers={"Idempotency-Key": "live-revision-1"})
    assert replay.status_code == 202
    assert replay.json()["run_id"] == child["run_id"]
    assert replay.json()["replayed"] is True
    assert len(client.app.state.store.get_events(child["run_id"])) == events_before
    old = client.get(f"/api/v1/travel/runs/{parent['run_id']}").json()
    assert old["status"] == "needs_input"


def test_live_manual_opening_window_is_applied(live_client):
    client, _ = live_client
    client.app.state.live_adapter_factory = lambda city, transport: FakeAdapter("hours_empty")
    body = live_body()
    body["manual_facts"] = [{"subject": "景山公园", "field": "opening_window",
                             "value": "09:00-17:00", "reason": "人工补充"}]
    response = client.post("/api/v1/travel/live-runs", json=body,
                           headers={"Idempotency-Key": "live-manual"})
    data = response.json()
    subjects = {issue.get("subject") for issue in data["issues"] if issue["code"] == "HOURS_UNKNOWN"}
    assert "景山公园" not in subjects
    assert any(fact["source_type"] == "manual_input" and fact["subject_id"] == "景山公园"
               for fact in data["facts"])


def test_live_budget_counts_internal_http_requests(live_client, monkeypatch):
    import app.live as live_module
    monkeypatch.setattr(live_module, "LIVE_MAX_TOOL_CALLS", 20)
    client, _ = live_client
    client.app.state.live_adapter_factory = lambda city, transport: CountingAdapter()
    response = client.post("/api/v1/travel/live-runs", json=live_body(),
                           headers={"Idempotency-Key": "live-http-count"})
    data = response.json()
    assert data["status"] == "completed"
    assert data["budget"]["tool_calls"] == 13  # origin1 + poi3 + weather1 + hours2 + matrix6


def test_live_budget_is_enforced(live_client, monkeypatch):
    import app.live as live_module
    monkeypatch.setattr(live_module, "LIVE_MAX_TOOL_CALLS", 2)
    client, _ = live_client
    response = client.post("/api/v1/travel/live-runs", json=live_body(),
                           headers={"Idempotency-Key": "live-budget"})
    data = response.json()
    assert data["status"] == "failed"
    assert data["budget"]["status"] == "exhausted"
    assert any(issue["code"] == "BUDGET_EXHAUSTED" for issue in data["issues"])


def test_live_provider_error_is_failed_not_success(live_client):
    client, _ = live_client
    client.app.state.live_adapter_factory = lambda city, transport: FakeAdapter("provider_error")
    response = client.post("/api/v1/travel/live-runs", json=live_body(),
                           headers={"Idempotency-Key": "live-error"})
    data = response.json()
    assert data["status"] == "failed"
    assert any(issue["code"] == "TOOL_PROVIDER_ERROR" for issue in data["issues"])


def test_live_cross_city_is_blocked(live_client):
    client, _ = live_client
    client.app.state.live_adapter_factory = lambda city, transport: FakeAdapter("cross_city")
    response = client.post("/api/v1/travel/live-runs", json=live_body(),
                           headers={"Idempotency-Key": "live-cross"})
    data = response.json()
    assert data["status"] == "failed"
    assert any(issue["code"] == "CROSS_CITY_POI" for issue in data["issues"])


def test_live_origin_outside_city_fails(live_client):
    client, _ = live_client
    client.app.state.live_adapter_factory = lambda city, transport: FakeAdapter("origin_cross_city")
    response = client.post("/api/v1/travel/live-runs", json=live_body(),
                           headers={"Idempotency-Key": "live-origin-cross"})
    data = response.json()
    assert data["status"] == "failed"
    assert any(issue["code"] == "ORIGIN_OUTSIDE_CITY" for issue in data["issues"])


def test_live_requires_key(client, monkeypatch):
    monkeypatch.delenv("AMAP_API_KEY", raising=False)
    response = client.post("/api/v1/travel/live-runs", json=live_body())
    assert response.status_code == 503
    assert response.json()["code"] == "LIVE_NOT_CONFIGURED"


def test_live_idempotency_conflict(live_client):
    client, _ = live_client
    first = client.post("/api/v1/travel/live-runs", json=live_body(),
                        headers={"Idempotency-Key": "live-conflict"})
    assert first.status_code == 202
    changed = live_body()
    changed["candidates"][0]["stay_seconds"] = 7200
    conflict = client.post("/api/v1/travel/live-runs", json=changed,
                           headers={"Idempotency-Key": "live-conflict"})
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "IDEMPOTENCY_CONFLICT"


def test_live_idempotency_replay(live_client):
    client, adapter = live_client
    first = client.post("/api/v1/travel/live-runs", json=live_body(),
                        headers={"Idempotency-Key": "live-same"})
    calls = adapter.calls
    second = client.post("/api/v1/travel/live-runs", json=live_body(),
                         headers={"Idempotency-Key": "live-same"})
    assert second.status_code == 202
    assert second.json()["run_id"] == first.json()["run_id"]
    assert adapter.calls == calls
    assert client.app.state.store.count_runs() >= 1
