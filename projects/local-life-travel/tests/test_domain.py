"""Pure domain / T-01 / T-04 unit tests (no DB, no API)."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from pydantic import ValidationError

from app.domain import (
    ORIGIN_KEY,
    Candidate,
    QualityStatus,
    TravelRequest,
    evaluate_timeline,
    greedy_reorder,
    leg_key,
    parse_dt,
    resolve_zone,
    validate_local_datetime,
)
from app.engine import create_run
from app.replay_tools import ReplayAdapter, load_fixtures, resolve_scenario
from conftest import drain_with


def _base_request(scenarios):
    return scenarios["F01"]["request"]


def _mutated(base, **changes):
    d = dict(base)
    d.update(changes)
    return d


# --------------------------------------------------------------------------- #
# T-01
# --------------------------------------------------------------------------- #

def test_t01_valid_request(scenarios):
    assert TravelRequest.model_validate(_base_request(scenarios)).mode == "replay"


@pytest.mark.parametrize("field,value", [
    ("date", "not-a-date"),
    ("city", ""),
    ("origin", ""),
    ("transport", "rocket"),
    ("timezone", "Mars/Phobos"),
])
def test_t01_invalid_scalar_fields(scenarios, field, value):
    with pytest.raises(ValidationError):
        TravelRequest.model_validate(_mutated(_base_request(scenarios), **{field: value}))


def test_t01_invalid_time_window_end_before_start(scenarios):
    bad = _mutated(_base_request(scenarios))
    bad["time_window"] = {"start": "2026-11-08T18:00:00+08:00", "end": "2026-11-08T09:00:00+08:00"}
    with pytest.raises(ValidationError):
        TravelRequest.model_validate(bad)


def test_t01_window_must_be_single_local_day(scenarios):
    bad = _mutated(_base_request(scenarios))
    bad["time_window"] = {"start": "2026-11-08T09:00:00+08:00", "end": "2026-11-09T02:00:00+08:00"}
    with pytest.raises(ValidationError):
        TravelRequest.model_validate(bad)


def test_t01_non_positive_stay_seconds(scenarios):
    bad = _mutated(_base_request(scenarios))
    bad["candidates"] = [
        {"name": "A", "stay_seconds": 0}, {"name": "B", "stay_seconds": 100},
        {"name": "C", "stay_seconds": 100},
    ]
    with pytest.raises(ValidationError):
        TravelRequest.model_validate(bad)


@pytest.mark.parametrize("count", [2, 7])
def test_t01_candidate_count_out_of_scope(scenarios, count):
    bad = _mutated(_base_request(scenarios))
    bad["candidates"] = [{"name": f"P{i}", "stay_seconds": 600} for i in range(count)]
    with pytest.raises(ValidationError):
        TravelRequest.model_validate(bad)


def test_t01_duplicate_candidate_keys(scenarios):
    bad = _mutated(_base_request(scenarios))
    bad["candidates"] = [
        {"name": "A", "stay_seconds": 600}, {"name": "A", "stay_seconds": 600},
        {"name": "B", "stay_seconds": 600},
    ]
    with pytest.raises(ValidationError):
        TravelRequest.model_validate(bad)


def test_t01_candidate_exactly_one_key():
    with pytest.raises(ValidationError):
        Candidate(name="A", poi_id="p1", stay_seconds=600)
    with pytest.raises(ValidationError):
        Candidate(stay_seconds=600)


def test_t01_iana_offset_and_dst_validation(scenarios):
    """Real IANA rules: historical +09:00 for Asia/Shanghai, plus DST anomaly checks."""
    zone = resolve_zone("Asia/Shanghai")
    assert datetime(1990, 7, 1, 9, 0, tzinfo=zone).utcoffset() == timedelta(hours=9)
    assert datetime(2026, 11, 8, 9, 0, tzinfo=zone).utcoffset() == timedelta(hours=8)

    historical = _mutated(_base_request(scenarios))
    historical["date"] = "1990-07-01"
    historical["time_window"] = {
        "start": "1990-07-01T09:00:00+09:00", "end": "1990-07-01T18:00:00+09:00",
    }
    assert TravelRequest.model_validate(historical).date == "1990-07-01"

    wrong_offset = dict(historical)
    wrong_offset["time_window"] = {
        "start": "1990-07-01T09:00:00+08:00", "end": "1990-07-01T18:00:00+08:00",
    }
    with pytest.raises(ValidationError):
        TravelRequest.model_validate(wrong_offset)

    ny = resolve_zone("America/New_York")
    with pytest.raises(ValueError, match="ambiguous"):
        validate_local_datetime(datetime.fromisoformat("2026-11-01T01:30:00-04:00"), ny)
    with pytest.raises(ValueError, match="nonexistent"):
        validate_local_datetime(datetime.fromisoformat("2026-03-08T02:30:00-05:00"), ny)
    with pytest.raises(ValueError):
        resolve_zone("Not/AZone")


# --------------------------------------------------------------------------- #
# T-04 pure engine
# --------------------------------------------------------------------------- #

def _timeline_inputs():
    req = {
        "time_window": {"start": "2026-11-08T09:00:00+08:00",
                        "end": "2026-11-08T18:00:00+08:00"},
        "timezone": "Asia/Shanghai", "transport": "transit",
    }
    candidates = [{"name": "A", "stay_seconds": 3600, "key": "A"},
                  {"name": "B", "stay_seconds": 3600, "key": "B"},
                  {"name": "C", "stay_seconds": 3600, "key": "C"}]
    candidate_by_key = {c["key"]: c for c in candidates}
    legs = {
        leg_key(ORIGIN_KEY, "A"): {"duration_seconds": 600, "distance_meters": 1000, "source_ref": "r"},
        leg_key("A", "B"): {"duration_seconds": 600, "distance_meters": 1000, "source_ref": "r"},
        leg_key("B", "C"): {"duration_seconds": 600, "distance_meters": 1000, "source_ref": "r"},
    }
    hours = {"A": ["08:00", "21:00"], "B": ["08:00", "21:00"], "C": ["08:00", "21:00"]}
    poi = {k: {"provider_poi_id": f"p-{k}", "name": k, "evidence_refs": ["r"]} for k in "ABC"}
    return req, list("ABC"), legs, hours, candidate_by_key, poi


def test_t04_feasible_timeline():
    req, order, legs, hours, cbk, poi = _timeline_inputs()
    out = evaluate_timeline(request=req, order=order, leg_durations=legs, hours=hours,
                            candidate_by_key=cbk, poi_by_key=poi, prior_issues=[], degraded=False)
    assert out["quality_status"] == QualityStatus.VERIFIED_FEASIBLE.value
    assert all(v["arrival"] and v["departure"] for v in out["visits"])
    assert len(out["legs"]) == 3
    assert out["unknown_constraint_count"] == 0


def test_t04_unknown_duration_uses_null_not_zero():
    req, order, legs, hours, cbk, poi = _timeline_inputs()
    legs.pop(leg_key("A", "B"))
    out = evaluate_timeline(request=req, order=order, leg_durations=legs, hours=hours,
                            candidate_by_key=cbk, poi_by_key=poi, prior_issues=[], degraded=False)
    assert out["quality_status"] == QualityStatus.PARTIALLY_VERIFIED.value
    assert out["visits"][1]["arrival"] is None and out["visits"][1]["departure"] is None
    assert out["visits"][2]["arrival"] is None
    assert any(i["code"] == "ROUTE_UNKNOWN" for i in out["issues"])


def test_t04_time_window_exceeded():
    req, order, legs, hours, cbk, poi = _timeline_inputs()
    req["time_window"]["end"] = "2026-11-08T11:00:00+08:00"
    out = evaluate_timeline(request=req, order=order, leg_durations=legs, hours=hours,
                            candidate_by_key=cbk, poi_by_key=poi, prior_issues=[], degraded=False)
    assert out["quality_status"] == QualityStatus.INFEASIBLE.value
    assert any(i["code"] == "TIME_WINDOW_EXCEEDED" for i in out["issues"])


def test_t04_opening_window_violation():
    req, order, legs, hours, cbk, poi = _timeline_inputs()
    hours["B"] = ["16:00", "17:00"]
    out = evaluate_timeline(request=req, order=order, leg_durations=legs, hours=hours,
                            candidate_by_key=cbk, poi_by_key=poi, prior_issues=[], degraded=False)
    assert out["quality_status"] == QualityStatus.INFEASIBLE.value
    assert any(i["code"] == "OPENING_WINDOW_VIOLATION" for i in out["issues"])


def test_t04_unknown_hours_partial_verification():
    req, order, legs, hours, cbk, poi = _timeline_inputs()
    hours.pop("C")
    out = evaluate_timeline(request=req, order=order, leg_durations=legs, hours=hours,
                            candidate_by_key=cbk, poi_by_key=poi, prior_issues=[], degraded=False)
    assert out["quality_status"] == QualityStatus.PARTIALLY_VERIFIED.value
    assert any(i["code"] == "HOURS_UNKNOWN" for i in out["issues"])


def test_t04_degraded_tool_result_prevents_verified_claim():
    req, order, legs, hours, cbk, poi = _timeline_inputs()
    out = evaluate_timeline(request=req, order=order, leg_durations=legs, hours=hours,
                            candidate_by_key=cbk, poi_by_key=poi, prior_issues=[], degraded=True)
    assert out["quality_status"] == QualityStatus.PARTIALLY_VERIFIED.value


def test_greedy_reorder_records_change_and_is_heuristic():
    legs = {
        leg_key(ORIGIN_KEY, "A"): {"duration_seconds": 100},
        leg_key(ORIGIN_KEY, "B"): {"duration_seconds": 10},
        leg_key("A", "B"): {"duration_seconds": 10},
    }
    new_order, changed, reason = greedy_reorder(["A", "B"], legs)
    assert new_order == ["B", "A"] and changed
    assert "非全局最优" in reason
    same, unchanged, _ = greedy_reorder(["B", "A"], legs)
    assert same == ["B", "A"] and not unchanged


def test_parse_dt_requires_explicit_offset():
    with pytest.raises(ValueError):
        parse_dt("2026-11-08T09:00:00")


# --------------------------------------------------------------------------- #
# T-02 (custom scenarios with injected adapter)
# --------------------------------------------------------------------------- #

def test_unmatched_poi_has_no_coordinates(store, scenarios):
    s = scenarios["F13"]
    run = create_run(store, s["request"], scenario=s)
    got = drain_with(store, run["run_id"], ReplayAdapter(s))
    unmatched = [p for p in got["state"]["poi_records"] if p["match_status"] == "unmatched"]
    assert unmatched and all(p["coordinates"] is None for p in unmatched)
    assert got["status"] == "needs_input"


def test_cross_city_poi_rejected(store):
    data = load_fixtures()
    custom = resolve_scenario({
        "id": "CUSTOM-CROSSCITY", "category": "tool_error", "label": "跨城",
        "expect": {"status": "failed", "quality_status": "unverified", "issue_codes": ["CROSS_CITY_POI"]},
        "tools_overrides": {"poi": {"西湖": {
            "candidate": "西湖", "status": "matched", "provider_poi_id": "rp-x",
            "name": "西湖", "city": "上海", "lon": 121.4, "lat": 31.2,
        }}},
    }, data["defaults"])
    run = create_run(store, custom["request"], scenario=custom)
    got = drain_with(store, run["run_id"], ReplayAdapter(custom))
    assert got["status"] == "failed"
    assert any(i["code"] == "CROSS_CITY_POI" for i in got["state"]["issues"])
