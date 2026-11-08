"""Deterministic six-stage engine for the replay travel judge.

Each call to advance() executes exactly ONE stage and persists immediately.
Stages are idempotent w.r.t. the saved `completed_stages` list, so a fresh
Store/Worker can resume after a restart without repeating completed work.
"""
from __future__ import annotations

import copy
import uuid
from datetime import datetime
from typing import Any, Callable

from .domain import (
    DEGRADING_ISSUES,
    DEFAULT_BUDGET,
    ORIGIN_KEY,
    REPLAY_PROVIDER,
    STAGES,
    TERMINAL_STATUSES,
    TOOL_STATUS_TO_ISSUE,
    TravelRequest,
    add_issue,
    canonical_hash,
    evaluate_timeline,
    greedy_reorder,
    next_stage,
    parse_dt,
    utc_now,
)
from .replay_tools import ReplayAdapter, get_scenario
from .store import Store, new_state


class BudgetExhausted(RuntimeError):
    pass


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def build_run(
    request: dict[str, Any],
    *,
    scenario: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
    budget_limits: dict[str, Any] | None = None,
    parent_run_id: str | None = None,
    revision: int = 1,
    versions: list[dict[str, Any]] | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Validate + construct a run dict. Pure: no I/O, no tool calls."""
    validated = TravelRequest.model_validate(request)
    normalized = validated.model_dump(mode="json")
    scenario_id = normalized["scenario_id"]
    if scenario is None:
        scenario = get_scenario(scenario_id)
    if scenario is None:
        raise ValueError(f"unknown replay scenario {scenario_id!r}")

    run_id = run_id or new_id("run")
    request_id = new_id("req")
    budget = dict(DEFAULT_BUDGET)
    if budget_limits:
        budget.update({k: v for k, v in budget_limits.items() if k in budget})
    state = new_state()
    state["order"] = [c["name"] or c["poi_id"] for c in normalized["candidates"]]

    return {
        "run_id": run_id,
        "request_id": request_id,
        "parent_run_id": parent_run_id,
        "request_hash": canonical_hash(normalized),
        "status": "queued",
        "current_stage": STAGES[0],
        "revision": revision,
        "versions": versions or [{"revision": revision, "run_id": run_id}],
        "budget": budget,
        "request": normalized,
        "state": state,
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "mode": "replay",
        "scenario_id": scenario_id,
        "idempotency_key": idempotency_key,
    }


def create_run(store: Store, request: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    """Convenience: build + persist + intake event (non-idempotent path)."""
    run = build_run(request, **kwargs)
    store.create_run(run)
    store.add_event(run["run_id"], "intake", "RUN_CREATED",
                    f"回放场景 {run['scenario_id']}；T-01 校验通过，未调用任何工具或模型")
    return run


def derive_revision(parent: dict[str, Any], revision_body: dict[str, Any]) -> dict[str, Any]:
    """Build a new request from a parent run + explicit user changes (U4/T-05)."""
    request = copy.deepcopy(parent["request"])
    removed = set(revision_body.get("remove_candidates") or [])
    request["candidates"] = [
        c for c in request["candidates"]
        if (c.get("name") or c.get("poi_id")) not in removed
    ]
    selected = dict(request.get("selected_poi_ids") or {})
    selected.update(revision_body.get("selected_poi_ids") or {})
    request["selected_poi_ids"] = selected
    if revision_body.get("time_window") is not None:
        request["time_window"] = revision_body["time_window"]
    if revision_body.get("transport") is not None:
        request["transport"] = revision_body["transport"]
    if revision_body.get("manual_facts"):
        request["manual_facts"] = list(request.get("manual_facts") or []) + list(revision_body["manual_facts"])
    return request


class _Context:
    """Budget accounting + normalized tool-result recording (T-03/T-05)."""

    def __init__(self, run: dict[str, Any], adapter: ReplayAdapter):
        self.run = run
        self.state = run["state"]
        self.budget = run["budget"]
        self.adapter = adapter

    def call(self, name: str, fn: Callable[[], Any]) -> dict[str, Any]:
        elapsed = (datetime.now().astimezone() - parse_dt(self.run["created_at"])).total_seconds()
        self.budget["elapsed_seconds"] = round(max(elapsed, 0.0), 3)
        if elapsed > self.budget["max_total_seconds"]:
            raise BudgetExhausted(
                f"total time budget exhausted ({elapsed:.3f}s > {self.budget['max_total_seconds']}s)"
            )
        if self.budget["tool_calls"] >= self.budget["max_tool_calls"]:
            raise BudgetExhausted(
                f"tool call budget exhausted ({self.budget['tool_calls']}/{self.budget['max_tool_calls']})"
            )
        result = fn()
        data = result.model_dump(mode="json") if hasattr(result, "model_dump") else dict(result)
        self.budget["tool_calls"] += 1
        data["tool"] = name
        self.state["tool_results"].append(data)
        return data

    def record_tool_issue(self, data: dict[str, Any], subject: str | None = None) -> None:
        status = data["status"]
        if status == "valid":
            return
        code = data.get("error_code") or TOOL_STATUS_TO_ISSUE.get(status, "TOOL_UNAVAILABLE")
        add_issue(self.state["issues"], code, "warning",
                  f"{data.get('tool')} 工具状态 {status}：{data.get('message') or '无有效结果'}（未按成功处理）",
                  subject=subject, evidence_refs=[data.get("source_ref", "")])


# --------------------------------------------------------------------------- #
# Stage handlers
# --------------------------------------------------------------------------- #

def _stage_validate(run: dict[str, Any], ctx: _Context, store: Store) -> None:
    TravelRequest.model_validate(run["request"])  # re-check persisted request
    # No tool/model calls by design (T-01).


def _stage_resolve_poi(run: dict[str, Any], ctx: _Context, store: Store) -> None:
    req, state = run["request"], run["state"]
    for key in list(state["order"]):
        selected = (req.get("selected_poi_ids") or {}).get(key)
        data = ctx.call("poi", lambda k=key, s=selected: ctx.adapter.poi_lookup(k, s))
        if data["status"] != "valid":
            ctx.record_tool_issue(data, subject=key)
            run["status"] = "failed"
            return
        payload = data["payload"] or {}
        match_status = payload.get("match_status")
        if match_status == "matched":
            poi = payload["poi"]
            lon, lat = float(poi["lon"]), float(poi["lat"])
            if not (-180.0 <= lon <= 180.0 and -90.0 <= lat <= 90.0):
                add_issue(state["issues"], "CROSS_CITY_POI", "blocker",
                          f"{key} 坐标超出合法范围", subject=key)
                run["status"] = "failed"
                return
            if poi.get("city") != req["city"]:
                add_issue(state["issues"], "CROSS_CITY_POI", "blocker",
                          f"{key} 匹配到 {poi.get('city')}，与请求城市 {req['city']} 不一致（跨城）",
                          subject=key, evidence_refs=[data.get("source_ref", "")])
                run["status"] = "failed"
                return
            record = {
                "internal_id": f"poi:{run['run_id']}:{key}",
                "provider": REPLAY_PROVIDER,
                "provider_poi_id": poi["provider_poi_id"],
                "name": poi["name"],
                "city": poi["city"],
                "coordinates": {"lon": lon, "lat": lat},
                "fetched_at": data["fetched_at"],
                "evidence_refs": [data.get("source_ref", "")],
                "match_status": "matched",
                "candidate_key": key,
            }
            state["poi_records"].append(record)
            state["poi_by_key"][key] = record
        elif match_status == "ambiguous":
            state["candidates_for_input"].append({
                "candidate": key,
                "options": payload.get("options", []),
                "source_ref": data.get("source_ref", ""),
            })
            add_issue(state["issues"], "AMBIGUOUS_POI", "warning",
                      f"{key} 存在多个合理候选，需用户通过 revisions 明确选择；未静默选择",
                      subject=key, evidence_refs=[data.get("source_ref", "")])
        else:  # unmatched
            add_issue(state["issues"], "POI_UNMATCHED", "warning",
                      f"{key} 无匹配POI；不生成坐标、不补占位景点", subject=key)
            state["poi_records"].append({
                "internal_id": f"poi:{run['run_id']}:{key}:unmatched",
                "provider": REPLAY_PROVIDER,
                "provider_poi_id": "",
                "name": key,
                "city": "",
                "coordinates": None,
                "fetched_at": data["fetched_at"],
                "evidence_refs": [data.get("source_ref", "")],
                "match_status": "unmatched",
                "candidate_key": key,
            })
            state["degraded"] = True

    if state["candidates_for_input"]:
        run["status"] = "needs_input"


def _stage_fetch_facts(run: dict[str, Any], ctx: _Context, store: Store) -> None:
    req, state = run["request"], run["state"]

    # Weather (T-03: date coverage, never current weather for a target day).
    weather = ctx.call("weather", lambda: ctx.adapter.weather(req["date"]))
    if weather["status"] == "unavailable" and weather.get("error_code") == "WEATHER_DATE_NOT_COVERED":
        add_issue(state["issues"], "WEATHER_DATE_NOT_COVERED", "warning",
                  weather.get("message") or "天气日期未覆盖，标为 unavailable", subject="weather",
                  evidence_refs=[weather.get("source_ref", "")])
        wvalue, wstatus = None, "unavailable"
    elif weather["status"] != "valid":
        ctx.record_tool_issue(weather, subject="weather")
        wvalue, wstatus = None, weather["status"]
    else:
        wvalue = (weather["payload"] or {}).get("summary")
        wstatus = "valid"
    state["facts"].append({
        "fact_id": f"fact:{run['run_id']}:weather", "subject_id": "weather", "field": "summary",
        "value": wvalue, "source_type": REPLAY_PROVIDER, "source_ref": weather.get("source_ref", ""),
        "fetched_at": weather["fetched_at"], "valid_for": req["date"], "provider_status": wstatus,
    })

    # Opening / appointment windows (T-03: unknown stays unknown; manual input is marked).
    hours = ctx.call("hours", ctx.adapter.hours)
    hours_status = hours["status"]
    state["hours"] = copy.deepcopy((hours.get("payload") or {}).get("windows", {})) if hours_status == "valid" else {}
    for mf in req.get("manual_facts") or []:
        if mf.get("field") != "opening_window":
            continue
        try:
            start, end = mf["value"].split("-", 1)
            state["hours"][mf["subject"]] = [start, end]
        except (KeyError, ValueError):
            continue
        state["facts"].append({
            "fact_id": f"fact:{run['run_id']}:manual:{mf['subject']}",
            "subject_id": mf["subject"], "field": "opening_window", "value": mf["value"],
            "source_type": "manual_input", "source_ref": "user-provided",
            "fetched_at": utc_now(), "valid_for": req["date"],
            "provider_status": "manual",
        })
    missing_hours = [k for k in state["order"] if k not in state["hours"]]
    if missing_hours:
        if hours_status != "valid":
            ctx.record_tool_issue(hours, subject="hours")
        for key in missing_hours:
            add_issue(state["issues"], "HOURS_UNKNOWN", "warning",
                      f"{key} 的开放/预约时段未知，保留 unknown（可人工补充并标来源）", subject=key)
    elif hours_status != "valid":
        add_issue(state["issues"], "HOURS_SUPPLIED_MANUALLY", "info",
                  "供应商不提供营业信息；用户人工补充了时段并已标记来源（source_type=manual_input）",
                  subject="hours", evidence_refs=[hours.get("source_ref", "")])

    # Route matrix (T-03: timeout/error is never an empty successful matrix).
    routes = ctx.call("routes", ctx.adapter.routes)
    if routes["status"] == "valid":
        matrix = (routes.get("payload") or {}).get("matrix", {})
        state["leg_durations"] = matrix
        for key, values in matrix.items():
            a, b = key.split("|", 1)
            state["legs"].append({
                "from_poi_id": a, "to_poi_id": b, "transport": req["transport"],
                "duration_seconds": values["duration_seconds"],
                "distance_meters": values["distance_meters"],
                "source_ref": values.get("source_ref", ""),
                "fetched_at": values.get("fetched_at", ""),
            })
    else:
        ctx.record_tool_issue(routes, subject="routes")
        state["leg_durations"] = {}


def _candidate_by_key(req: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out = {}
    for c in req["candidates"]:
        key = c.get("name") or c.get("poi_id")
        out[key] = {**c, "key": key}
    return out


def _evaluate(run: dict[str, Any]) -> dict[str, Any]:
    state = run["state"]
    degraded = state["degraded"] or any(
        issue["code"] in DEGRADING_ISSUES for issue in state["issues"]
    )
    outcome = evaluate_timeline(
        request=run["request"],
        order=state["order"],
        leg_durations=state["leg_durations"],
        hours=state["hours"],
        candidate_by_key=_candidate_by_key(run["request"]),
        poi_by_key=state["poi_by_key"],
        prior_issues=[],
        degraded=degraded,
    )
    # Constraint-derived issues are computed fresh each time; tool-level issues
    # stay in state["issues"] and are never lost or duplicated.
    result = {
        "run_id": run["run_id"],
        "revision": run["revision"],
        "quality_status": outcome["quality_status"],
        "visits": outcome["visits"],
        "legs": outcome["legs"],
        "issues": list(state["issues"]) + outcome["issues"],
        "changes": list(state["changes"]),
        "evidence_refs": outcome["evidence_refs"],
    }
    state["quality_status"] = outcome["quality_status"]
    state["result"] = result
    return result


def _stage_check_constraints(run: dict[str, Any], ctx: _Context, store: Store) -> None:
    _evaluate(run)


def _stage_adjust(run: dict[str, Any], ctx: _Context, store: Store) -> None:
    state, budget = run["state"], run["budget"]
    # Only a hard infeasibility can be addressed by reordering. A
    # partially_verified result is caused by unknown facts, not by ordering.
    if state["quality_status"] != "infeasible":
        return
    if budget["adjustment_rounds"] >= budget["max_adjustment_rounds"]:
        add_issue(state["issues"], "BUDGET_EXHAUSTED", "info",
                  "调整轮次已达上限，不再重排", subject="__adjust__")
        return
    old_order = list(state["order"])
    new_order, changed, reason = greedy_reorder(old_order, state["leg_durations"])
    budget["adjustment_rounds"] += 1
    if not changed:
        return
    state["order"] = new_order
    state["changes"].append({
        "kind": "reorder",
        "detail": f"{' → '.join(old_order)} 重排为 {' → '.join(new_order)}",
        "reason": reason,
    })
    _evaluate(run)  # T-04: re-run the full constraint check after any change


def _stage_finalize(run: dict[str, Any], ctx: _Context, store: Store) -> None:
    if run["status"] not in TERMINAL_STATUSES:
        run["status"] = "completed"
    store.add_event(run["run_id"], "finalize", "FINALIZED",
                    f"处理结束；quality_status={run['state']['quality_status']}；"
                    "completed 仅表示处理结束，不表示行程可行")


_HANDLERS = {
    "validate": _stage_validate,
    "resolve_poi": _stage_resolve_poi,
    "fetch_facts": _stage_fetch_facts,
    "check_constraints": _stage_check_constraints,
    "adjust": _stage_adjust,
    "finalize": _stage_finalize,
}


def advance(store: Store, run_id: str, adapter: ReplayAdapter | None = None) -> dict[str, Any]:
    """Execute exactly one stage of one run; persist immediately."""
    run = store.get_run(run_id)
    if run is None:
        raise KeyError(run_id)
    if run["status"] in TERMINAL_STATUSES:
        return run
    if run["status"] == "queued":
        run["status"] = "running"

    stage = run["current_stage"]
    if stage in run["state"]["completed_stages"]:
        stage = next_stage(stage) or stage
        run["current_stage"] = stage
    if adapter is None:
        scenario = get_scenario(run["scenario_id"])
        if scenario is None:
            raise ValueError(f"unknown replay scenario {run['scenario_id']!r}")
        adapter = ReplayAdapter(scenario)
    ctx = _Context(run, adapter)

    try:
        _HANDLERS[stage](run, ctx, store)
    except BudgetExhausted as exc:
        run["status"] = "failed"
        run["budget"]["status"] = "exhausted"
        add_issue(run["state"]["issues"], "BUDGET_EXHAUSTED", "blocker", str(exc))
        store.add_event(run_id, stage, "BUDGET_EXHAUSTED", str(exc))
        if run["state"]["result"] is None:
            _evaluate(run)
        store.save_run(run)
        return run

    run["state"]["completed_stages"].append(stage)
    run["state"]["stage_log"].append(stage)
    run["state"]["executed_stages"] += 1
    store.add_event(run_id, stage, "STAGE_COMPLETED",
                    f"{stage} 完成；status={run['status']}；工具调用 {run['budget']['tool_calls']}")
    nxt = next_stage(stage)
    run["current_stage"] = nxt or stage
    store.save_run(run)
    return run
