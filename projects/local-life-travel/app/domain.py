"""Domain contracts and pure deterministic functions for the replay travel judge.

This module has NO I/O: no network, no database, no model calls. Everything here is
reproducible from its inputs, which is what makes the T-01..T-06 checks testable.

All persisted state is JSON (plain dicts). Pydantic models are used at the API
boundary and by the pure helpers; engine/worker deliberately operate on dicts so
that a SQLite round-trip never changes semantics.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone as dt_timezone
from enum import Enum
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

ORIGIN_KEY = "__origin__"
REPLAY_PROVIDER = "replay-fixture"
REPLAY_NOTICE = (
    "REPLAY / 本地回放演示：本运行只使用仓库内固定 fixture，不连接真实地图、天气或模型服务；"
    "POI、路线与天气结果不表示地点已经由真实供应商核验。"
)

# IANA timezones are resolved through the standard-library zoneinfo module.
# tzdata is installed on this host; no extra dependency was added.
TRANSPORTS = ("walking", "driving", "transit", "bicycling")
MIN_CANDIDATES = 3
MAX_CANDIDATES = 6

DEFAULT_BUDGET = {
    "max_tool_calls": 10,
    "max_adjustment_rounds": 2,
    "max_total_seconds": 90,
    "max_model_calls": 0,
    "tool_calls": 0,
    "adjustment_rounds": 0,
    "model_calls": 0,
    "elapsed_seconds": 0.0,
    "status": "ok",
}

STAGES = (
    "validate",
    "resolve_poi",
    "fetch_facts",
    "check_constraints",
    "adjust",
    "finalize",
)

TERMINAL_STATUSES = ("completed", "failed", "cancelled", "needs_input")


class RunStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    NEEDS_INPUT = "needs_input"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class QualityStatus(str, Enum):
    VERIFIED_FEASIBLE = "verified_feasible"
    INFEASIBLE = "infeasible"
    PARTIALLY_VERIFIED = "partially_verified"
    UNVERIFIED = "unverified"


class ToolStatus(str, Enum):
    VALID = "valid"
    EMPTY = "empty"
    TIMEOUT = "timeout"
    PROVIDER_ERROR = "provider_error"
    FORMAT_ERROR = "format_error"
    UNSUPPORTED = "unsupported"
    UNAVAILABLE = "unavailable"


class MatchStatus(str, Enum):
    MATCHED = "matched"
    AMBIGUOUS = "ambiguous"
    UNMATCHED = "unmatched"


# Issue codes (see specs.md).
ISSUE_CODES = (
    "AMBIGUOUS_POI", "POI_UNMATCHED", "CROSS_CITY_POI",
    "TOOL_FORMAT_ERROR", "TOOL_TIMEOUT", "TOOL_PROVIDER_ERROR",
    "TOOL_EMPTY", "TOOL_UNSUPPORTED", "TOOL_UNAVAILABLE", "STAGE_EXECUTION_ERROR",
    "WEATHER_DATE_NOT_COVERED", "HOURS_UNKNOWN", "ROUTE_UNKNOWN", "TIME_WINDOW_EXCEEDED",
    "OPENING_WINDOW_VIOLATION", "BUDGET_EXHAUSTED", "RESOURCE_CLEANUP_FAILED",
)
DEGRADING_ISSUES = frozenset(
    c for c in ISSUE_CODES if c.startswith("TOOL_") or c in ("WEATHER_DATE_NOT_COVERED", "HOURS_UNKNOWN", "ROUTE_UNKNOWN")
)

TOOL_STATUS_TO_ISSUE = {
    "format_error": "TOOL_FORMAT_ERROR",
    "timeout": "TOOL_TIMEOUT",
    "provider_error": "TOOL_PROVIDER_ERROR",
    "empty": "TOOL_EMPTY",
    "unsupported": "TOOL_UNSUPPORTED",
    "unavailable": "TOOL_UNAVAILABLE",
}


# --------------------------------------------------------------------------- #
# Time helpers
# --------------------------------------------------------------------------- #

def utc_now() -> str:
    """RFC3339 UTC timestamp with explicit offset."""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def parse_dt(value: str) -> datetime:
    """Parse an RFC3339 string; requires an explicit offset."""
    if not isinstance(value, str):
        raise ValueError("datetime must be a string")
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("datetime must carry an explicit UTC offset")
    return dt


def to_rfc3339(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def offset_minutes(dt: datetime) -> int:
    off = dt.utcoffset()
    return int(off.total_seconds() // 60) if off else 0


def resolve_zone(name: str) -> ZoneInfo:
    """Resolve an IANA timezone name; reject unknown labels explicitly.

    Uses the standard library (tzdata present on this host). No fixed-offset
    shortcut: historical DST rules for e.g. Asia/Shanghai are honoured.
    """
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, KeyError) as exc:
        raise ValueError(f"unsupported IANA timezone {name!r}") from exc


def validate_local_datetime(dt: datetime, zone: ZoneInfo) -> None:
    """Check the explicit offset against IANA rules and reject DST anomalies.

    - ambiguous local time (DST overlap): fold=0 / fold=1 give different offsets
    - nonexistent local time (DST gap): UTC round-trip does not return the same wall time
    - wrong explicit offset for that local date in that zone
    """
    naive = dt.replace(tzinfo=None)
    fold0 = naive.replace(tzinfo=zone, fold=0)
    fold1 = naive.replace(tzinfo=zone, fold=1)
    # Check the gap FIRST: a nonexistent local time also has differing fold
    # offsets, so an ambiguity check alone would misclassify it.
    roundtrip = fold0.astimezone(dt_timezone.utc).astimezone(zone).replace(tzinfo=None)
    if roundtrip != naive:
        raise ValueError("nonexistent local time (DST gap)")
    if fold0.utcoffset() != fold1.utcoffset():
        raise ValueError("ambiguous local time (DST overlap); specify an unambiguous offset")
    if fold0.utcoffset() != dt.utcoffset():
        raise ValueError("explicit UTC offset does not match IANA zone rules for this local date")


def minutes_of_day(value: str) -> int:
    """'HH:MM' -> minutes since local midnight."""
    hh, mm = value.split(":")
    h, m = int(hh), int(mm)
    if not (0 <= h <= 23 and 0 <= m <= 59):
        raise ValueError("HH:MM out of range")
    return h * 60 + m


def leg_key(a: str, b: str) -> str:
    """Order-independent key for a route leg (symmetric travel times)."""
    return "|".join(sorted((a, b)))


def canonical_hash(payload: Any) -> str:
    """Stable hash of a JSON-serialisable payload for idempotency keys."""
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# Request contracts (T-01)
# --------------------------------------------------------------------------- #

class TimeWindow(BaseModel):
    start: str = Field(description="RFC3339 with offset")
    end: str = Field(description="RFC3339 with offset")

    @field_validator("start", "end")
    @classmethod
    def _rfc3339(cls, v: str) -> str:
        parse_dt(v)
        return v

    @model_validator(mode="after")
    def _consistent(self) -> "TimeWindow":
        s, e = parse_dt(self.start), parse_dt(self.end)
        if e <= s:
            raise ValueError("time_window.end must be after time_window.start")
        if (e - s).total_seconds() > 86400:
            raise ValueError("time_window must not exceed 24h (single-day scope)")
        if offset_minutes(s) != offset_minutes(e):
            raise ValueError("time_window.start and end must use the same offset")
        return self


class Candidate(BaseModel):
    name: str | None = None
    poi_id: str | None = None
    stay_seconds: int = Field(gt=0)
    optional_time_window: dict[str, str] | None = None

    @model_validator(mode="after")
    def _exactly_one_key(self) -> "Candidate":
        if bool(self.name) == bool(self.poi_id):
            raise ValueError("exactly one of name or poi_id must be provided")
        if self.optional_time_window:
            minutes_of_day(self.optional_time_window["start"])
            minutes_of_day(self.optional_time_window["end"])
        return self

    @property
    def key(self) -> str:
        return self.name or self.poi_id or ""


class ManualFact(BaseModel):
    """User-supplied opening/appointment info; recorded with source_type=manual_input."""
    subject: str
    field: str
    value: str
    reason: str = ""


class TravelRequest(BaseModel):
    mode: str = "replay"
    scenario_id: str = Field(min_length=1)
    city: str = Field(min_length=1)
    date: str
    timezone: str
    origin: str = Field(min_length=1)
    time_window: TimeWindow
    transport: Literal["walking", "driving", "transit", "bicycling"]
    candidates: list[Candidate] = Field(min_length=MIN_CANDIDATES, max_length=MAX_CANDIDATES)
    preferences: dict[str, Any] = Field(default_factory=dict)
    manual_facts: list[ManualFact] = Field(default_factory=list)
    selected_poi_ids: dict[str, str] = Field(default_factory=dict)

    @field_validator("date")
    @classmethod
    def _date(cls, v: str) -> str:
        datetime.strptime(v, "%Y-%m-%d")
        return v

    @model_validator(mode="after")
    def _cross_field(self) -> "TravelRequest":
        zone = resolve_zone(self.timezone)
        s, e = parse_dt(self.time_window.start), parse_dt(self.time_window.end)
        validate_local_datetime(s, zone)
        validate_local_datetime(e, zone)
        if s.astimezone(zone).date().isoformat() != self.date or e.astimezone(zone).date().isoformat() != self.date:
            raise ValueError("time_window must lie on request.date in the IANA timezone (single-day scope)")
        keys = [c.key for c in self.candidates]
        if len(set(keys)) != len(keys):
            raise ValueError("candidate keys must be unique")
        return self


class LiveTravelRequest(TravelRequest):
    """Same validated shape as replay, but no fixture scenario is selected."""

    mode: Literal["live"] = "live"
    scenario_id: str = "live"


class RevisionRequest(BaseModel):
    selected_poi_ids: dict[str, str] = Field(default_factory=dict)
    remove_candidates: list[str] = Field(default_factory=list)
    time_window: TimeWindow | None = None
    transport: str | None = None
    manual_facts: list[ManualFact] = Field(default_factory=list)
    reason: str = ""


# --------------------------------------------------------------------------- #
# Output contracts (dicts are stored; these models document the shape)
# --------------------------------------------------------------------------- #

class ToolResult(BaseModel):
    status: ToolStatus
    source_ref: str
    fetched_at: str
    payload: Any = None
    error_code: str | None = None
    message: str | None = None


class POIRecord(BaseModel):
    internal_id: str
    provider: str = REPLAY_PROVIDER
    provider_poi_id: str
    name: str
    city: str
    coordinates: dict[str, float]
    fetched_at: str
    evidence_refs: list[str] = Field(default_factory=list)
    match_status: str


class Fact(BaseModel):
    fact_id: str
    subject_id: str
    field: str
    value: Any = None
    source_type: str
    source_ref: str
    fetched_at: str
    valid_for: str | None = None
    provider_status: str = "valid"


class RouteLeg(BaseModel):
    from_poi_id: str
    to_poi_id: str
    transport: str
    duration_seconds: int
    distance_meters: int
    source_ref: str
    fetched_at: str


class Issue(BaseModel):
    code: str
    severity: str
    message: str
    subject: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)


class Change(BaseModel):
    kind: str
    detail: str
    reason: str


class Visit(BaseModel):
    poi_id: str
    name: str
    arrival: str | None
    departure: str | None
    stay_seconds: int


class ItineraryResult(BaseModel):
    run_id: str
    revision: int
    quality_status: str
    visits: list[dict[str, Any]] = Field(default_factory=list)
    legs: list[dict[str, Any]] = Field(default_factory=list)
    issues: list[dict[str, Any]] = Field(default_factory=list)
    changes: list[dict[str, Any]] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)


class ErrorResponse(BaseModel):
    code: str
    message: str
    retryable: bool = False
    run_id: str | None = None
    field_errors: list[dict[str, str]] | None = None


def make_issue(code: str, severity: str, message: str, subject: str | None = None,
               evidence_refs: list[str] | None = None) -> dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "message": message,
        "subject": subject,
        "evidence_refs": evidence_refs or [],
    }


def add_issue(issues: list[dict[str, Any]], code: str, severity: str, message: str,
              subject: str | None = None, evidence_refs: list[str] | None = None) -> None:
    """Dedupe by (code, subject) so one missing route does not flood the report."""
    for existing in issues:
        if existing["code"] == code and existing["subject"] == subject:
            return
    issues.append(make_issue(code, severity, message, subject, evidence_refs))


# --------------------------------------------------------------------------- #
# Pure deterministic constraint engine (T-04)
# --------------------------------------------------------------------------- #

def greedy_reorder(order: list[str], leg_durations: dict[str, dict[str, Any]]) -> tuple[list[str], bool, str]:
    """One heuristic pass: repeatedly take the nearest unvisited place.

    Not a global optimum. Returns (new_order, changed, reason).
    """
    remaining = list(order)
    result: list[str] = []
    current = ORIGIN_KEY
    while remaining:
        def cost(key: str) -> tuple[float, str]:
            leg = leg_durations.get(leg_key(current, key))
            dur = leg.get("duration_seconds") if leg else None
            return (float(dur) if dur is not None else float("inf"), key)

        best = min(remaining, key=cost)
        result.append(best)
        remaining.remove(best)
        current = best
    changed = result != order
    reason = (
        "贪心重排：每步选择距当前位置耗时最短的未访问地点（启发式，非全局最优）"
        if changed else "贪心重排未改变顺序"
    )
    return result, changed, reason


def _window_bounds(candidate: dict[str, Any], hours: dict[str, Any]) -> tuple[int | None, int | None, str]:
    """Return (start_min, end_min, source_label); None bounds => unknown."""
    opt = candidate.get("optional_time_window")
    if opt:
        return minutes_of_day(opt["start"]), minutes_of_day(opt["end"]), "用户指定时段"
    win = hours.get(candidate["key"])
    if isinstance(win, (list, tuple)) and len(win) == 2:
        return minutes_of_day(win[0]), minutes_of_day(win[1]), "replay 开放时段"
    return None, None, "unknown"


def evaluate_timeline(
    *,
    request: dict[str, Any],
    order: list[str],
    leg_durations: dict[str, dict[str, Any]],
    hours: dict[str, Any],
    candidate_by_key: dict[str, dict[str, Any]],
    poi_by_key: dict[str, dict[str, Any]],
    prior_issues: list[dict[str, Any]],
    degraded: bool,
) -> dict[str, Any]:
    """Compute visits/legs/issues/quality_status from known facts only.

    Unknown durations produce null arrival/departure -- never 0, empty string,
    or an invented value (SPEC section 5 / T-04).
    """
    issues = [dict(i) for i in prior_issues]
    zone = resolve_zone(request["timezone"])
    start = parse_dt(request["time_window"]["start"])
    end = parse_dt(request["time_window"]["end"])
    current: datetime | None = start
    previous = ORIGIN_KEY
    visits: list[dict[str, Any]] = []
    legs_out: list[dict[str, Any]] = []
    evidence: list[str] = []
    unknown_count = 0
    hard_violation = False

    for key in order:
        cand = candidate_by_key.get(key, {})
        poi = poi_by_key.get(key)
        stay = int(cand.get("stay_seconds", 0))
        leg = leg_durations.get(leg_key(previous, key))
        leg_ok = bool(leg and leg.get("duration_seconds") is not None)

        if not leg_ok or current is None:
            unknown_count += 1
            reason = (f"路线耗时未知：{previous} → {key}" if not leg_ok
                      else f"前序路线耗时未知，{key} 的到达/离开时间无法继续推算")
            add_issue(issues, "ROUTE_UNKNOWN", "warning",
                      f"{reason}；不使用 0 或猜测值", subject=key)
            arrival = departure = None
            current = None
        else:
            dur = int(leg["duration_seconds"])
            arrival_dt = current + timedelta(seconds=dur)
            departure_dt = arrival_dt + timedelta(seconds=stay)
            arrival = to_rfc3339(arrival_dt)
            departure = to_rfc3339(departure_dt)
            legs_out.append({
                "from_poi_id": previous,
                "to_poi_id": key,
                "transport": request["transport"],
                "duration_seconds": dur,
                "distance_meters": int(leg.get("distance_meters", 0)),
                "source_ref": leg.get("source_ref", ""),
                "fetched_at": leg.get("fetched_at", ""),
            })
            evidence.append(leg.get("source_ref", ""))
            if departure_dt > end:
                hard_violation = True
                add_issue(issues, "TIME_WINDOW_EXCEEDED", "blocker",
                          f"{key} 预计离开 {departure} 晚于时间窗结束 {request['time_window']['end']}", subject=key)
            wstart, wend, wlabel = _window_bounds(cand, hours)
            if wstart is None:
                unknown_count += 1
                add_issue(issues, "HOURS_UNKNOWN", "warning",
                          f"{key} 的开放/预约时段未知，保留 unknown（可人工补充并标来源）", subject=key)
            else:
                local_arrival = arrival_dt.astimezone(zone)
                local_departure = departure_dt.astimezone(zone)
                amin = local_arrival.hour * 60 + local_arrival.minute
                dmin = local_departure.hour * 60 + local_departure.minute
                if amin < wstart or dmin > wend:
                    hard_violation = True
                    add_issue(issues, "OPENING_WINDOW_VIOLATION", "blocker",
                              f"{key} 的安排 {local_arrival.strftime('%H:%M')}-{local_departure.strftime('%H:%M')} "
                              f"超出{wlabel} {wstart // 60:02d}:{wstart % 60:02d}-{wend // 60:02d}:{wend % 60:02d}",
                              subject=key)
            current = departure_dt

        visits.append({
            "poi_id": (poi or {}).get("provider_poi_id"),
            "name": (poi or {}).get("name", key),
            "arrival": arrival,
            "departure": departure,
            "stay_seconds": stay,
        })
        if poi:
            evidence.extend(poi.get("evidence_refs", []))
        previous = key

    if hard_violation:
        quality = QualityStatus.INFEASIBLE.value
    elif unknown_count > 0 or degraded or not visits:
        quality = QualityStatus.PARTIALLY_VERIFIED.value
    else:
        quality = QualityStatus.VERIFIED_FEASIBLE.value

    if quality == QualityStatus.INFEASIBLE.value:
        add_issue(issues, "TIME_WINDOW_EXCEEDED", "info",
                  "可选调整：缩短停留、延长时间窗，或通过 revisions 显式删除地点后重算",
                  subject="__adjustments__")

    return {
        "quality_status": quality,
        "visits": visits,
        "legs": legs_out,
        "issues": issues,
        "evidence_refs": sorted({e for e in evidence if e}),
        "unknown_constraint_count": unknown_count,
    }


def next_stage(stage: str) -> str | None:
    try:
        idx = STAGES.index(stage)
    except ValueError:
        return None
    return STAGES[idx + 1] if idx + 1 < len(STAGES) else None
