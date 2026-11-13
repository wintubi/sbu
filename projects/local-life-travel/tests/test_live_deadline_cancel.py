"""Task 2：单调deadline、可达的API取消与原子终态。

全部离线：假时钟/真实单调时钟偏移、``httpx.MockTransport`` 合成供应商、
进程内真实loopback（127.0.0.1）并发POST/重放/cancel/GET。不访问真实供应商，
不用真实sleep制造90秒，不旁路写DB代替取消。
"""
from __future__ import annotations

import time
from contextlib import contextmanager
from datetime import timedelta
from threading import Event, Thread

import httpx
import pytest
import uvicorn
from fastapi.testclient import TestClient

from app.amap_tools import AmapAdapter, AmapClient
from app.domain import (
    DEFAULT_BUDGET,
    REPLAY_NOTICE,
    ToolResult,
    ToolStatus,
    leg_key,
    utc_now,
)
from app.main import LIVE_NOTICE, create_app
from app.runtime import BudgetExhausted, LiveRuntime, RunCancelled, RuntimeControlError


def live_body() -> dict:
    return {
        "mode": "live", "city": "北京", "date": "2026-11-09", "timezone": "Asia/Shanghai",
        "origin": "合成起点", "transport": "walking",
        "time_window": {"start": "2026-11-09T09:00:00+08:00",
                        "end": "2026-11-09T18:00:00+08:00"},
        "candidates": [{"name": name, "stay_seconds": 600}
                       for name in ("合成甲", "合成乙", "合成丙")],
    }


# --------------------------------------------------------------------------- #
# 时钟 / fake
# --------------------------------------------------------------------------- #
class FakeClock:
    """可写单调时钟：从0开始，测试直接赋值推进，不sleep。"""

    def __init__(self, value: float = 0.0):
        self.value = value

    def __call__(self) -> float:
        return self.value


class OffsetClock:
    """真实单调时钟 + 可写偏移；用于在工具/清理阶段越过总deadline。"""

    def __init__(self):
        self.offset = 0.0

    def __call__(self) -> float:
        return time.monotonic() + self.offset


class BlockingFinalClock:
    """真实单调时钟，但可让“收尾后最后一次check”的采样阻塞在barrier上。"""

    def __init__(self):
        self.block_next = False
        self.blocked = Event()
        self.release = Event()

    def __call__(self) -> float:
        if self.block_next:
            self.block_next = False
            self.blocked.set()
            if not self.release.wait(20):
                raise AssertionError("final clock release timeout")
        return time.monotonic()


def runtime_with(clock=None, *, limit: int = 40, seconds: float = 90.0,
                 probe=None) -> LiveRuntime:
    return LiveRuntime({**DEFAULT_BUDGET, "max_tool_calls": limit,
                        "max_total_seconds": seconds},
                       clock=clock, cancel_probe=probe)


# --------------------------------------------------------------------------- #
# 真实适配器 + 合成供应商
# --------------------------------------------------------------------------- #
class ProviderTransport(httpx.MockTransport):
    """正常15次发送路径的合成供应商；记录真正到达传输层的请求。"""

    def __init__(self):
        self.sent: list[str] = []
        super().__init__(self.handle)

    def handle(self, request: httpx.Request) -> httpx.Response:
        assert request.url.params["key"] == "synthetic-example"
        path = request.url.path
        self.sent.append(path)
        if path == "/v3/geocode/geo":
            data = {"geocodes": [{"location": "116.4,39.9", "city": "北京",
                                  "adcode": "110000"}]}
        elif path == "/v3/place/text":
            name = request.url.params["keywords"]
            data = {"pois": [{"id": name, "name": name, "cityname": "北京",
                              "location": "116.4,39.9"}]}
        elif path == "/v3/place/detail":
            data = {"pois": [{"biz_ext": {"open_time": "09:00-18:00"}}]}
        elif path == "/v3/weather/weatherInfo":
            data = {"forecasts": [{"casts": [{"date": "2026-11-09",
                                              "dayweather": "晴"}]}]}
        else:
            assert path == "/v3/direction/walking"
            data = {"route": {"paths": [{"duration": "60", "distance": "100"}]}}
        return httpx.Response(200, json={"status": "1", **data})


class BlockingClient(AmapClient):
    """在第二次发送（POI搜索）之前阻塞，先让取消提交，再观察是否还会发送。"""

    def __init__(self, *args, gate: Event, release: Event, **kwargs):
        super().__init__(*args, **kwargs)
        self.gate = gate
        self.release = release

    def get(self, path: str, params: dict):
        if path == "/v3/place/text" and not self.gate.is_set():
            self.gate.set()
            if not self.release.wait(20):
                raise AssertionError("adapter release timeout")
        return super().get(path, params)


