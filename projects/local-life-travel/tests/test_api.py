"""API / E2E tests through FastAPI TestClient."""
from __future__ import annotations

import json

from app.replay_tools import resolve_all

URL = "/api/v1/travel/runs"


def _post(client, request, key=None):
    headers = {"Idempotency-Key": key} if key else {}
    return client.post(URL, json=request, headers=headers)


def test_health_live_and_ready(client):
    live = client.get("/health/live")
    assert live.status_code == 200 and live.json()["status"] == "ok"
    assert live.json()["mode"] == "replay"
    ready = client.get("/health/ready")
    assert ready.status_code == 200
    d = ready.json()
    assert d["status"] == "ready"
    assert d["database"] == "ok"
    assert d["worker"] == "manual-drain (explicit test mode)"
    assert d["worker_healthy"] is True
    assert d["live_mode_enabled"] is False
    assert d["fixtures"] == 20


def test_ui_has_replay_banner_and_status_pills(client):
    html = client.get("/").text
    assert "REPLAY / 本地回放演示" in html
    assert "不连接真实地图" in html
    assert "结果不表示地点已核验" in html
    for cls in ("st-needs_input", "st-failed", "st-completed", "st-cancelled",
                "q-verified_feasible", "q-infeasible", "q-partially_verified", "q-unverified"):
        assert cls in html
    assert "replay fixture" in html


def test_fixtures_endpoint_declares_replay(client):
    d = client.get("/fixtures").json()
    assert d["count"] == 20 and d["mode"] == "replay"
    assert all(s["request"]["mode"] == "replay" for s in d["scenarios"])


def test_malformed_json_returns_422_not_500(client):
    r = client.post(URL, content=b"{not-json",
                    headers={"Content-Type": "application/json"})
    assert r.status_code == 422
    assert r.json()["code"] == "VALIDATION_ERROR"
    assert r.json()["field_errors"]


def test_malformed_json_on_revisions_returns_422(client, scenarios):
    created = _post(client, scenarios["F01"]["request"])
    rid = created.json()["run_id"]
    r = client.post(f"{URL}/{rid}/revisions", content=b"not-json",
                    headers={"Content-Type": "application/json"})
    assert r.status_code == 422
    assert r.json()["code"] == "VALIDATION_ERROR"


def test_invalid_request_returns_422_and_no_run(client, app, scenarios):
    bad = dict(scenarios["F01"]["request"])
    bad["candidates"] = bad["candidates"][:2]
    r = _post(client, bad)
    assert r.status_code == 422
    assert r.json()["code"] == "VALIDATION_ERROR"
    assert r.json()["field_errors"]
    assert app.state.store.count_runs() == 0  # T-01: no run, no tool call


def test_live_mode_rejected(client, app, scenarios):
    body = dict(scenarios["F01"]["request"])
    body["mode"] = "live"
    r = _post(client, body)
    assert r.status_code == 400
    assert r.json()["code"] == "LIVE_MODE_DISABLED"
    assert app.state.store.count_runs() == 0


def test_create_and_poll_run(client, app, scenarios):
    r = _post(client, scenarios["F01"]["request"])
    assert r.status_code == 202
    d = r.json()
    assert d["status"] == "queued" and d["mode"] == "replay"
    assert d["replay_notice"] and d["replayed"] is False
    app.state.worker.drain()
    got = client.get(f"{URL}/{d['run_id']}").json()
    assert got["status"] == "completed"
    assert got["quality_status"] == "verified_feasible"
    assert len(got["result"]["visits"]) == 3
    assert all(p["provider"] == "replay-fixture" for p in got["poi_records"])
    assert got["events"] and got["budget"]["tool_calls"] > 0
    assert got["mode"] == "replay"


def test_idempotency_same_and_conflict(client, app, scenarios):
    req = scenarios["F01"]["request"]
    r1 = _post(client, req, key="same-key")
    r2 = _post(client, req, key="same-key")
    assert r1.status_code == r2.status_code == 202
    assert r1.json()["run_id"] == r2.json()["run_id"]
    assert r2.json()["replayed"] is True

    different = dict(req)
    different["origin"] = "杭州站"
    r3 = _post(client, different, key="same-key")
    assert r3.status_code == 409
    assert r3.json()["code"] == "IDEMPOTENCY_CONFLICT"
    assert app.state.store.count_runs() == 1


