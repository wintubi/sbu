"""Synchronous LIVE execution path.

This is deliberately separate from the replay stage machine: a live run must
surface a provider failure immediately and must not look like a completed
replay. The same domain contracts (ToolResult, evaluate_timeline) are reused.
"""
from __future__ import annotations

import copy
import uuid
from typing import Any, Callable

from .amap_tools import normalize_city
from .domain import (
    DEFAULT_BUDGET,
    ORIGIN_KEY,
    TOOL_STATUS_TO_ISSUE,
    LiveTravelRequest,
    ToolResult,
    ToolStatus,
    add_issue,
    canonical_hash,
    evaluate_timeline,
    utc_now,
)
from .store import Store, new_state
from .runtime import BudgetExhausted, LiveRuntime


LIVE_MAX_TOOL_CALLS = 40  # live counts real HTTP requests, including matrix/hours details


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def build_live_run(request: LiveTravelRequest, *, idempotency_key: str | None = None,
                   parent_run_id: str | None = None, revision: int = 1,
                   versions: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    normalized = request.model_dump(mode="json")
    run_id = _new_id("run")
    state = new_state()
    state["order"] = [c["name"] or c["poi_id"] for c in normalized["candidates"]]
    lineage = list(versions or [{"revision": 1, "run_id": run_id}])
    if lineage[-1].get("run_id") == "pending" or lineage[-1].get("revision") != revision:
        lineage = [item for item in lineage if item.get("revision") != revision]
        lineage.append({"revision": revision, "run_id": run_id})
    budget = copy.deepcopy(DEFAULT_BUDGET)
    budget["max_tool_calls"] = LIVE_MAX_TOOL_CALLS
    return {
        "run_id": run_id,
        "request_id": _new_id("req"),
        "parent_run_id": parent_run_id,
        "request_hash": canonical_hash(normalized),
        "status": "queued",
        "current_stage": "live",
        "revision": revision,
        "versions": lineage,
        "budget": budget,
        "request": normalized,
        "state": state,
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "mode": "live",
        "scenario_id": "live",
        "idempotency_key": idempotency_key,
    }


def _record(run: dict[str, Any], tool: str, result: ToolResult) -> None:
    # 工具/子证据交付不消费预算；只有发送前reserve成功才记HTTP尝试。
    data = result.model_dump(mode="json")
    data["tool"] = tool
    run["state"]["tool_results"].append(data)


def _record_issue(run: dict[str, Any], result: ToolResult, subject: str) -> None:
    if result.status == ToolStatus.VALID:
        return
    code = result.error_code or TOOL_STATUS_TO_ISSUE.get(result.status.value, "TOOL_UNAVAILABLE")
    add_issue(run["state"]["issues"], code, "warning",
              f"{subject} 工具状态 {result.status.value}：{result.message or '无有效结果'}",
              subject=subject, evidence_refs=[result.source_ref])
    run["state"]["degraded"] = True


def execute_live(run: dict[str, Any], adapter: Any, runtime: LiveRuntime) -> dict[str, Any]:
    request = run["request"]
    state = run["state"]
    order = state["order"]
    run["status"] = "running"
    run["budget"]["status"] = "running"

    def invoke(tool: str, function, *args):
        runtime.check()
        result = function(*args)
        runtime.check()
        _record(run, tool, result)
        return result

    origin = invoke("origin", adapter.resolve_origin, request["origin"])
    if origin.status != ToolStatus.VALID:
        _record_issue(run, origin, "origin")
        run["status"] = "failed"
        run["budget"]["status"] = "failed"
        return run
    origin_poi = (origin.payload or {}).get("poi") or {}
    if origin_poi.get("city") and normalize_city(str(origin_poi["city"])) != normalize_city(request["city"]):
        add_issue(state["issues"], "ORIGIN_OUTSIDE_CITY", "blocker",
                  f"出发地 {request['origin']} 匹配到 {origin_poi['city']}，与请求城市 {request['city']} 不一致",
                  subject="origin", evidence_refs=[origin.source_ref])
        run["status"] = "failed"
        run["budget"]["status"] = "failed"
        return run

    for key in order:
        selected = (request.get("selected_poi_ids") or {}).get(key)
        result = invoke("poi", adapter.poi_lookup, key, selected)
        if result.status != ToolStatus.VALID:
            _record_issue(run, result, key)
            run["status"] = "failed"
            break
        payload = result.payload or {}
        match_status = payload.get("match_status")
        if match_status == "matched":
            poi = payload["poi"]
            point = poi.get("coordinates") or {}
            lon, lat = float(point.get("lon")), float(point.get("lat"))
            if not (-180 <= lon <= 180 and -90 <= lat <= 90):
                add_issue(state["issues"], "CROSS_CITY_POI", "blocker",
                          f"{key} 坐标超出合法范围", subject=key)
                run["status"] = "failed"
                break
            if normalize_city(str(poi.get("city", ""))) != normalize_city(request["city"]):
                add_issue(state["issues"], "CROSS_CITY_POI", "blocker",
                          f"{key} 匹配到 {poi.get('city')}，与请求城市 {request['city']} 不一致",
                          subject=key, evidence_refs=[result.source_ref])
                run["status"] = "failed"
                break
            record = {
                "internal_id": f"poi:{run['run_id']}:{key}",
                "provider": "amap-web-service",
                "provider_poi_id": poi["provider_poi_id"],
                "name": poi["name"],
                "city": poi.get("city", ""),
                "coordinates": {"lon": lon, "lat": lat},
                "fetched_at": result.fetched_at,
                "evidence_refs": [result.source_ref],
                "match_status": "matched",
                "candidate_key": key,
            }
            state["poi_records"].append(record)
            state["poi_by_key"][key] = record
        elif match_status == "ambiguous":
            state["candidates_for_input"].append({
                "candidate": key, "options": payload.get("options", []),
                "source_ref": result.source_ref,
            })
            add_issue(state["issues"], "AMBIGUOUS_POI", "warning",
                      f"{key} 存在多个合理候选，需用户通过 revisions 明确选择；未静默选择",
                      subject=key, evidence_refs=[result.source_ref])
        else:
            add_issue(state["issues"], "POI_UNMATCHED", "warning",
                      f"{key} 无匹配POI；不生成坐标、不补占位景点", subject=key)
            state["degraded"] = True

    if run["status"] == "failed":
        run["budget"]["status"] = "failed"
        return run
    if state["candidates_for_input"]:
        run["status"] = "needs_input"
    weather = invoke("weather", adapter.weather, request["date"])
    if weather.status == ToolStatus.VALID:
        state["facts"].append({
            "fact_id": f"fact:{run['run_id']}:weather", "subject_id": "weather",
            "field": "summary", "value": (weather.payload or {}).get("summary"),
            "source_type": "amap-web-service", "source_ref": weather.source_ref,
            "fetched_at": weather.fetched_at, "valid_for": request["date"],
            "provider_status": "valid",
        })
    else:
        _record_issue(run, weather, "weather")
        add_issue(state["issues"], weather.error_code or "TOOL_UNAVAILABLE", "warning",
                  "天气不可用；不使用当前天气代替目标日预报", subject="weather",
                  evidence_refs=[weather.source_ref])
        state["degraded"] = True

    hours = invoke("hours", adapter.hours)
    if hours.status == ToolStatus.VALID:
        state["hours"] = dict((hours.payload or {}).get("windows") or {})
    else:
        _record_issue(run, hours, "hours")
        for key in order:
            if key not in state["hours"]:
                add_issue(state["issues"], "HOURS_UNKNOWN", "warning",
                          f"{key} 的开放/预约时段未知，保留 unknown", subject=key)

    for manual in request.get("manual_facts") or []:
        if manual.get("field") != "opening_window":
            continue
        try:
            start, end = str(manual["value"]).split("-", 1)
        except (KeyError, ValueError):
            add_issue(state["issues"], "MANUAL_FACT_INVALID", "warning",
                      "人工营业时间格式无效；保留 unknown", subject=manual.get("subject"))
            continue
        subject = manual.get("subject")
        if not subject:
            continue
        state["hours"][subject] = [start.strip(), end.strip()]
        state["facts"].append({
            "fact_id": f"fact:{run['run_id']}:manual:{subject}",
            "subject_id": subject, "field": "opening_window",
            "value": manual["value"], "source_type": "manual_input",
            "source_ref": "user-provided", "fetched_at": utc_now(),
            "valid_for": request["date"], "provider_status": "manual",
        })
        state["issues"] = [issue for issue in state["issues"] if not (
            issue["code"] == "HOURS_UNKNOWN" and issue.get("subject") == subject
        )]

    matched_keys = [key for key in order if key in state["poi_by_key"]]
    pairs = [(ORIGIN_KEY, key) for key in matched_keys]
    pairs += [(a, b) for index, a in enumerate(matched_keys) for b in matched_keys[index + 1:]]
    routes = invoke("routes", adapter.matrix, pairs)
    if routes.status == ToolStatus.VALID:
        state["leg_durations"] = dict((routes.payload or {}).get("matrix") or {})
        for key, values in state["leg_durations"].items():
            a, b = key.split("|", 1)
            state["legs"].append({
                "from_poi_id": a, "to_poi_id": b, "transport": request["transport"],
                "duration_seconds": values["duration_seconds"],
                "distance_meters": values["distance_meters"],
                "source_ref": values.get("source_ref", ""),
                "fetched_at": values.get("fetched_at", ""),
            })
    else:
        _record_issue(run, routes, "routes")
        state["leg_durations"] = {}

    candidate_by_key = {}
    for candidate in request["candidates"]:
        key = candidate["name"] or candidate["poi_id"]
        candidate_by_key[key] = {**candidate, "key": key}
    outcome = evaluate_timeline(
        request=request, order=order, leg_durations=state["leg_durations"],
        hours=state["hours"], candidate_by_key=candidate_by_key,
        poi_by_key=state["poi_by_key"], prior_issues=list(state["issues"]),
        degraded=state["degraded"],
    )
    state["issues"] = outcome["issues"]
    state["quality_status"] = outcome["quality_status"]
    state["result"] = {
        "run_id": run["run_id"], "revision": run["revision"],
        "quality_status": outcome["quality_status"],
        "visits": outcome["visits"], "legs": outcome["legs"],
        "issues": outcome["issues"], "changes": [],
        "evidence_refs": outcome["evidence_refs"],
    }
    if run["status"] not in ("needs_input", "failed"):
        run["status"] = "completed"
    run["budget"]["status"] = "ok" if run["status"] == "completed" else run["status"]
    return run


def create_live_run(store: Store, request: LiveTravelRequest,
                    adapter_factory: Callable[[str, str], Any], key: str | None,
                    *, parent_run_id: str | None = None, revision: int = 1,
                    versions: list[dict[str, Any]] | None = None) -> tuple[dict[str, Any], bool]:
    run = build_live_run(request, idempotency_key=key, parent_run_id=parent_run_id,
                         revision=revision, versions=versions)
    if key:
        outcome, prior = store.create_run_atomic(run, key, run["request_hash"])
        if outcome == "existing":
            existing = store.get_run(prior["run_id"])
            if existing is None:
                raise RuntimeError("idempotency row exists but run is missing")
            if existing["request_hash"] != run["request_hash"]:
                raise RuntimeError("IDEMPOTENCY_CONFLICT")
            return existing, False
    else:
        store.create_run(run)
    runtime = LiveRuntime(run["budget"], on_evidence=lambda tool, result: _record(run, tool, result))
    adapter = None
    try:
        runtime.check()
        adapter = adapter_factory(request.city, request.transport)
        if not callable(getattr(adapter, "bind_runtime", None)) or not callable(getattr(adapter, "close", None)):
            raise TypeError("LIVE adapter requires bind_runtime and close")
        adapter.bind_runtime(runtime)
        runtime.check()
        execute_live(run, adapter, runtime)
    except BudgetExhausted as exc:
        run["status"] = "failed"
        run["budget"]["status"] = "exhausted"
        run["budget"]["exhaustion_reason"] = exc.reason
        run["state"]["result"] = None
        run["state"]["quality_status"] = "unverified"
        add_issue(run["state"]["issues"], "BUDGET_EXHAUSTED", "blocker", str(exc))
    except Exception as exc:  # noqa: BLE001 - a live failure must be persisted
        run["status"] = "failed"
        run["budget"]["status"] = "failed"
        run["state"]["result"] = None
        run["state"]["quality_status"] = "unverified"
        add_issue(run["state"]["issues"], "STAGE_EXECUTION_ERROR", "blocker",
                  f"真实渠道执行异常：{type(exc).__name__}")
    finally:
        close = getattr(adapter, "close", None)
        if callable(close):
            try:
                close()
            except Exception as exc:
                add_issue(run["state"]["issues"], "RESOURCE_CLEANUP_FAILED", "warning",
                          f"资源清理尝试失败：{type(exc).__name__}")
    store.save_run(run)
    store.add_event(run["run_id"], "live", "LIVE_FINISHED",
                    f"真实渠道执行结束；status={run['status']}；quality={run['state']['quality_status']}")
    return run, True