class GatedCloseAmapAdapter(AmapAdapter):
    """清理阶段阻塞：此时主分类已在内存中，取消可在最终提交前胜出。"""

    def __init__(self, *args, entered: Event, release: Event, **kwargs):
        super().__init__(*args, **kwargs)
        self.entered = entered
        self.release = release

    def close(self):
        self.entered.set()
        if not self.release.wait(20):
            raise AssertionError("close release timeout")
        super().close()


class BlockingCloseAmapAdapter(AmapAdapter):
    """收尾close置位后阻塞下一次时钟采样（即收尾后最后一次check）。"""

    def __init__(self, *args, clock: BlockingFinalClock, **kwargs):
        super().__init__(*args, **kwargs)
        self.clock = clock

    def close(self):
        super().close()
        self.clock.block_next = True


# --------------------------------------------------------------------------- #
# 协议fake：显式逐HTTP准入，可挂发送/清理钩子
# --------------------------------------------------------------------------- #
class FakeAdapter:
    def __init__(self, *, mode: str = "ok", on_send=None, on_close=None):
        self.mode = mode
        self.on_send = on_send
        self.on_close = on_close
        self.sent: list[str] = []
        self._resolved: list[str] = []
        self._runtime = None
        self._closed = False

    def bind_runtime(self, runtime):
        if self._closed or self._runtime is not None:
            raise RuntimeError("fake adapter is active or closed")
        self._runtime = runtime

    def close(self):
        self._closed = True
        self._runtime = None
        if self.on_close is not None:
            self.on_close()

    def _send(self, label: str) -> None:
        if self._runtime is None:
            raise RuntimeError("fake adapter is not bound to a runtime")
        self._runtime.reserve_http(5.0)
        self.sent.append(label)
        if self.on_send is not None:
            self.on_send(label)

    def resolve_origin(self, address: str):
        self._send("origin")
        if self.mode == "origin_timeout":
            return ToolResult(status=ToolStatus.TIMEOUT, source_ref="fake:origin",
                              fetched_at=utc_now(), error_code="TOOL_TIMEOUT",
                              message="synthetic timeout")
        if self.mode == "origin_provider_error":
            return ToolResult(status=ToolStatus.PROVIDER_ERROR, source_ref="fake:origin",
                              fetched_at=utc_now(), error_code="TOOL_PROVIDER_ERROR",
                              message="synthetic provider error")
        if self.mode == "origin_format_error":
            return ToolResult(status=ToolStatus.FORMAT_ERROR, source_ref="fake:origin",
                              fetched_at=utc_now(), error_code="TOOL_FORMAT_ERROR",
                              message="synthetic format error")
        return ToolResult(status=ToolStatus.VALID, source_ref="fake:origin",
                          fetched_at=utc_now(),
                          payload={"poi": {"name": address, "city": "北京",
                                           "coordinates": {"lon": 116.4, "lat": 39.9}}})

    def poi_lookup(self, key: str, selected_poi_id: str | None = None):
        self._send(f"poi:{key}")
        if self.mode == "ambiguous" and key == "合成乙" and not selected_poi_id:
            return ToolResult(status=ToolStatus.VALID, source_ref=f"fake:poi:{key}",
                              fetched_at=utc_now(),
                              payload={"match_status": "ambiguous",
                                       "options": [{"provider_poi_id": "A", "name": key},
                                                   {"provider_poi_id": "B", "name": key}]})
        if key not in self._resolved:
            self._resolved.append(key)
        return ToolResult(status=ToolStatus.VALID, source_ref=f"fake:poi:{key}",
                          fetched_at=utc_now(),
                          payload={"match_status": "matched",
                                   "poi": {"provider_poi_id": key, "name": key, "city": "北京",
                                           "coordinates": {"lon": 116.4, "lat": 39.9}}})

    def weather(self, date: str):
        self._send("weather")
        return ToolResult(status=ToolStatus.VALID, source_ref="fake:weather",
                          fetched_at=utc_now(), payload={"date": date, "summary": "晴"})

    def hours(self):
        self._send("hours")
        return ToolResult(status=ToolStatus.VALID, source_ref="fake:hours",
                          fetched_at=utc_now(),
                          payload={"windows": {name: ["09:00", "17:00"]
                                               for name in self._resolved}})

    def matrix(self, pairs):
        pairs = list(pairs)
        self._send("matrix")
        matrix = {leg_key(a, b): {"duration_seconds": 600, "distance_meters": 1000,
                                  "source_ref": "fake:route", "fetched_at": utc_now()}
                  for a, b in pairs}
        return ToolResult(status=ToolStatus.VALID, source_ref="fake:routes",
                          fetched_at=utc_now(), payload={"matrix": matrix})


