"""Amap Web Service adapter for the single-day travel judge.

This is an optional LIVE adapter; the replay adapter remains the default.
No key is stored here: set AMAP_API_KEY in the environment. Every external
call is bounded by a timeout and mapped to ToolStatus so that empty results,
provider errors and malformed payloads cannot be reported as success.

Amap does not provide a per-date weather endpoint or an opening-hours endpoint
for arbitrary POIs. Weather is accepted only when the target date appears in
the forecast; opening hours are parsed only when the provider returns them.
"""
from __future__ import annotations

import os
import re
from threading import Lock
from typing import Any, Iterable

from .runtime import LiveRuntime

import httpx

from .domain import (
    ORIGIN_KEY,
    TOOL_STATUS_TO_ISSUE,
    MatchStatus,
    ToolResult,
    ToolStatus,
    leg_key,
    utc_now,
)

AMAP_BASE_URL = "https://restapi.amap.com"
AMAP_PROVIDER = "amap-web-service"
_CITY_SUFFIXES = ("特别行政区", "自治州", "地区", "盟", "市")
_OPEN_RE = re.compile(r"(\d{1,2}):(\d{2})\s*[-~—]\s*(\d{1,2}):(\d{2})")


class AmapClient:
    """Thin HTTP client with deterministic error classification."""

    def __init__(
        self,
        key: str | None = None,
        *,
        base_url: str = AMAP_BASE_URL,
        timeout: float = 5.0,
        transport: httpx.BaseTransport | None = None,
    ):
        self.key = (key if key is not None else os.environ.get("AMAP_API_KEY", "")).strip()
        if not self.key:
            raise ValueError("AMAP_API_KEY is required for live Amap calls")
        self.calls = 0
        self._lock = Lock()
        self._runtime: LiveRuntime | None = None
        self._state = "open"
        self._timeout = timeout
        self._client = httpx.Client(base_url=base_url, timeout=timeout, transport=transport,
                                    follow_redirects=False)

    def bind_runtime(self, runtime: LiveRuntime) -> None:
        if runtime is None:
            raise ValueError("runtime is required")
        with self._lock:
            if self._state != "open" or self._runtime is not None:
                raise RuntimeError("Amap client is active, closing or closed")
            self._runtime = runtime

    def unbind_runtime(self, runtime: LiveRuntime) -> None:
        with self._lock:
            if self._runtime is not runtime:
                raise RuntimeError("Amap runtime identity mismatch")
            self._runtime = None

    def close(self) -> None:
        self.release(None, owns_client=True)

    def release(self, runtime: LiveRuntime | None, *, owns_client: bool) -> None:
        # 身份核对、解绑和closing转换在同一短锁内，HTTP/close在锁外。
        with self._lock:
            if self._runtime is not runtime:
                raise RuntimeError("Amap runtime identity mismatch")
            if self._state != "open":
                return
            self._runtime = None
            if not owns_client:
                return
            self._state = "closing"
        try:
            self._client.close()
        finally:
            # 关闭失败也不能恢复open；不宣称物理释放成功。
            with self._lock:
                self._state = "closed"

    def deliver_evidence(self, tool: str, result: ToolResult) -> None:
        with self._lock:
            runtime = self._runtime
        if runtime is not None:
            runtime.deliver_evidence(tool, result)

    def get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            if self._state != "open":
                raise RuntimeError("Amap client is closing or closed")
            runtime = self._runtime
        timeout = runtime.reserve_http(self._timeout) if runtime is not None else self._timeout
        with self._lock:
            self.calls += 1
        query = {**params, "key": self.key}
        try:
            response = self._client.get(path, params=query, timeout=timeout)
        except httpx.TimeoutException:
            return {"_error": "timeout", "message": "Amap request timed out"}
        except httpx.HTTPError as exc:
            return {"_error": "http", "message": f"{type(exc).__name__}: {exc}"}
        if response.status_code != 200:
            return {"_error": "http", "message": f"HTTP {response.status_code}"}
        try:
            data = response.json()
        except ValueError:
            return {"_error": "format", "message": "response is not valid JSON"}
        if not isinstance(data, dict) or str(data.get("status")) != "1":
            return {
                "_error": "provider",
                "message": f"{data.get('info', 'provider error')} ({data.get('infocode', 'unknown')})"
                if isinstance(data, dict) else "provider error",
                "infocode": data.get("infocode") if isinstance(data, dict) else None,
            }
        return data


def normalize_city(name: str) -> str:
    text = (name or "").strip()
    for suffix in _CITY_SUFFIXES:
        if text.endswith(suffix) and len(text) > len(suffix):
            return text[: -len(suffix)]
    return text