def test_get_unknown_run_returns_404(client):
    r = client.get(f"{URL}/run_does_not_exist")
    assert r.status_code == 404
    assert r.json()["code"] == "RUN_NOT_FOUND"


def test_ambiguity_run_exposes_candidates(client, app, scenarios):
    r = _post(client, scenarios["F11"]["request"])
    app.state.worker.drain()
    got = client.get(f"{URL}/{r.json()['run_id']}").json()
    assert got["status"] == "needs_input"
    assert got["candidates_for_input"] and got["candidates_for_input"][0]["options"]
    assert got["result"] is None  # no placeholder plan


def test_revision_keeps_parent_result(client, app, scenarios):
    r = _post(client, scenarios["F19"]["request"])
    rid = r.json()["run_id"]
    app.state.worker.drain()
    parent = client.get(f"{URL}/{rid}").json()
    assert len(parent["result"]["visits"]) == 4

    rv = client.post(f"{URL}/{rid}/revisions",
                     json={"remove_candidates": ["雷峰塔"], "reason": "用户删除一个地点"})
    assert rv.status_code == 202
    cid = rv.json()["run_id"]
    app.state.worker.drain()
    child = client.get(f"{URL}/{cid}").json()
    assert child["parent_run_id"] == rid and child["revision"] == 2
    assert len(child["result"]["visits"]) == 3
    assert client.get(f"{URL}/{rid}").json()["result"] == parent["result"]


def test_revision_idempotency(client, app, scenarios):
    r = _post(client, scenarios["F19"]["request"])
    rid = r.json()["run_id"]
    before = app.state.store.count_runs()
    body = {"remove_candidates": ["雷峰塔"], "reason": "幂等修订"}
    first = client.post(f"{URL}/{rid}/revisions", json=body,
                        headers={"Idempotency-Key": "revision-same"})
    assert first.status_code == 202
    second = client.post(f"{URL}/{rid}/revisions", json=body,
                         headers={"Idempotency-Key": "revision-same"})
    assert second.status_code == 202
    assert second.json()["run_id"] == first.json()["run_id"]
    assert second.json()["replayed"] is True
    assert app.state.store.count_runs() == before + 1
    requests = [event for event in app.state.store.get_events(rid)
                if event["action"] == "REVISION_REQUESTED"]
    assert len(requests) == 1


def test_cancel_queued_run(client, app, scenarios):
    r = _post(client, scenarios["F01"]["request"])
    rid = r.json()["run_id"]
    c = client.post(f"{URL}/{rid}/cancel")
    assert c.status_code == 200 and c.json()["status"] == "cancelled"
    assert "不声称撤销远端" in c.json()["message"]
    app.state.worker.drain()
    assert client.get(f"{URL}/{rid}").json()["status"] == "cancelled"


def test_cancel_terminal_run_conflict(client, app, scenarios):
    r = _post(client, scenarios["F01"]["request"])
    rid = r.json()["run_id"]
    app.state.worker.drain()
    c = client.post(f"{URL}/{rid}/cancel")
    assert c.status_code == 409
    assert c.json()["code"] == "RUN_NOT_CANCELLABLE"


def test_every_response_carries_replay_declaration(client, app, scenarios):
    r = _post(client, scenarios["F01"]["request"])
    rid = r.json()["run_id"]
    app.state.worker.drain()
    bodies = [
        client.get("/health/live").json(),
        client.get("/health/ready").json(),
        client.get("/fixtures").json(),
        r.json(),
        client.get(f"{URL}/{rid}").json(),
    ]
    for body in bodies:
        assert body["mode"] == "replay"
        assert "replay" in body["replay_notice"].lower() or "回放" in body["replay_notice"]
    assert "已核验真实 POI" not in client.get("/").text


def test_all_scenarios_reachable_via_api(client, app):
    for s in resolve_all():
        r = _post(client, s["request"])
        assert r.status_code == 202, f"{s['id']}: {r.text[:200]}"
    app.state.worker.drain()
    assert app.state.store.count_runs() == 20