class BlockingFakeAdapter(FakeAdapter):
    """第一次工具之前阻塞：取消先提交，随后该run不应再有HTTP。"""

    def __init__(self, *, entered: Event, release: Event):
        super().__init__()
        self.entered = entered
        self.release = release

    def resolve_origin(self, address: str):
        self.entered.set()
        if not self.release.wait(20):
            raise AssertionError("fake adapter release timeout")
        return super().resolve_origin(address)


# --------------------------------------------------------------------------- #
# loopback服务
# --------------------------------------------------------------------------- #
@contextmanager
def serve(app):
    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error",
                            lifespan="on", access_log=False)
    server = uvicorn.Server(config)
    thread = Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("uvicorn did not start")
        time.sleep(0.005)
    port = server.servers[0].sockets[0].getsockname()[1]
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=20)
        assert not thread.is_alive()


def assert_cancelled_snapshot(payload: dict, *, require_reason_absent: bool = True) -> None:
    assert payload["status"] == "cancelled"
    assert payload["budget"]["status"] == "cancelled"
    assert payload["quality_status"] == "unverified"
    assert payload["result"] is None
    if require_reason_absent:
        assert "exhaustion_reason" not in payload["budget"]


def assert_live_cancel_wording(payload: dict) -> None:
    assert payload["mode"] == "live"
    assert payload["replay_notice"] == LIVE_NOTICE
    assert REPLAY_NOTICE not in payload["replay_notice"]
    message = payload["message"]
    assert "回放" not in message and "无远端" not in message
    assert "尽力" in message and "可能仍完成" in message


# --------------------------------------------------------------------------- #
# 运行时单元：单调边界 / timeout / 探针
# --------------------------------------------------------------------------- #
def test_check_boundary_zero_and_ninety_uses_monotonic_clock():
    clock = FakeClock(0.0)
    runtime = runtime_with(clock)
    runtime.check()  # elapsed == 0 < 90
    clock.value = 89.999
    runtime.check()
    clock.value = 90.0
    with pytest.raises(BudgetExhausted) as info:
        runtime.check()
    assert info.value.reason == "deadline"
    assert runtime.budget["tool_calls"] == 0  # check不消费HTTP次数


def test_check_observes_cancel_before_deadline():
    clock = FakeClock(0.0)
    order: list[str] = []

    def probe():
        order.append("probe")
        return "cancelled"

    runtime = LiveRuntime({**DEFAULT_BUDGET, "max_total_seconds": 90},
                          clock=clock, cancel_probe=probe)
    clock.value = 91.0  # 时间也已到：仍必须先观察取消
    with pytest.raises(RunCancelled):
        runtime.check()
    assert order == ["probe"]


def test_reserve_http_timeout_is_min_of_config_and_remaining():
    clock = FakeClock(0.0)
    runtime = runtime_with(clock)
    assert runtime.reserve_http(5.0) == 5.0            # 配置更短：不放大
    clock.value = 89.0
    assert runtime.reserve_http(5.0) == 1.0            # 剩余1秒
    clock.value = 89.0
    assert runtime.reserve_http(0.25) == 0.25          # 更短配置不被放大
    clock.value = 89.75
    timeout = runtime.reserve_http(5.0)
    assert timeout == 0.25                             # 剩余0.25秒
    assert 0 < timeout < float("inf")                  # 不关闭超时
    assert runtime.budget["tool_calls"] == 4


def test_reserve_http_rejects_without_consuming_limit_or_deadline():
    clock = FakeClock(0.0)
    limited = runtime_with(clock, limit=0)
    with pytest.raises(BudgetExhausted) as info:
        limited.reserve_http(5.0)
    assert info.value.reason == "call_limit"
    assert limited.budget["tool_calls"] == 0
    clock.value = 0.0
    expired = runtime_with(clock)
    clock.value = 90.0
    with pytest.raises(BudgetExhausted) as info:
        expired.reserve_http(5.0)
    assert info.value.reason == "deadline"
    assert expired.budget["tool_calls"] == 0