def _location(text: str) -> tuple[float, float] | None:
    try:
        lon, lat = (float(part) for part in str(text).split(",", 1))
    except (TypeError, ValueError):
        return None
    if not (-180 <= lon <= 180 and -90 <= lat <= 90):
        return None
    return lon, lat


def _tool_error(status: str, ref: str, message: str) -> ToolResult:
    return ToolResult(
        status=ToolStatus(status),
        source_ref=ref,
        fetched_at=utc_now(),
        error_code=TOOL_STATUS_TO_ISSUE.get(status, "TOOL_UNAVAILABLE"),
        message=message,
    )


def _map_client_error(error: dict[str, Any], ref: str) -> ToolResult:
    kind = error.get("_error")
    if kind == "timeout":
        return _tool_error("timeout", ref, str(error.get("message")))
    if kind == "format":
        return _tool_error("format_error", ref, str(error.get("message")))
    return _tool_error("provider_error", ref, str(error.get("message")))


def _parse_open_window(value: Any) -> list[str] | None:
    if not isinstance(value, str):
        return None
    match = _OPEN_RE.search(value)
    if not match:
        return None
    start_h, start_m, end_h, end_m = (int(part) for part in match.groups())
    if not (0 <= start_h <= 23 and 0 <= end_h <= 23 and 0 <= start_m <= 59 and 0 <= end_m <= 59):
        return None
    return [f"{start_h:02d}:{start_m:02d}", f"{end_h:02d}:{end_m:02d}"]


