"""Task 1公共契约：只用合成凭据及MockTransport，不访问供应商。"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from types import SimpleNamespace

import httpx
import pytest

from fastapi.testclient import TestClient

from app.amap_tools import AmapAdapter, AmapClient
from app.domain import DEFAULT_BUDGET
from app.main import create_app


def live_body():
    return {
        "mode": "live", "city": "北京", "date": "2026-11-09", "timezone": "Asia/Shanghai",
        "origin": "合成起点", "transport": "walking",
        "time_window": {"start": "2026-11-09T09:00:00+08:00",
                        "end": "2026-11-09T18:00:00+08:00"},
        "candidates": [{"name": name, "stay_seconds": 600} for name in ("合成甲", "合成乙", "合成丙")],
    }


class ProviderTransport(httpx.MockTransport):
    """只模拟供应商边界，同时观测实际发送与物理关闭。"""
    def __init__(self):
        self.sent = []
        self.close_attempts = 0
        super().__init__(self.handle)

    def handle(self, request):
        assert request.url.params["key"] == "synthetic-example"
        self.sent.append(request.url.path)
        path = request.url.path
        if path == "/v3/geocode/geo":
            data = {"geocodes": [{"location": "116.4,39.9", "city": "北京", "adcode": "110000"}]}
        elif path == "/v3/place/text":
            name = request.url.params["keywords"]
            data = {"pois": [{"id": name, "name": name, "cityname": "北京", "location": "116.4,39.9"}]}
        elif path == "/v3/place/detail":
            data = {"pois": [{"biz_ext": {"open_time": "09:00-18:00"}}]}
        elif path == "/v3/weather/weatherInfo":
            data = {"forecasts": [{"casts": [{"date": "2026-11-09", "dayweather": "晴"}]}]}
        else:
            assert path == "/v3/direction/walking"
            data = {"route": {"paths": [{"duration": "60", "distance": "100"}]}}
        return httpx.Response(200, json={"status": "1", **data})

    def close(self):
        self.close_attempts += 1
        super().close()


def test_real_adapter_api_exact_budget_and_replay(store, worker, monkeypatch):
    import app.live as live
    monkeypatch.setattr(live, "LIVE_MAX_TOOL_CALLS", 15)
    transports = []

    def factory(city, transport):
        boundary = ProviderTransport()
        transports.append(boundary)
        return AmapAdapter(AmapClient(key="synthetic-example", transport=boundary),
                           city=city, transport=transport, owns_client=True)

    with TestClient(create_app(store=store, worker=worker, live_adapter_factory=factory)) as api:
        first = api.post("/api/v1/travel/live-runs", json=live_body(),
                         headers={"Idempotency-Key": "exact"})
        assert first.status_code == 202
        data = first.json()
        assert data["status"] == "completed"
        assert data["quality_status"] == "verified_feasible"
        assert data["budget"]["tool_calls"] == 15
        assert data["budget"]["status"] == "ok"
        assert len(transports[0].sent) == 15
        assert transports[0].close_attempts == 1
        reread = api.get(f"/api/v1/travel/runs/{data['run_id']}").json()
        assert reread["budget"] == data["budget"]
        assert reread["tool_results"] == data["tool_results"]
        replay = api.post("/api/v1/travel/live-runs", json=live_body(),
                          headers={"Idempotency-Key": "exact"}).json()
        assert replay["run_id"] == data["run_id"]
        assert replay["replayed"] is True
        assert replay["events"] == data["events"]
        assert len(transports) == 1
        assert len(transports[0].sent) == 15
        assert transports[0].close_attempts == 1


@pytest.mark.parametrize("limit,subtool,payload", [
    (7, "hours_detail", {"windows": {"合成甲": ["09:00", "18:00"]}}),
    (10, "route_leg", {"duration_seconds": 60, "distance_meters": 100,
                        "from": "__origin__", "to": "合成甲"}),
])
def test_api_interrupted_batch_keeps_normalized_evidence(store, worker, monkeypatch, limit, subtool, payload):
    import app.live as live
    monkeypatch.setattr(live, "LIVE_MAX_TOOL_CALLS", limit)
    boundary = ProviderTransport()
    adapter = AmapAdapter(AmapClient(key="synthetic-example", transport=boundary),
                          city="北京", owns_client=True)
    with TestClient(create_app(store=store, worker=worker,
                              live_adapter_factory=lambda city, transport: adapter)) as api:
        response = api.post("/api/v1/travel/live-runs", json=live_body(),
                            headers={"Idempotency-Key": "partial"})
        data = response.json()
        assert data["status"] == "failed"
        assert data["budget"]["status"] == "exhausted"
        assert data["budget"]["exhaustion_reason"] == "call_limit"
        assert data["budget"]["tool_calls"] == len(boundary.sent) == limit
        assert data["result"] is None
        assert data["quality_status"] == "unverified"
        reread = api.get(f"/api/v1/travel/runs/{data['run_id']}").json()
        evidence = [item for item in reread["tool_results"] if item["tool"] == subtool]
        assert len(evidence) == 1
        assert evidence[0]["payload"] == payload
        assert evidence[0]["source_ref"].startswith("amap:")
        assert evidence[0]["fetched_at"]
        assert not any(item["tool"] == ("hours" if subtool == "hours_detail" else "routes")
                       for item in reread["tool_results"])
        assert boundary.close_attempts == 1
        replay = api.post("/api/v1/travel/live-runs", json=live_body(),
                          headers={"Idempotency-Key": "partial"}).json()
        assert replay["run_id"] == data["run_id"]
        assert replay["events"] == data["events"]
        assert replay["tool_results"] == data["tool_results"]
        assert len(boundary.sent) == limit
        assert boundary.close_attempts == 1


def runtime_with(limit=40):
    from app.runtime import LiveRuntime
    return LiveRuntime({**DEFAULT_BUDGET, "max_tool_calls": limit})


@pytest.mark.parametrize("limit", [0, 1, 2, 40])
def test_http_boundaries_at_transport(limit):
    from app.runtime import BudgetExhausted
    runtime = runtime_with(limit)
    boundary = ProviderTransport()
    adapter = AmapAdapter(AmapClient(key="synthetic-example", transport=boundary), city="北京",
                          owns_client=True)
    adapter.bind_runtime(runtime)
    try:
        for _ in range(limit):
            adapter.client.get("/v3/geocode/geo", {})
        assert runtime.budget["tool_calls"] == len(boundary.sent) == limit
        with pytest.raises(BudgetExhausted):
            adapter.client.get("/v3/geocode/geo", {})
        assert runtime.budget["tool_calls"] == adapter.client.calls == len(boundary.sent) == limit
    finally:
        adapter.close()


@pytest.mark.parametrize("failure,expected", [("connect", "provider_error"), ("timeout", "timeout"),
                                               ("provider", "provider_error"), ("format", "format_error")])
def test_failed_admitted_attempts_still_count(failure, expected):
    sent = []

    def handler(request):
        sent.append(request.url.path)
        if failure == "connect":
            raise httpx.ConnectError("synthetic failure", request=request)
        if failure == "timeout":
            raise httpx.ReadTimeout("synthetic failure", request=request)
        if failure == "provider":
            return httpx.Response(200, json={"status": "0", "infocode": "10013"})
        return httpx.Response(200, text="invalid json")

    runtime = runtime_with(1)
    adapter = AmapAdapter(AmapClient(key="synthetic-example", transport=httpx.MockTransport(handler)),
                          city="北京", owns_client=True)
    adapter.bind_runtime(runtime)
    try:
        assert adapter.poi_lookup("合成甲").status.value == expected
        assert runtime.budget["tool_calls"] == adapter.client.calls == len(sent) == 1
    finally:
        adapter.close()


def test_local_empty_matrix_and_hours_consume_zero():
    runtime = runtime_with(0)
    boundary = ProviderTransport()
    adapter = AmapAdapter(AmapClient(key="synthetic-example", transport=boundary), city="北京",
                          owns_client=True)
    adapter.bind_runtime(runtime)
    try:
        assert adapter.matrix([]).payload == {"matrix": {}}
        assert adapter.hours().payload == {"windows": {}}
        assert adapter.leg("missing", "also missing").status.value == "unavailable"
        assert runtime.budget["tool_calls"] == adapter.client.calls == len(boundary.sent) == 0
    finally:
        adapter.close()


def test_weather_adcode_is_cached_but_http_forecast_is_not():
    runtime = runtime_with(3)
    boundary = ProviderTransport()
    adapter = AmapAdapter(AmapClient(key="synthetic-example", transport=boundary), city="北京",
                          owns_client=True)
    adapter.bind_runtime(runtime)
    try:
        assert adapter.weather("2026-11-09").status.value == "valid"
        assert adapter.weather("2026-11-09").status.value == "valid"
        assert boundary.sent == ["/v3/geocode/geo", "/v3/weather/weatherInfo", "/v3/weather/weatherInfo"]
        assert runtime.budget["tool_calls"] == adapter.client.calls == 3
    finally:
        adapter.close()


def test_bind_race_one_winner_and_failed_cleanup_preserves_owner():
    boundary = ProviderTransport()
    client = AmapClient(key="synthetic-example", transport=boundary)
    adapters = [AmapAdapter(client, city="北京", owns_client=True) for _ in range(2)]
    runtimes = [runtime_with(1), runtime_with(2)]
    start = Barrier(2)

    def bind(index):
        start.wait(timeout=5)
        try:
            adapters[index].bind_runtime(runtimes[index])
            return True
        except RuntimeError:
            return False

    with ThreadPoolExecutor(max_workers=2) as threads:
        futures = [threads.submit(bind, index) for index in range(2)]
        won = [future.result(timeout=5) for future in futures]
    assert sum(won) == 1
    winner = won.index(True)
    loser = won.index(False)
    adapters[loser].close()
    assert boundary.close_attempts == 0
    assert adapters[winner].resolve_origin("合成起点").status.value == "valid"
    assert runtimes[winner].budget["tool_calls"] == 1
    assert runtimes[loser].budget["tool_calls"] == 0
    adapters[winner].close()
    adapters[winner].close()
    assert boundary.close_attempts == 1


def test_reentrant_factory_object_failure_does_not_clean_active_owner(store, worker):
    boundary = ProviderTransport()
    adapter = AmapAdapter(AmapClient(key="synthetic-example", transport=boundary), city="北京",
                          owns_client=True)
    original = runtime_with(1)
    adapter.bind_runtime(original)
    try:
        with TestClient(create_app(store=store, worker=worker,
                                  live_adapter_factory=lambda city, transport: adapter)) as api:
            rejected = api.post("/api/v1/travel/live-runs", json=live_body()).json()
            assert rejected["status"] == "failed"
            assert rejected["issues"][0]["code"] == "STAGE_EXECUTION_ERROR"
            assert rejected["budget"]["tool_calls"] == 0
            assert len(boundary.sent) == boundary.close_attempts == 0
        assert adapter.resolve_origin("合成起点").status.value == "valid"
        assert original.budget["tool_calls"] == 1
    finally:
        adapter.close()
    assert boundary.close_attempts == 1


def test_borrowed_client_unbinds_for_sequential_runs_without_close():
    boundary = ProviderTransport()
    client = AmapClient(key="synthetic-example", transport=boundary)
    for limit in (1, 2):
        runtime = runtime_with(limit)
        adapter = AmapAdapter(client, city="北京")
        adapter.bind_runtime(runtime)
        assert adapter.resolve_origin("合成起点").status.value == "valid"
        adapter.close()
        adapter.close()
        assert runtime.budget["tool_calls"] == 1
        assert boundary.close_attempts == 0
    assert client.calls == 2
    client.close()
    assert boundary.close_attempts == 1


@pytest.mark.parametrize("fail_close", [False, True])
def test_owned_close_rejects_bind_while_physical_close_waits(fail_close):
    entered, finish = Event(), Event()

    class ClosingTransport(ProviderTransport):
        def close(self):
            super().close()
            entered.set()
            assert finish.wait(timeout=5)
            if fail_close:
                raise OSError("synthetic close failure")

    boundary = ClosingTransport()
    client = AmapClient(key="synthetic-example", transport=boundary)
    owner = AmapAdapter(client, city="北京", owns_client=True)
    owner.bind_runtime(runtime_with())
    with ThreadPoolExecutor(max_workers=1) as threads:
        closing = threads.submit(owner.close)
        try:
            assert entered.wait(timeout=5)
            rejected = AmapAdapter(client, city="北京", owns_client=True)
            with pytest.raises(RuntimeError):
                rejected.bind_runtime(runtime_with())
            rejected.close()
        finally:
            finish.set()
        if fail_close:
            with pytest.raises(OSError):
                closing.result(timeout=5)
        else:
            closing.result(timeout=5)
    with pytest.raises(RuntimeError):
        client.bind_runtime(runtime_with())
    owner.close()
    assert boundary.close_attempts == 1


def test_default_factory_owns_independent_client(store, worker, monkeypatch):
    """默认LIVE factory自己创建client并以owns_client=True移交，运行结束物理关闭一次。"""
    import app.main as main_module

    boundary = ProviderTransport()
    real_client = main_module.AmapClient
    monkeypatch.setenv("AMAP_API_KEY", "synthetic-example")
    monkeypatch.setattr(main_module, "AmapClient",
                        lambda: real_client(key="synthetic-example", transport=boundary))
    with TestClient(create_app(store=store, worker=worker)) as api:
        data = api.post("/api/v1/travel/live-runs", json=live_body(),
                        headers={"Idempotency-Key": "default-factory"}).json()
    assert data["status"] == "completed"
    assert data["budget"]["tool_calls"] == len(boundary.sent) == 15
    assert boundary.close_attempts == 1


def _protocol_spy(missing):
    calls = {"bind": 0, "tools": 0, "close": 0}

    def bind_runtime(runtime):
        calls["bind"] += 1

    def close():
        calls["close"] += 1

    def resolve_origin(address):
        calls["tools"] += 1
        raise AssertionError("缺少绑定协议时不得调用工具")

    attributes = {"bind_runtime": bind_runtime, "close": close, "resolve_origin": resolve_origin}
    attributes.pop(missing)
    return SimpleNamespace(**attributes), calls


@pytest.mark.parametrize("missing,expected_close", [("bind_runtime", 1), ("close", 0)])
def test_missing_binding_protocol_invokes_no_tool(store, worker, missing, expected_close):
    adapter, calls = _protocol_spy(missing)
    with TestClient(create_app(store=store, worker=worker,
                              live_adapter_factory=lambda city, transport: adapter)) as api:
        data = api.post("/api/v1/travel/live-runs", json=live_body(),
                        headers={"Idempotency-Key": f"protocol-{missing}"}).json()
    assert data["status"] == "failed"
    assert data["issues"][0]["code"] == "STAGE_EXECUTION_ERROR"
    assert data["budget"]["tool_calls"] == 0
    assert calls == {"bind": 0, "tools": 0, "close": expected_close}
    assert data["quality_status"] == "unverified"
    assert data["result"] is None


def test_http_limit_is_reserved_before_transport():
    from app.runtime import BudgetExhausted, LiveRuntime

    budget = {**DEFAULT_BUDGET, "max_tool_calls": 2}
    runtime = LiveRuntime(budget)
    sent = []

    def handler(request):
        sent.append(request.url.path)
        return httpx.Response(200, json={"status": "1"})

    client = AmapClient(key="synthetic-example", transport=httpx.MockTransport(handler))
    client.bind_runtime(runtime)
    try:
        client.get("/first", {})
        client.get("/second", {})
        with pytest.raises(BudgetExhausted, match="limit"):
            client.get("/rejected", {})
        assert sent == ["/first", "/second"]
        assert budget["tool_calls"] == client.calls == 2
    finally:
        client.unbind_runtime(runtime)
        client.close()