def test_probe_failure_is_fixed_category_without_raw_exception_text():
    clock = FakeClock(0.0)

    def boom():
        raise RuntimeError("synthetic secret /v3/geocode/geo?key=SECRET-TOKEN")

    runtime = runtime_with(clock, probe=boom)
    with pytest.raises(RuntimeControlError) as info:
        runtime.reserve_http(5.0)
    text = str(info.value)
    assert "secret" not in text.lower() and "SECRET" not in text
    assert info.value.safe_exception_type == "RuntimeError"
    assert runtime.budget["tool_calls"] == 0

    missing = runtime_with(clock, probe=lambda: None)
    with pytest.raises(RuntimeControlError) as info:
        missing.check()
    assert info.value.category == "RUN_STATE_MISSING"
    assert missing.budget["tool_calls"] == 0


def test_utc_wall_clock_jump_does_not_change_monotonic_elapsed(monkeypatch):
    real_time = time.time
    monkeypatch.setattr(time, "time", lambda: real_time() + 3600)
    import app.domain as domain_module
    real_datetime = domain_module.datetime

    class JumpedDatetime(real_datetime):
        @classmethod
        def now(cls, tz=None):
            return real_datetime.now(tz) + timedelta(hours=1)

    monkeypatch.setattr(domain_module, "datetime", JumpedDatetime)
    clock = FakeClock(0.0)
    runtime = runtime_with(clock)
    assert runtime.elapsed() == 0.0
    runtime.check()
    assert runtime.reserve_http(5.0) == 5.0
    clock.value = 90.0
    with pytest.raises(BudgetExhausted) as info:
        runtime.check()
    assert info.value.reason == "deadline"


@pytest.mark.parametrize("configured,remaining,expected", [
    (5.0, 90.0, 5.0),
    (5.0, 1.0, 1.0),
    (0.25, 1.0, 0.25),
])
def test_amap_client_applies_bounded_timeout_to_all_four_operations(
        configured, remaining, expected):
    seen: list[dict] = []

    def handler(request: httpx.Request):
        seen.append(request.extensions["timeout"])
        return httpx.Response(200, json={"status": "1"})

    clock = FakeClock(0.0)
    runtime = runtime_with(clock)
    clock.value = 90.0 - remaining
    client = AmapClient(key="synthetic-example", timeout=configured,
                        transport=httpx.MockTransport(handler))
    client.bind_runtime(runtime)
    try:
        client.get("/v3/geocode/geo", {})
    finally:
        client.unbind_runtime(runtime)
        client.close()
    assert len(seen) == 1
    assert set(seen[0]) == {"connect", "read", "write", "pool"}
    assert all(value == pytest.approx(expected) for value in seen[0].values())
    assert runtime.budget["tool_calls"] == 1


# --------------------------------------------------------------------------- #
# API：deadline / 晚到 / 普通失败（TestClient，仍走同一ASGI与threadpool）
# --------------------------------------------------------------------------- #
def _api(store, worker, factory, clock=None):
    return create_app(store=store, worker=worker, manual_drain=True,
                      live_adapter_factory=factory, live_clock=clock)


def test_deadline_zero_before_factory_starts_no_http(store, worker, monkeypatch):
    import app.live as live_module
    monkeypatch.setattr(live_module, "DEFAULT_BUDGET",
                        {**DEFAULT_BUDGET, "max_total_seconds": 0})
    factory_calls: list[str] = []

    def factory(city, transport):
        factory_calls.append(city)
        return FakeAdapter()

    app = _api(store, worker, factory)
    with TestClient(app) as api:
        data = api.post("/api/v1/travel/live-runs", json=live_body(),
                        headers={"Idempotency-Key": "zero-deadline"}).json()
        assert data["status"] == "failed"
        assert data["budget"]["status"] == "exhausted"
        assert data["budget"]["exhaustion_reason"] == "deadline"
        assert data["budget"]["tool_calls"] == 0
        assert data["result"] is None and data["quality_status"] == "unverified"
        assert any(issue["code"] == "BUDGET_EXHAUSTED" for issue in data["issues"])
        assert factory_calls == []
        reread = api.get(f"/api/v1/travel/runs/{data['run_id']}").json()
        assert reread["budget"] == data["budget"]