class AmapAdapter:
    """Live tool adapter implementing the same surface as ReplayAdapter.

    A run is bound to one city and one transport. POI results are cached for
    the lifetime of the adapter; route calls are explicit because Amap bills
    per request and the engine budget must stay observable.
    """

    def __init__(self, client: AmapClient, *, city: str, transport: str = "walking",
                 owns_client: bool = False):
        if transport not in ("walking", "driving"):
            if owns_client:
                client.close()
            raise ValueError("live adapter supports walking or driving only")
        self.client = client
        self.city = city
        self.transport = transport
        self._owns_client = owns_client
        self._lifecycle_lock = Lock()
        self._runtime: LiveRuntime | None = None
        self._closed = False
        # 最近一次bind未取得所有权：紧接着的那次close属于失败的绑定尝试，
        # 必须让位给原owner（不触碰client、不改本对象绑定状态）。
        self._binding_failed = False
        self._pois: dict[str, dict[str, Any]] = {}
        self._adcode: str | None = None

    def bind_runtime(self, runtime: LiveRuntime) -> None:
        with self._lifecycle_lock:
            if self._closed:
                raise RuntimeError("Amap adapter is active or closed")
            if self._runtime is not None:
                # 该adapter已属于另一个运行：本次调用没有取得它。标记后，紧接着
                # 由本次运行发起的那次close只作废自己，不解绑/关闭原owner的client。
                self._binding_failed = True
                raise RuntimeError("Amap adapter is active or closed")
            try:
                self.client.bind_runtime(runtime)
            except Exception:
                # client已绑定别的run或已closing/closed：本adapter未取得控制权，
                # 只把自己作废，绝不物理关闭共享client。
                self._binding_failed = True
                self._closed = True
                raise
            self._runtime = runtime
            self._binding_failed = False

    def close(self) -> None:
        with self._lifecycle_lock:
            if self._binding_failed:
                # 对应的是一次失败的bind：对象未被本次运行取得，不触碰client，
                # 也不把对象标记为closed（它仍归原owner，原owner的close照常生效）。
                self._binding_failed = False
                return
            if self._closed:
                return
            self._closed = True
            runtime = self._runtime
            self._runtime = None
        self.client.release(runtime, owns_client=self._owns_client)

    # -- POI --------------------------------------------------------------- #
    def _search(self, keywords: str) -> dict[str, Any]:
        return self.client.get(
            "/v3/place/text",
            {
                "keywords": keywords,
                "city": self.city,
                "citylimit": "true",
                "offset": "10",
                "page": "1",
                "extensions": "base",
            },
        )

    def _detail(self, poi_id: str) -> dict[str, Any]:
        return self.client.get("/v3/place/detail", {"id": poi_id, "extensions": "all"})

    def resolve_origin(self, address: str) -> ToolResult:
        """Geocode the start address so matrix() can route from it."""
        ref = f"amap:origin:{address}"
        data = self.client.get("/v3/geocode/geo", {"address": address, "city": self.city})
        if "_error" in data:
            return _map_client_error(data, ref)
        geocodes = data.get("geocodes") or []
        if not geocodes:
            return ToolResult(status=ToolStatus.EMPTY, source_ref=ref, fetched_at=utc_now(),
                              message="origin not found")
        point = _location((geocodes[0] or {}).get("location", ""))
        if point is None:
            return _tool_error("format_error", ref, "origin geocode has no valid coordinates")
        poi = {"provider_poi_id": "origin", "name": address,
               "city": str((geocodes[0] or {}).get("city", "") or self.city),
               "address": address, "coordinates": {"lon": point[0], "lat": point[1]}, "adcode": ""}
        self._pois[ORIGIN_KEY] = poi
        return ToolResult(status=ToolStatus.VALID, source_ref=ref, fetched_at=utc_now(),
                          payload={"poi": poi})

    def poi_lookup(self, candidate_key: str, selected_poi_id: str | None = None) -> ToolResult:
        ref = f"amap:poi:{candidate_key}"
        if selected_poi_id:
            data = self._detail(selected_poi_id)
            if "_error" in data:
                return _map_client_error(data, ref)
            pois = data.get("pois") or []
            if not pois:
                return ToolResult(status=ToolStatus.EMPTY, source_ref=ref, fetched_at=utc_now(),
                                  payload={"match_status": MatchStatus.UNMATCHED.value},
                                  message="selected POI id returned no detail")
            poi = self._to_poi(pois[0])
            if poi is None:
                return _tool_error("format_error", ref, "POI detail has no valid coordinates")
            self._pois[candidate_key] = poi
            return ToolResult(status=ToolStatus.VALID, source_ref=ref, fetched_at=utc_now(),
                              payload={"match_status": MatchStatus.MATCHED.value, "poi": poi,
                                       "selected_by_user": True})
        data = self._search(candidate_key)
        if "_error" in data:
            return _map_client_error(data, ref)
        pois = [self._to_poi(item) for item in (data.get("pois") or [])]
        pois = [poi for poi in pois if poi is not None]
        if not pois:
            return ToolResult(status=ToolStatus.VALID, source_ref=ref, fetched_at=utc_now(),
                              payload={"match_status": MatchStatus.UNMATCHED.value})
        exact = [poi for poi in pois if poi["name"] == candidate_key]
        choices = exact or pois
        if len(choices) == 1:
            poi = choices[0]
            self._pois[candidate_key] = poi
            return ToolResult(status=ToolStatus.VALID, source_ref=ref, fetched_at=utc_now(),
                              payload={"match_status": MatchStatus.MATCHED.value, "poi": poi})
        options = [
            {k: poi[k] for k in ("provider_poi_id", "name", "city", "address", "coordinates")}
            for poi in choices[:5]
        ]
        return ToolResult(status=ToolStatus.VALID, source_ref=ref, fetched_at=utc_now(),
                          payload={"match_status": MatchStatus.AMBIGUOUS.value, "options": options})

    def _to_poi(self, raw: dict[str, Any]) -> dict[str, Any] | None:
        point = _location(raw.get("location", ""))
        if point is None or not raw.get("id") or not raw.get("name"):
            return None
        return {
            "provider_poi_id": str(raw["id"]),
            "name": str(raw["name"]),
            "city": str(raw.get("cityname", "")),
            "address": str(raw.get("address", "")),
            "coordinates": {"lon": point[0], "lat": point[1]},
            "adcode": str(raw.get("adcode", "")),
        }

    # -- Weather ----------------------------------------------------------- #
    def _city_adcode(self) -> str | None:
        if self._adcode:
            return self._adcode
        data = self.client.get("/v3/geocode/geo", {"address": self.city, "city": self.city})
        if "_error" in data:
            return None
        geocodes = data.get("geocodes") or []
        if not geocodes:
            return None
        self._adcode = str(geocodes[0].get("adcode", "") or "") or None
        return self._adcode

    def weather(self, target_date: str) -> ToolResult:
        ref = f"amap:weather:{self.city}:{target_date}"
        adcode = self._city_adcode()
        if not adcode:
            return _tool_error("provider_error", ref, "city adcode not found; weather not queried")
        data = self.client.get("/v3/weather/weatherInfo",
                               {"city": adcode, "extensions": "all"})
        if "_error" in data:
            return _map_client_error(data, ref)
        forecasts = data.get("forecasts") or []
        casts = []
        for forecast in forecasts:
            casts.extend(forecast.get("casts") or [])
        chosen = next((cast for cast in casts if str(cast.get("date")) == target_date), None)
        if chosen is None:
            return ToolResult(
                status=ToolStatus.UNAVAILABLE, source_ref=ref, fetched_at=utc_now(),
                error_code="WEATHER_DATE_NOT_COVERED",
                message="target date is outside the provider forecast window; current weather is not used",
            )
        summary = " / ".join(
            part for part in (chosen.get("dayweather"), chosen.get("nightweather")) if part
        ) or "unknown"
        return ToolResult(
            status=ToolStatus.VALID, source_ref=ref, fetched_at=utc_now(),
            payload={"date": target_date, "summary": summary, "adcode": adcode,
                     "daytemp": chosen.get("daytemp"), "nighttemp": chosen.get("nighttemp")},
        )

    # -- Opening hours ----------------------------------------------------- #
    def hours(self) -> ToolResult:
        ref = f"amap:hours:{self.city}"
        windows: dict[str, list[str]] = {}
        errors = 0
        for key, poi in self._pois.items():
            if key == ORIGIN_KEY:
                continue
            data = self._detail(poi["provider_poi_id"])
            if "_error" in data:
                errors += 1
                continue
            detail = (data.get("pois") or [{}])[0]
            biz = detail.get("biz_ext") or {}
            parsed = _parse_open_window(biz.get("open_time")) or _parse_open_window(biz.get("opentime2"))
            if parsed:
                self.client.deliver_evidence("hours_detail", ToolResult(
                    status=ToolStatus.VALID, source_ref=f"amap:hours:{poi['provider_poi_id']}",
                    fetched_at=utc_now(), payload={"windows": {key: parsed}},
                ))
                windows[key] = parsed
        if not windows:
            status = ToolStatus.EMPTY if errors == 0 else ToolStatus.PROVIDER_ERROR
            return ToolResult(status=status, source_ref=ref, fetched_at=utc_now(),
                              payload={"windows": {}}, message="no opening hours returned by provider")
        return ToolResult(status=ToolStatus.VALID, source_ref=ref, fetched_at=utc_now(),
                          payload={"windows": windows})

    # -- Routes ------------------------------------------------------------ #
    def _route(self, origin: str, destination: str) -> dict[str, Any]:
        path = "/v3/direction/walking" if self.transport == "walking" else "/v3/direction/driving"
        return self.client.get(path, {"origin": origin, "destination": destination, "extensions": "base"})

    def leg(self, from_key: str, to_key: str) -> ToolResult:
        ref = f"amap:route:{from_key}->{to_key}"
        start, end = self._pois.get(from_key), self._pois.get(to_key)
        if not start or not end:
            return _tool_error("unavailable", ref, "both POIs must be resolved before routing")
        data = self._route(_coord(start), _coord(end))
        if "_error" in data:
            return _map_client_error(data, ref)
        paths = (data.get("route") or {}).get("paths") or []
        if not paths:
            return ToolResult(status=ToolStatus.EMPTY, source_ref=ref, fetched_at=utc_now(),
                              payload={}, message="no route path returned")
        try:
            duration = int(float(paths[0]["duration"]))
            distance = int(float(paths[0].get("distance", 0)))
        except (KeyError, TypeError, ValueError):
            return _tool_error("format_error", ref, "route path has no numeric duration/distance")
        return ToolResult(
            status=ToolStatus.VALID, source_ref=ref, fetched_at=utc_now(),
            payload={"duration_seconds": duration, "distance_meters": distance,
                     "from": from_key, "to": to_key},
        )

    def matrix(self, pairs: Iterable[tuple[str, str]]) -> ToolResult:
        ref = f"amap:routes:{self.transport}"
        matrix: dict[str, dict[str, Any]] = {}
        fetched_at = utc_now()
        for from_key, to_key in pairs:
            result = self.leg(from_key, to_key)
            if result.status != ToolStatus.VALID:
                return result
            self.client.deliver_evidence("route_leg", result)
            payload = result.payload or {}
            fetched_at = result.fetched_at
            matrix[leg_key(from_key, to_key)] = {
                "duration_seconds": payload["duration_seconds"],
                "distance_meters": payload["distance_meters"],
                "source_ref": result.source_ref,
                "fetched_at": fetched_at,
            }
        return ToolResult(status=ToolStatus.VALID, source_ref=ref, fetched_at=fetched_at,
                          payload={"matrix": matrix})


def _coord(poi: dict[str, Any]) -> str:
    point = poi["coordinates"]
    return f"{point['lon']:.6f},{point['lat']:.6f}"
