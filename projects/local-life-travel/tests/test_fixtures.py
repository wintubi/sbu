"""Fixture contract tests + the frozen 20-scenario expectation matrix."""
from __future__ import annotations

from collections import Counter

import pytest

from app.domain import REPLAY_PROVIDER, TravelRequest
from app.engine import create_run
from app.replay_tools import ReplayAdapter, load_fixtures, resolve_all, scenario_index
from conftest import drain_with

EXPECTED_GROUPS = {
    "feasible": 6, "time_conflict": 4, "ambiguity": 3,
    "weather_coverage": 2, "tool_error": 3, "condition_modification": 2,
}


def test_scenario_groups_frozen_at_20():
    scenarios = resolve_all()
    assert len(scenarios) == 20
    assert dict(Counter(s["category"] for s in scenarios)) == EXPECTED_GROUPS
    assert len(scenario_index()) == 20


def test_fixture_file_declares_replay_only():
    data = load_fixtures()
    assert data["mode"] == "replay"
    assert "不表示已由真实供应商核验" in data["notice"]
    assert data["frozen_on"] == "2026-11-07"
    assert REPLAY_PROVIDER == "replay-fixture"


def test_all_fixture_requests_are_valid():
    for s in resolve_all():
        TravelRequest.model_validate(s["request"])


def _assert_expectation(run, expect, label):
    assert run["status"] == expect["status"], f"{label}: status"
    assert run["state"]["quality_status"] == expect["quality_status"], f"{label}: quality"
    issues = run["state"]["result"]["issues"] if run["state"]["result"] else run["state"]["issues"]
    codes = {i["code"] for i in issues}
    for required in expect.get("issue_codes", []):
        assert required in codes, f"{label}: missing issue {required}; got {sorted(codes)}"
    if expect.get("issue_codes") == []:
        assert not any(i["severity"] == "blocker" for i in issues), f"{label}: unexpected blocker"
    if "visit_count" in expect:
        assert len(run["state"]["result"]["visits"]) == expect["visit_count"], f"{label}: visit_count"
    if "has_changes" in expect:
        assert bool(run["state"]["changes"]) == expect["has_changes"], f"{label}: has_changes"


def test_all_20_scenarios_match_frozen_expectations(store, worker):
    for s in resolve_all():
        run = create_run(store, s["request"], scenario=s)
        worker.drain()
        got = store.get_run(run["run_id"])
        _assert_expectation(got, s["expect"], s["id"])


def test_weather_scenarios_do_not_use_current_weather(store, worker):
    for sid in ("F14", "F15"):
        s = next(x for x in resolve_all() if x["id"] == sid)
        run = create_run(store, s["request"], scenario=s)
        worker.drain()
        got = store.get_run(run["run_id"])
        weather_facts = [f for f in got["state"]["facts"] if f["subject_id"] == "weather"]
        assert weather_facts and weather_facts[0]["value"] is None
        assert weather_facts[0]["provider_status"] == "unavailable"


def test_revision_scenarios_match_expectations(store, worker):
    for s in resolve_all():
        if "revision" not in s:
            continue
        parent = create_run(store, s["request"], scenario=s)
        worker.drain()
        parent_got = store.get_run(parent["run_id"])
        _assert_expectation(parent_got, s["expect"], s["id"] + ":parent")

        from app.engine import derive_revision
        derived = derive_revision(parent_got, s["revision"])
        child = create_run(store, derived, scenario=s,
                           parent_run_id=parent["run_id"], revision=2)
        worker.drain()
        child_got = store.get_run(child["run_id"])
        exp = s["revision_expect"]
        assert child_got["status"] == exp["status"], s["id"]
        assert child_got["state"]["quality_status"] == exp["quality_status"], s["id"]
        assert len(child_got["state"]["result"]["visits"]) == exp["visit_count"], s["id"]
        assert child_got["parent_run_id"] == parent["run_id"]
        # parent result is unchanged
        assert store.get_run(parent["run_id"])["state"]["result"] == parent_got["state"]["result"]


def test_provider_is_replay_fixture_on_every_matched_poi(store, scenarios):
    s = scenarios["F01"]
    run = create_run(store, s["request"], scenario=s)
    got = drain_with(store, run["run_id"], ReplayAdapter(s))
    records = got["state"]["poi_records"]
    assert len(records) == 3
    assert all(r["provider"] == REPLAY_PROVIDER for r in records)
    assert all(r["evidence_refs"] for r in records)
    assert all(r["fetched_at"] for r in records)