def test_late_tool_result_after_deadline_is_not_completed(store, worker):
    clock = OffsetClock()

    def advance(label: str) -> None:
        if label == "origin":
            clock.offset = 91.0

    adapter = FakeAdapter(on_send=advance)
    with TestClient(_api(store, worker, lambda city, transport: adapter, clock)) as api:
        data = api.post("/api/v1/travel/live-runs", json=live_body(),
                        headers={"Idempotency-Key": "late-tool"}).json()
    assert data["status"] == "failed"
    assert data["budget"]["status"] == "exhausted"
    assert data["budget"]["exhaustion_reason"] == "deadline"
    assert data["budget"]["elapsed_seconds"] >= 90
    assert data["budget"]["tool_calls"] == 1
    assert adapter.sent == ["origin"]
    assert data["tool_results"] == []  # 晚到结果不作为正常工具证据
    assert data["result"] is None and data["quality_status"] == "unverified"


def test_late_needs_input_after_deadline_is_rejected(store, worker):
    clock = OffsetClock()

    def advance(label: str) -> None:
        if label == "weather":
            clock.offset = 91.0

    adapter = FakeAdapter(mode="ambiguous", on_send=advance)
    with TestClient(_api(store, worker, lambda city, transport: adapter, clock)) as api:
        data = api.post("/api/v1/travel/live-runs", json=live_body(),
                        headers={"Idempotency-Key": "late-needs-input"}).json()
    assert data["status"] == "failed"
    assert data["budget"]["status"] == "exhausted"
    assert data["budget"]["exhaustion_reason"] == "deadline"
    assert data["quality_status"] == "unverified" and data["result"] is None
    assert any(issue["code"] == "BUDGET_EXHAUSTED" for issue in data["issues"])


def test_cleanup_past_deadline_rejects_completed_terminal(store, worker):
    clock = OffsetClock()
    adapter = FakeAdapter(on_close=lambda: setattr(clock, "offset", 91.0))
    with TestClient(_api(store, worker, lambda city, transport: adapter, clock)) as api:
        data = api.post("/api/v1/travel/live-runs", json=live_body(),
                        headers={"Idempotency-Key": "late-cleanup"}).json()
    assert data["status"] == "failed"
    assert data["budget"]["status"] == "exhausted"
    assert data["budget"]["exhaustion_reason"] == "deadline"
    assert data["budget"]["elapsed_seconds"] >= 90
    assert data["quality_status"] == "unverified" and data["result"] is None
    assert len(data["tool_results"]) == data["budget"]["tool_calls"]  # 证据保留


@pytest.mark.parametrize("mode,issue_code", [
    ("origin_timeout", "TOOL_TIMEOUT"),
    ("origin_provider_error", "TOOL_PROVIDER_ERROR"),
    ("origin_format_error", "TOOL_FORMAT_ERROR"),
])
def test_ordinary_tool_failure_keeps_classification(store, worker, mode, issue_code):
    adapter = FakeAdapter(mode=mode)
    with TestClient(_api(store, worker, lambda city, transport: adapter)) as api:
        data = api.post("/api/v1/travel/live-runs", json=live_body(),
                        headers={"Idempotency-Key": f"plain-{mode}"}).json()
    assert data["status"] == "failed"
    assert data["budget"]["status"] == "failed"
    assert "exhaustion_reason" not in data["budget"]
    assert data["budget"]["tool_calls"] == 1
    assert any(issue["code"] == issue_code for issue in data["issues"])
    assert data["result"] is None and data["quality_status"] == "unverified"


def test_primary_failure_survives_later_deadline_check(store, worker):
    clock = OffsetClock()
    adapter = FakeAdapter(mode="origin_provider_error",
                          on_close=lambda: setattr(clock, "offset", 91.0))
    with TestClient(_api(store, worker, lambda city, transport: adapter, clock)) as api:
        data = api.post("/api/v1/travel/live-runs", json=live_body(),
                        headers={"Idempotency-Key": "primary-failure"}).json()
    assert data["status"] == "failed"
    assert data["budget"]["status"] == "failed"      # 更早主失败不被时间检查覆盖
    assert "exhaustion_reason" not in data["budget"]
    assert data["budget"]["elapsed_seconds"] >= 90
    assert any(issue["code"] == "TOOL_PROVIDER_ERROR" for issue in data["issues"])
    assert not any(issue["code"] == "BUDGET_EXHAUSTED" for issue in data["issues"])


