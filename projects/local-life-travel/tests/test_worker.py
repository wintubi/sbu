"""Worker / engine integration: restart, budget, ambiguity, error states, revisions."""
from __future__ import annotations

import pytest

from app.engine import create_run, derive_revision
from app.replay_tools import resolve_all
from app.store import Store
from app.worker import Worker


def _scenario(sid):
    return next(s for s in resolve_all() if s["id"] == sid)


def _run(store, worker, sid, **kwargs):
    s = _scenario(sid)
    run = create_run(store, s["request"], scenario=s, **kwargs)
    worker.drain()
    return s, store.get_run(run["run_id"])


def test_restart_resumes_without_duplicate_stage(store, worker, db_path):
    s = _scenario("F01")
    run = create_run(store, s["request"], scenario=s)
    assert worker.tick() and worker.tick()  # validate + resolve_poi persisted

    fresh_store = Store(db_path)
    fresh_worker = Worker(fresh_store, autostart=False)
    try:
        fresh_worker.drain()
        got = fresh_store.get_run(run["run_id"])
        assert got["status"] == "completed"
        stages = got["state"]["completed_stages"]
        assert len(stages) == 6 and len(set(stages)) == 6
        stage_events = [e for e in fresh_store.get_events(run["run_id"])
                        if e["action"] == "STAGE_COMPLETED"]
        assert len(stage_events) == 6
        assert [e["stage"] for e in stage_events] == stages
        assert all(e["reason"] for e in stage_events)
    finally:
        fresh_worker.stop()
        fresh_store.close()


def test_budget_exhaustion_stops_and_keeps_partial(store, worker):
    s, got = _run(store, worker, "F01", budget_limits={"max_tool_calls": 2})
    assert got["status"] == "failed"
    assert got["budget"]["status"] == "exhausted"
    assert got["budget"]["tool_calls"] == 2
    assert any(i["code"] == "BUDGET_EXHAUSTED" for i in got["state"]["issues"])
    assert len(got["state"]["tool_results"]) == 2  # partial results preserved
    assert got["state"]["poi_records"]  # already-resolved POIs are kept


def test_budget_total_time_limit_is_enforced(store, worker):
    s, got = _run(store, worker, "F01", budget_limits={"max_total_seconds": -1})
    assert got["status"] == "failed"
    assert got["budget"]["status"] == "exhausted"
    assert got["budget"]["elapsed_seconds"] >= 0
    assert any(i["code"] == "BUDGET_EXHAUSTED" for i in got["state"]["issues"])


def test_ambiguity_needs_input_with_candidates(store, worker):
    for sid in ("F11", "F12", "F13"):
        _, got = _run(store, worker, sid)
        assert got["status"] == "needs_input", sid
        assert got["state"]["candidates_for_input"], sid
        assert got["state"]["result"] is None, sid  # no placeholder itinerary
        assert any(i["code"] == "AMBIGUOUS_POI" for i in got["state"]["issues"]), sid


def test_revision_resolves_ambiguity(store, worker):
    s, parent = _run(store, worker, "F11")
    group = parent["state"]["candidates_for_input"][0]
    selected = {group["candidate"]: group["options"][0]["provider_poi_id"]}
    derived = derive_revision(parent, {"selected_poi_ids": selected, "reason": "用户选择候选"})
    child = create_run(store, derived, scenario=s, parent_run_id=parent["run_id"], revision=2)
    worker.drain()
    got = store.get_run(child["run_id"])
    assert got["parent_run_id"] == parent["run_id"]
    assert got["revision"] == 2
    assert got["status"] == "completed"
    assert got["state"]["candidates_for_input"] == []
    assert store.get_run(parent["run_id"])["state"]["result"] is None  # old result preserved


def test_format_error_not_masked_as_success(store, worker):
    _, got = _run(store, worker, "F16")
    assert got["status"] == "failed"
    assert got["state"]["quality_status"] == "unverified"
    codes = {i["code"] for i in got["state"]["issues"]}
    assert "TOOL_FORMAT_ERROR" in codes
    assert got["state"]["result"] is None
    # the failing tool result is recorded, not turned into "success + empty list"
    bad = [t for t in got["state"]["tool_results"] if t["tool"] == "poi"]
    assert bad and bad[0]["status"] == "format_error"


def test_unknown_constraints_partial(store, worker):
    for sid in ("F17", "F18"):
        _, got = _run(store, worker, sid)
        assert got["status"] == "completed", sid
        assert got["state"]["quality_status"] == "partially_verified", sid
        assert any(i["code"] in ("TOOL_TIMEOUT", "TOOL_PROVIDER_ERROR")
                   for i in got["state"]["issues"]), sid


def test_time_conflict_scenarios_are_infeasible(store, worker):
    for sid in ("F07", "F08", "F09", "F10"):
        _, got = _run(store, worker, sid)
        assert got["status"] == "completed", sid
        assert got["state"]["quality_status"] == "infeasible", sid
        assert any(i["severity"] == "blocker" for i in got["state"]["result"]["issues"]), sid


def test_weather_out_of_coverage(store, worker):
    for sid in ("F14", "F15"):
        _, got = _run(store, worker, sid)
        assert got["state"]["quality_status"] == "partially_verified", sid
        assert any(i["code"] == "WEATHER_DATE_NOT_COVERED" for i in got["state"]["issues"]), sid


def test_reorder_fixture_records_change(store, worker):
    _, got = _run(store, worker, "F06")
    assert got["state"]["quality_status"] == "verified_feasible"
    assert len(got["state"]["changes"]) == 1
    assert got["state"]["changes"][0]["kind"] == "reorder"
    assert "非全局最优" in got["state"]["changes"][0]["reason"]
    assert got["state"]["result"]["changes"]


def test_completed_does_not_mean_feasible(store, worker):
    _, got = _run(store, worker, "F07")
    assert got["status"] == "completed"
    assert got["state"]["quality_status"] == "infeasible"


def test_cancel_cannot_be_resurrected_by_late_save(store, worker):
    s = _scenario("F01")
    run = create_run(store, s["request"], scenario=s)
    assert store.cancel_run(run["run_id"]) == "ok"
    stale = store.get_run(run["run_id"])
    stale["status"] = "running"  # simulate an in-flight worker writing late
    store.save_run(stale)
    assert store.get_run(run["run_id"])["status"] == "cancelled"
    worker.drain()
    assert store.get_run(run["run_id"])["status"] == "cancelled"


def test_worker_logs_unexpected_error_and_marks_terminal(store, worker, monkeypatch):
    import app.worker as worker_mod

    def boom(*_args, **_kwargs):
        raise RuntimeError("injected stage failure")

    monkeypatch.setattr(worker_mod, "advance", boom)
    s = _scenario("F01")
    run = create_run(store, s["request"], scenario=s)
    assert worker.tick() is True
    assert worker.last_error and "injected stage failure" in worker.last_error
    got = store.get_run(run["run_id"])
    assert got["status"] == "failed"  # no infinite retry
    assert any(i["code"] == "STAGE_EXECUTION_ERROR" for i in got["state"]["issues"])
    assert worker.tick() is False
