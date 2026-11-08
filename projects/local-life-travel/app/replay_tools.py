"""Replay fixture loader and tool adapter.

No network, no subprocess, no model. Every tool result carries an explicit
ToolStatus so that empty/error/timeout can never be reported as success.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from .domain import (
    ORIGIN_KEY,
    TOOL_STATUS_TO_ISSUE,
    MatchStatus,
    ToolResult,
    ToolStatus,
    leg_key,
    utc_now,
)

FIXTURES_PATH = Path(__file__).resolve().parent.parent / "fixtures" / "scenarios.json"


def load_fixtures(path: str | Path | None = None) -> dict[str, Any]:
    with open(path or FIXTURES_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


def deep_merge(base: Any, override: Any) -> Any:
    if isinstance(base, dict) and isinstance(override, dict):
        out = copy.deepcopy(base)
        for key, value in override.items():
            out[key] = deep_merge(out[key], value) if key in out else copy.deepcopy(value)
        return out
    return copy.deepcopy(override)


def _apply_tool_override(tools: dict[str, Any], name: str, override: Any) -> None:
    """Merge one tool override with fixture-friendly semantics."""
    if name == "poi":
        if isinstance(override, dict) and "status" in override and "candidate" not in override:
            # Tool-level failure (e.g. format_error), replacing the whole lookup.
            tools["poi"] = copy.deepcopy(override)
        elif isinstance(override, dict):
            current = tools["poi"]
            if not isinstance(current, list):
                raise ValueError("poi override by candidate requires a default poi list")
            by_candidate = {entry["candidate"]: copy.deepcopy(entry) for entry in current}
            for key, value in override.items():
                by_candidate[key] = copy.deepcopy(value)
            tools["poi"] = list(by_candidate.values())
        else:
            tools["poi"] = copy.deepcopy(override)
    elif name == "hours":
        ov = copy.deepcopy(override)
        windows = ov.pop("windows", None)
        tools["hours"] = deep_merge(tools["hours"], ov)
        if windows is not None:
            # {} explicitly clears all windows; a non-empty dict is a partial merge.
            if not windows:
                tools["hours"]["windows"] = {}
            else:
                existing = tools["hours"].get("windows") or {}
                existing.update(windows)
                tools["hours"]["windows"] = existing
    else:
        tools[name] = copy.deepcopy(override)


def resolve_scenario(raw: dict[str, Any], defaults: dict[str, Any]) -> dict[str, Any]:
    """Expand one compact scenario entry into a full request + tool script."""
    request = copy.deepcopy(defaults["request"])
    request["candidates"] = copy.deepcopy(defaults.get("candidates", []))
    request = deep_merge(request, raw.get("request_overrides", {}))
    request["scenario_id"] = raw["id"]
    tools = copy.deepcopy(defaults["tools"])
    for name, override in raw.get("tools_overrides", {}).items():
        _apply_tool_override(tools, name, override)
    out = {
        "id": raw["id"],
        "category": raw["category"],
        "label": raw["label"],
        "expect": copy.deepcopy(raw["expect"]),
        "request": request,
        "tools": tools,
    }
    if "revision" in raw:
        out["revision"] = copy.deepcopy(raw["revision"])
        out["revision_expect"] = copy.deepcopy(raw["revision_expect"])
    return out


def resolve_all(path: str | Path | None = None) -> list[dict[str, Any]]:
    data = load_fixtures(path)
    return [resolve_scenario(s, data["defaults"]) for s in data["scenarios"]]


def scenario_index(path: str | Path | None = None) -> list[dict[str, Any]]:
    """Compact listing for the UI (no tool scripts)."""
    return [
        {
            "id": s["id"],
            "category": s["category"],
            "label": s["label"],
            "request": s["request"],
        }
        for s in resolve_all(path)
    ]


def get_scenario(scenario_id: str, path: str | Path | None = None) -> dict[str, Any] | None:
    for scenario in resolve_all(path):
        if scenario["id"] == scenario_id:
            return scenario
    return None


def _tool_error(status: str, ref: str, message: str | None = None) -> ToolResult:
    return ToolResult(
        status=ToolStatus(status),
        source_ref=ref,
        fetched_at=utc_now(),
        error_code=TOOL_STATUS_TO_ISSUE.get(status, "TOOL_UNAVAILABLE"),
        message=message or f"replay tool returned {status}",
    )


class ReplayAdapter:
    """Deterministic tool adapter backed entirely by one frozen scenario."""

    def __init__(self, scenario: dict[str, Any]):
        self.scenario = scenario
        self.scenario_id = scenario["id"]
        self.tools = scenario["tools"]

    def _ref(self, tool: str) -> str:
        return f"replay:{self.scenario_id}:{tool}"

    # -- T-02 ------------------------------------------------------------- #
    def poi_lookup(self, candidate_key: str, selected_poi_id: str | None = None) -> ToolResult:
        ref = f"{self._ref('poi')}:{candidate_key}"
        poi = self.tools["poi"]
        if isinstance(poi, dict):  # tool-level failure
            return _tool_error(poi.get("status", "format_error"), ref, poi.get("message"))

        entry = next((e for e in poi if e.get("candidate") == candidate_key), None)
        if entry is None:
            return ToolResult(
                status=ToolStatus.VALID, source_ref=ref, fetched_at=utc_now(),
                payload={"match_status": MatchStatus.UNMATCHED.value},
            )

        status = entry.get("status", "matched")
        if status == "unmatched":
            return ToolResult(
                status=ToolStatus.VALID, source_ref=ref, fetched_at=utc_now(),
                payload={"match_status": MatchStatus.UNMATCHED.value},
            )
        if status == "ambiguous":
            options = entry.get("options", [])
            if selected_poi_id:
                chosen = next((o for o in options if o.get("provider_poi_id") == selected_poi_id), None)
                if chosen:
                    return ToolResult(
                        status=ToolStatus.VALID, source_ref=ref, fetched_at=utc_now(),
                        payload={"match_status": MatchStatus.MATCHED.value, "poi": copy.deepcopy(chosen),
                                 "selected_by_user": True},
                    )
            return ToolResult(
                status=ToolStatus.VALID, source_ref=ref, fetched_at=utc_now(),
                payload={"match_status": MatchStatus.AMBIGUOUS.value, "options": copy.deepcopy(options)},
            )
        if status != "matched":
            return _tool_error(status, ref, entry.get("message"))

        poi_record = {k: copy.deepcopy(v) for k, v in entry.items()
                      if k not in ("candidate", "status", "options")}
        return ToolResult(
            status=ToolStatus.VALID, source_ref=ref, fetched_at=utc_now(),
            payload={"match_status": MatchStatus.MATCHED.value, "poi": poi_record},
        )

    # -- T-03 ------------------------------------------------------------- #
    def weather(self, target_date: str) -> ToolResult:
        ref = self._ref("weather")
        w = self.tools["weather"]
        if w.get("status") != "valid":
            status = w.get("status", "unavailable")
            if status == "unavailable":
                return ToolResult(
                    status=ToolStatus.UNAVAILABLE, source_ref=ref, fetched_at=utc_now(),
                    error_code="WEATHER_DATE_NOT_COVERED",
                    message=w.get("message") or "天气服务未覆盖目标日；不把当前天气当目标日预报",
                )
            return _tool_error(status, ref, w.get("message"))
        if w.get("forecast_date") != target_date:
            return ToolResult(
                status=ToolStatus.UNAVAILABLE, source_ref=ref, fetched_at=utc_now(),
                error_code="WEATHER_DATE_NOT_COVERED",
                message=f"回放预报日期 {w.get('forecast_date')} 不覆盖目标日 {target_date}；标为 unavailable",
            )
        return ToolResult(
            status=ToolStatus.VALID, source_ref=ref, fetched_at=utc_now(),
            payload={"forecast_date": target_date, "summary": w.get("summary", ""),
                     "valid_for": target_date},
        )

    def hours(self) -> ToolResult:
        ref = self._ref("hours")
        h = self.tools["hours"]
        if h.get("status") != "valid":
            return _tool_error(h.get("status", "unsupported"), ref, h.get("message"))
        return ToolResult(
            status=ToolStatus.VALID, source_ref=ref, fetched_at=utc_now(),
            payload={"windows": copy.deepcopy(h.get("windows", {}))},
        )

    def routes(self) -> ToolResult:
        ref = self._ref("routes")
        r = self.tools["routes"]
        if r.get("status") != "valid":
            return _tool_error(r.get("status", "timeout"), ref, r.get("message"))
        matrix: dict[str, dict[str, Any]] = {}
        for key, values in (r.get("matrix") or {}).items():
            a, b = key.split("|", 1)
            matrix[leg_key(ORIGIN_KEY if a == "__origin__" else a,
                           ORIGIN_KEY if b == "__origin__" else b)] = {
                "duration_seconds": int(values[0]),
                "distance_meters": int(values[1]),
                "source_ref": ref,
                "fetched_at": utc_now(),
            }
        return ToolResult(status=ToolStatus.VALID, source_ref=ref,
                          fetched_at=utc_now(), payload={"matrix": matrix})