def test_idempotent_replay_does_not_build_runtime(store, worker, monkeypatch):
    import app.live as live_module
    built: list[str] = []
    real_runtime = live_module.LiveRuntime

    class CountingRuntime(real_runtime):
        def __init__(self, *args, **kwargs):
            built.append("runtime")
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(live_module, "LiveRuntime", CountingRuntime)
    adapter = FakeAdapter()
    with TestClient(_api(store, worker, lambda city, transport: adapter)) as api:
        first = api.post("/api/v1/travel/live-runs", json=live_body(),
                         headers={"Idempotency-Key": "runtime-replay"}).json()
        assert first["status"] == "completed"
        assert len(built) == 1
        replay = api.post("/api/v1/travel/live-runs", json=live_body(),
                          headers={"Idempotency-Key": "runtime-replay"}).json()
        assert replay["run_id"] == first["run_id"] and replay["replayed"] is True
        assert len(built) == 1  # 幂等命中不建立runtime/factory/HTTP


def test_cancel_rejects_committed_live_failure(store, worker):
    adapter = FakeAdapter(mode="origin_provider_error")
    with TestClient(_api(store, worker, lambda city, transport: adapter)) as api:
        data = api.post("/api/v1/travel/live-runs", json=live_body(),
                        headers={"Idempotency-Key": "committed-failure"}).json()
        assert data["status"] == "failed"
        rejected = api.post(f"/api/v1/travel/runs/{data['run_id']}/cancel")
        assert rejected.status_code == 409
        assert rejected.json()["code"] == "RUN_NOT_CANCELLABLE"
        reread = api.get(f"/api/v1/travel/runs/{data['run_id']}").json()
        assert reread["status"] == "failed"
        assert reread["budget"]["status"] == "failed"


# --------------------------------------------------------------------------- #
# 真实loopback并发：创建/修订在threadpool里等待时，重放与取消必须可达
# --------------------------------------------------------------------------- #
def test_api_create_replay_then_cancel_stops_next_handler(store, worker):
    gate, release = Event(), Event()
    boundary = ProviderTransport()
    factory_calls: list[str] = []

    def factory(city, transport):
        factory_calls.append(city)
        client = BlockingClient(key="synthetic-example", transport=boundary,
                                gate=gate, release=release)
        return AmapAdapter(client, city=city, transport=transport, owns_client=True)

    app = _api(store, worker, factory)
    with serve(app) as base:
        body = live_body()
        with httpx.Client(base_url=base, timeout=20, trust_env=False) as original, \
                httpx.Client(base_url=base, timeout=20, trust_env=False) as control:
            result: dict = {}

            def run_original():
                result["response"] = original.post(
                    "/api/v1/travel/live-runs", json=body,
                    headers={"Idempotency-Key": "reachable-create"})

            thread = Thread(target=run_original, daemon=True)
            thread.start()
            try:
                assert gate.wait(15)
                # 在等待期间，同键同载荷重放拿到run_id，且不新增factory/HTTP/事件。
                replay = control.post("/api/v1/travel/live-runs", json=body,
                                      headers={"Idempotency-Key": "reachable-create"})
                assert replay.status_code == 202
                assert replay.json()["replayed"] is True
                run_id = replay.json()["run_id"]
                events_before = len(replay.json()["events"])
                sent_before = list(boundary.sent)
                assert factory_calls == ["北京"]
                again = control.post("/api/v1/travel/live-runs", json=body,
                                     headers={"Idempotency-Key": "reachable-create"})
                assert again.json()["run_id"] == run_id
                assert len(again.json()["events"]) == events_before
                assert len(factory_calls) == 1 and boundary.sent == sent_before
                # 取消入口可达；确认的快照在短事务内已归一。
                cancel = control.post(f"/api/v1/travel/runs/{run_id}/cancel")
                assert cancel.status_code == 200
                assert_live_cancel_wording(cancel.json())
                assert_cancelled_snapshot(cancel.json())
                cancelled_events = [item for item in cancel.json()["events"]
                                    if item["action"] == "CANCELLED"]
                assert len(cancelled_events) == 1
                assert "LIVE" in cancelled_events[0]["reason"]
                assert "回放" not in cancelled_events[0]["reason"]
                for _ in range(3):
                    during = control.get(f"/api/v1/travel/runs/{run_id}").json()
                    assert_cancelled_snapshot(during)
                replay_after = control.post("/api/v1/travel/live-runs", json=body,
                                            headers={"Idempotency-Key": "reachable-create"})
                assert_cancelled_snapshot(replay_after.json())
            finally:
                release.set()
                thread.join(timeout=20)
            assert not thread.is_alive()
            final = result["response"]
            assert final.status_code == 202
            data = final.json()
            assert data["mode"] == "live"
            assert_cancelled_snapshot(data)
            assert data["budget"]["tool_calls"] == 1          # 实际计数保留
            assert [item["tool"] for item in data["tool_results"]] == ["origin"]
            # 检查后竞争：下一发送未命中传输层。
            assert boundary.sent == ["/v3/geocode/geo"]
            finished = [item for item in store.get_events(run_id)
                        if item["action"] == "LIVE_FINISHED"]
            assert finished and "status=cancelled" in finished[-1]["reason"]
            after = control.get(f"/api/v1/travel/runs/{run_id}").json()
            assert_cancelled_snapshot(after)
            assert after["budget"]["tool_calls"] == 1
            replay_final = control.post("/api/v1/travel/live-runs", json=body,
                                        headers={"Idempotency-Key": "reachable-create"}).json()
            assert replay_final["run_id"] == run_id
            assert replay_final["events"] == data["events"]  # 重放不新增事件
            assert len(factory_calls) == 1
            assert boundary.sent == ["/v3/geocode/geo"]


def test_api_revision_replay_then_cancel_stops_child_http(store, worker):
    entered, release = Event(), Event()
    parent_adapter = FakeAdapter(mode="ambiguous")
    child_adapter = BlockingFakeAdapter(entered=entered, release=release)
    queue = [parent_adapter, child_adapter]
    factory_calls: list[str] = []

    def factory(city, transport):
        factory_calls.append(city)
        return queue.pop(0)

    app = _api(store, worker, factory)
    with serve(app) as base:
        with httpx.Client(base_url=base, timeout=20, trust_env=False) as original, \
                httpx.Client(base_url=base, timeout=20, trust_env=False) as control:
            parent = control.post("/api/v1/travel/live-runs", json=live_body(),
                                  headers={"Idempotency-Key": "revision-parent"}).json()
            assert parent["status"] == "needs_input"
            body = {"selected_poi_ids": {"合成乙": "B"}, "reason": "选择候选"}
            url = f"/api/v1/travel/runs/{parent['run_id']}/revisions"
            result: dict = {}

            def run_revision():
                result["response"] = original.post(
                    url, json=body, headers={"Idempotency-Key": "revision-1"})

            thread = Thread(target=run_revision, daemon=True)
            thread.start()
            try:
                assert entered.wait(15)
                replay = control.post(url, json=body,
                                      headers={"Idempotency-Key": "revision-1"})
                assert replay.status_code == 202
                assert replay.json()["replayed"] is True
                child_id = replay.json()["run_id"]
                assert replay.json()["mode"] == "live"
                events_before = len(replay.json()["events"])
                assert len(factory_calls) == 2
                assert child_adapter.sent == []
                again = control.post(url, json=body,
                                      headers={"Idempotency-Key": "revision-1"})
                assert again.json()["run_id"] == child_id
                assert len(again.json()["events"]) == events_before
                assert len(factory_calls) == 2
                cancel = control.post(f"/api/v1/travel/runs/{child_id}/cancel")
                assert cancel.status_code == 200
                assert_live_cancel_wording(cancel.json())
                assert_cancelled_snapshot(cancel.json())
                for _ in range(2):
                    during = control.get(f"/api/v1/travel/runs/{child_id}").json()
                    assert_cancelled_snapshot(during)
            finally:
                release.set()
                thread.join(timeout=20)
            assert not thread.is_alive()
            data = result["response"].json()
            assert data["mode"] == "live"
            assert data["parent_run_id"] == parent["run_id"]
            assert data["revision"] == 2
            assert_cancelled_snapshot(data)
            assert data["budget"]["tool_calls"] == 0
            assert child_adapter.sent == []           # 下一handler未命中
            parent_after = control.get(f"/api/v1/travel/runs/{parent['run_id']}").json()
            assert parent_after["status"] == "needs_input"
            cancelled = [item for item in store.get_events(child_id)
                         if item["action"] == "CANCELLED"]
            assert cancelled and "LIVE" in cancelled[0]["reason"]


def test_cancel_after_final_check_normalizes_atomic_terminal(store, worker):
    clock = BlockingFinalClock()
    boundary = ProviderTransport()
    factory_calls: list[str] = []

    def factory(city, transport):
        factory_calls.append(city)
        return BlockingCloseAmapAdapter(
            AmapClient(key="synthetic-example", transport=boundary),
            city=city, transport=transport, owns_client=True, clock=clock)

    app = _api(store, worker, factory, clock)
    with serve(app) as base:
        body = live_body()
        with httpx.Client(base_url=base, timeout=25, trust_env=False) as original, \
                httpx.Client(base_url=base, timeout=25, trust_env=False) as control:
            result: dict = {}

            def run_original():
                result["response"] = original.post(
                    "/api/v1/travel/live-runs", json=body,
                    headers={"Idempotency-Key": "final-race"})

            thread = Thread(target=run_original, daemon=True)
            thread.start()
            try:
                # 全部工具已完成；收尾close后的最后一次check被barrier挡住。
                assert clock.blocked.wait(20)
                replay = control.post("/api/v1/travel/live-runs", json=body,
                                      headers={"Idempotency-Key": "final-race"})
                run_id = replay.json()["run_id"]
                assert replay.json()["replayed"] is True
                assert len(factory_calls) == 1
                assert len(boundary.sent) == 15
                cancel = control.post(f"/api/v1/travel/runs/{run_id}/cancel")
                assert cancel.status_code == 200
                assert_live_cancel_wording(cancel.json())
                assert_cancelled_snapshot(cancel.json())
                # 独立连接的多次GET：每次都必须读到归一快照，不能先混合后修补。
                for _ in range(5):
                    during = control.get(f"/api/v1/travel/runs/{run_id}").json()
                    assert_cancelled_snapshot(during)
                replayed = control.post("/api/v1/travel/live-runs", json=body,
                                        headers={"Idempotency-Key": "final-race"}).json()
                assert_cancelled_snapshot(replayed)
                assert replayed["run_id"] == run_id
            finally:
                clock.release.set()
                thread.join(timeout=25)
            assert not thread.is_alive()
            data = result["response"].json()
            assert data["mode"] == "live"
            assert_cancelled_snapshot(data)
            assert data["budget"]["tool_calls"] == 15          # 实际计数
            assert {item["tool"] for item in data["tool_results"]} >= {
                "origin", "poi", "weather", "hours", "routes"}  # 工具证据保留
            assert data["budget"]["elapsed_seconds"] > 0
            assert len(boundary.sent) == 15                    # 收尾不再发送
            after = control.get(f"/api/v1/travel/runs/{run_id}").json()
            assert_cancelled_snapshot(after)
            assert after["budget"]["tool_calls"] == 15
            finished = [item for item in store.get_events(run_id)
                        if item["action"] == "LIVE_FINISHED"]
            assert finished and "status=cancelled" in finished[-1]["reason"]


def test_cancel_wins_over_in_memory_exhaustion_and_drops_reason(store, worker, monkeypatch):
    import app.live as live_module
    monkeypatch.setattr(live_module, "LIVE_MAX_TOOL_CALLS", 1)
    entered, release = Event(), Event()
    boundary = ProviderTransport()

    def factory(city, transport):
        return GatedCloseAmapAdapter(
            AmapClient(key="synthetic-example", transport=boundary),
            city=city, transport=transport, owns_client=True,
            entered=entered, release=release)

    app = _api(store, worker, factory)
    with serve(app) as base:
        body = live_body()
        with httpx.Client(base_url=base, timeout=25, trust_env=False) as original, \
                httpx.Client(base_url=base, timeout=25, trust_env=False) as control:
            result: dict = {}

            def run_original():
                result["response"] = original.post(
                    "/api/v1/travel/live-runs", json=body,
                    headers={"Idempotency-Key": "exhausted-cancel"})

            thread = Thread(target=run_original, daemon=True)
            thread.start()
            try:
                assert entered.wait(20)   # call_limit已在内存中分类，清理被挡住
                replay = control.post("/api/v1/travel/live-runs", json=body,
                                      headers={"Idempotency-Key": "exhausted-cancel"})
                run_id = replay.json()["run_id"]
                cancel = control.post(f"/api/v1/travel/runs/{run_id}/cancel")
                assert cancel.status_code == 200
                assert_cancelled_snapshot(cancel.json())
                assert len(boundary.sent) == 1
                for _ in range(3):
                    during = control.get(f"/api/v1/travel/runs/{run_id}").json()
                    assert_cancelled_snapshot(during)
            finally:
                release.set()
                thread.join(timeout=25)
            assert not thread.is_alive()
            data = result["response"].json()
            assert_cancelled_snapshot(data)
            assert data["budget"]["tool_calls"] == 1
            assert len(boundary.sent) == 1
            # 原诊断保留在issues，但不混入budget主分类。
            assert any(issue["code"] == "BUDGET_EXHAUSTED" for issue in data["issues"])
            after = control.get(f"/api/v1/travel/runs/{run_id}").json()
            assert_cancelled_snapshot(after)
