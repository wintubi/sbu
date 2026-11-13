"""Task 3：异常资源收尾与脱敏。

全部离线：真实 ``AmapAdapter`` + ``httpx.MockTransport`` 合成供应商、协议 fake、
可注入失败步骤。所有敏感标记都是合成字符串，断言 API 响应、持久 state 与事件
都不回显它们；不访问真实供应商。
"""
from __future__ import annotations

import json
import sqlite3

import httpx
from fastapi.testclient import TestClient

from app.amap_tools import AmapAdapter, AmapClient
from app.domain import ToolResult, ToolStatus, utc_now
from app.live import create_live_run
from app.main import create_app

SECRET_KEY = "SECRET-KEY-7f3a"
SECRET_QUERY = f"/v3/geocode/geo?key={SECRET_KEY}&private=PRIVATE-PARAM"
PRIVATE_MARK = "PRIVATE-MARKER-9c1d"


def live_body() -> dict:
    return {
        "mode": "live", "city": "北京", "date": "2026-11-09", "timezone": "Asia/Shanghai",
        "origin": "合成起点", "transport": "walking",
        "time_window": {"start": "2026-11-09T09:00:00+08:00",
                        "end": "2026-11-09T18:00:00+08:00"},
        "candidates": [{"name": name, "stay_seconds": 600}
                       for name in ("合成甲", "合成乙", "合成丙")],
    }


class FakeClock:
    def __init__(self, value: float = 0.0):
        self.value = value

    def __call__(self) -> float:
        return self.value


class OffsetClock:
    def __init__(self):
        self.offset = 0.0

    def __call__(self) -> float:
        import time
        return time.monotonic() + self.offset


class RecordingTransport(httpx.MockTransport):
    """合成供应商：记录真实发送与物理关闭尝试。"""

    def __init__(self):
        self.sent: list[str] = []
        self.close_attempts = 0
        self.on_request = None
        super().__init__(self._handle)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        assert request.url.params["key"] == "synthetic-example"
        self.sent.append(request.url.path)
        if self.on_request is not None:
            self.on_request(request)
        path = request.url.path
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

    def close(self) -> None:
        self.close_attempts += 1
        super().close()


class FailingCloseTransport(RecordingTransport):
    def __init__(self, *, on_close=None):
        super().__init__()
        self.on_close = on_close

    def close(self) -> None:
        self.close_attempts += 1
        if self.on_close is not None:
            self.on_close()
        raise OSError(f"synthetic close failure {PRIVATE_MARK} {SECRET_QUERY}")


class UnbindFailingClient(AmapClient):
    """解绑步骤抛含敏感文本的异常；物理close仍应独立尝试。"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.unbind_failures = 0

    def _detach_locked(self, runtime, *, owns_client):
        if owns_client and not self.unbind_failures:
            self.unbind_failures += 1
            raise RuntimeError(f"synthetic unbind failure {PRIVATE_MARK} {SECRET_QUERY}")
        return super()._detach_locked(runtime, owns_client=owns_client)


class ProtocolAdapter:
    """协议 fake：显式逐HTTP准入，可制造顶层异常。"""

    def __init__(self, *, explode: bool = False, close_error: Exception | None = None):
        self.explode = explode
        self.close_error = close_error
        self.bind_calls = 0
        self.close_calls = 0
        self._runtime = None

    def bind_runtime(self, runtime):
        self.bind_calls += 1
        self._runtime = runtime

    def close(self):
        self.close_calls += 1
        self._runtime = None
        if self.close_error is not None:
            raise self.close_error

    def resolve_origin(self, address):
        if self.explode:
            raise RuntimeError(f"top-level execution {PRIVATE_MARK} {SECRET_QUERY}")
        self._runtime.reserve_http(5.0)
        return ToolResult(status=ToolStatus.VALID, source_ref="fake:origin",
                          fetched_at=utc_now(),
                          payload={"poi": {"name": address, "city": "北京",
                                           "coordinates": {"lon": 116.4, "lat": 39.9}}})

    # 其余工具在 origin 之后才会被调用；这里给最小实现避免误导。
    def poi_lookup(self, key, selected_poi_id=None):
        raise AssertionError("fixture only exercises origin")

    def weather(self, target_date):
        raise AssertionError("fixture only exercises origin")

    def hours(self):
        raise AssertionError("fixture only exercises origin")

    def matrix(self, pairs):
        raise AssertionError("fixture only exercises origin")


class ProbeFailingStore:
    """取消探针读取失败（含敏感文本）；其余Store调用委派真实实现。"""

    def __init__(self, inner):
        object.__setattr__(self, "_inner", inner)

    def probe_run_status(self, run_id):
        raise RuntimeError(f"probe boom {PRIVATE_MARK} {SECRET_QUERY}")

    def __getattr__(self, name):
        return getattr(object.__getattribute__(self, "_inner"), name)


def owned_adapter(transport=None, *, client_cls=AmapClient):
    transport = transport if transport is not None else RecordingTransport()
    client = client_cls(key="synthetic-example", transport=transport)
    return AmapAdapter(client, city="北京", transport="walking", owns_client=True), transport


def api_with(store, worker, factory, clock=None):
    return create_app(store=store, worker=worker, manual_drain=True,
                      live_adapter_factory=factory, live_clock=clock)


def post_live(api, key: str, body: dict | None = None):
    return api.post("/api/v1/travel/live-runs", json=body or live_body(),
                    headers={"Idempotency-Key": key})


# --------------------------------------------------------------------------- #
# 3.1 六类出口：自有资源各有一次清理尝试
# --------------------------------------------------------------------------- #
def test_success_exit_closes_owned_client_once(store, worker):
    adapter, boundary = owned_adapter()
    with TestClient(api_with(store, worker, lambda city, transport: adapter)) as api:
        data = post_live(api, "exit-success").json()
    assert data["status"] == "completed"
    assert data["budget"]["tool_calls"] == len(boundary.sent) == 15
    assert boundary.close_attempts == 1
    assert adapter.client._state == "closed"


def test_provider_error_exit_closes_owned_client_once(store, worker):
    class ProviderErrorTransport(RecordingTransport):
        def _handle(self, request):
            self.sent.append(request.url.path)
            return httpx.Response(200, json={"status": "0", "info": PRIVATE_MARK,
                                             "infocode": "10013"})

    transport = ProviderErrorTransport()
    adapter, _ = owned_adapter(transport)
    with TestClient(api_with(store, worker, lambda city, transport: adapter)) as api:
        data = post_live(api, "exit-provider").json()
    assert data["status"] == "failed"
    assert data["budget"]["status"] == "failed"
    assert data["budget"]["tool_calls"] == 1
    assert any(issue["code"] == "TOOL_PROVIDER_ERROR" for issue in data["issues"])
    assert transport.close_attempts == 1


def test_call_limit_exit_closes_owned_client_once(store, worker, monkeypatch):
    import app.live as live_module
    monkeypatch.setattr(live_module, "LIVE_MAX_TOOL_CALLS", 1)
    adapter, boundary = owned_adapter()
    with TestClient(api_with(store, worker, lambda city, transport: adapter)) as api:
        data = post_live(api, "exit-limit").json()
    assert data["status"] == "failed"
    assert data["budget"]["status"] == "exhausted"
    assert data["budget"]["exhaustion_reason"] == "call_limit"
    assert data["budget"]["tool_calls"] == len(boundary.sent) == 1
    assert boundary.close_attempts == 1


def test_deadline_exit_closes_owned_client_once(store, worker):
    clock = OffsetClock()
    boundary = RecordingTransport()
    boundary.on_request = lambda request: setattr(clock, "offset", 91.0)
    adapter, _ = owned_adapter(boundary)
    with TestClient(api_with(store, worker, lambda city, transport: adapter, clock)) as api:
        data = post_live(api, "exit-deadline").json()
    assert data["status"] == "failed"
    assert data["budget"]["status"] == "exhausted"
    assert data["budget"]["exhaustion_reason"] == "deadline"
    assert data["budget"]["tool_calls"] == 1
    assert boundary.close_attempts == 1


def test_cancel_exit_closes_owned_client_once(store, worker):
    boundary = RecordingTransport()

    def cancel_run(request):
        if len(boundary.sent) == 1:  # 第一次发送返回后，持久状态被取消
            run_id = store.list_runs()[-1]["run_id"]
            assert store.cancel_run(run_id) == "ok"

    boundary.on_request = cancel_run
    adapter, _ = owned_adapter(boundary)
    with TestClient(api_with(store, worker, lambda city, transport: adapter)) as api:
        data = post_live(api, "exit-cancel").json()
    assert data["status"] == "cancelled"
    assert data["budget"]["status"] == "cancelled"
    assert data["budget"]["tool_calls"] == 1
    assert data["quality_status"] == "unverified" and data["result"] is None
    assert boundary.close_attempts == 1


def test_constructor_validation_failure_closes_owned_client_and_is_idempotent(store, worker):
    boundary = RecordingTransport()
    created: dict = {}

    def factory(city, transport):
        client = AmapClient(key="synthetic-example", transport=boundary)
        created["client"] = client
        # 构造校验失败：AmapAdapter 在返回对象前清理已移交的自有client。
        return AmapAdapter(client, city=city, transport="flying", owns_client=True)

    with TestClient(api_with(store, worker, factory)) as api:
        data = post_live(api, "exit-constructor").json()
    assert data["status"] == "failed"
    assert data["issues"][0]["code"] == "STAGE_EXECUTION_ERROR"
    assert data["budget"]["tool_calls"] == 0
    assert boundary.sent == [] and boundary.close_attempts == 1
    # close幂等：构造失败路径已关闭后，再次显式关闭不增加物理关闭次数。
    created["client"].close()
    assert boundary.close_attempts == 1


def test_factory_failure_before_return_owns_its_unreturned_resources(store, worker):
    boundary = RecordingTransport()
    calls = {"factory": 0, "factory_close": 0}

    def factory(city, transport):
        calls["factory"] += 1
        client = AmapClient(key="synthetic-example", transport=boundary)
        try:
            raise RuntimeError(f"factory failed before returning {PRIVATE_MARK} {SECRET_QUERY}")
        finally:
            # 未交出的资源由factory负责；顶层无法也不会关闭未知对象。
            client.close()
            calls["factory_close"] += 1

    with TestClient(api_with(store, worker, factory)) as api:
        data = post_live(api, "factory-failure").json()
    assert data["status"] == "failed"
    assert data["issues"][0]["code"] == "STAGE_EXECUTION_ERROR"
    assert data["budget"]["tool_calls"] == 0 and boundary.sent == []
    assert calls == {"factory": 1, "factory_close": 1}
    assert boundary.close_attempts == 1  # 恰好一次，顶层没有二次关闭
    assert PRIVATE_MARK not in json.dumps(data, ensure_ascii=False)
    assert SECRET_KEY not in json.dumps(data, ensure_ascii=False)


def test_borrowed_client_is_not_closed_and_reused_sequentially(store, worker):
    boundary = RecordingTransport()
    client = AmapClient(key="synthetic-example", transport=boundary)

    def factory(city, transport):
        return AmapAdapter(client, city=city, transport=transport)  # 借入，无拥有权

    with TestClient(api_with(store, worker, factory)) as api:
        first = post_live(api, "borrowed-1").json()
        second = post_live(api, "borrowed-2").json()
    assert first["status"] == second["status"] == "completed"
    assert boundary.close_attempts == 0
    assert client._state == "open"
    assert client.calls == first["budget"]["tool_calls"] + second["budget"]["tool_calls"] == 30
    client.close()  # 原拥有者决定关闭
    assert boundary.close_attempts == 1


# --------------------------------------------------------------------------- #
# 3.2 解绑/关闭异常、主结果保留与固定警告
# --------------------------------------------------------------------------- #
def test_unbind_failure_still_attempts_physical_close_and_keeps_result(store, worker):
    boundary = RecordingTransport()
    client = UnbindFailingClient(key="synthetic-example", transport=boundary)
    adapter = AmapAdapter(client, city="北京", transport="walking", owns_client=True)
    with TestClient(api_with(store, worker, lambda city, transport: adapter)) as api:
        data = post_live(api, "unbind-failure").json()
    assert client.unbind_failures == 1
    assert boundary.close_attempts == 1          # 解绑失败没有跳过物理关闭尝试
    assert data["status"] == "completed"         # 主结果保留
    warning = [issue for issue in data["issues"] if issue["code"] == "RESOURCE_CLEANUP_FAILED"]
    assert len(warning) == 1
    assert "RuntimeError" in warning[0]["message"]
    assert PRIVATE_MARK not in json.dumps(data, ensure_ascii=False)
    assert SECRET_KEY not in json.dumps(data, ensure_ascii=False)
    reread = api.get(f"/api/v1/travel/runs/{data['run_id']}").json()
    assert any(issue["code"] == "RESOURCE_CLEANUP_FAILED" for issue in reread["issues"])


def test_cleanup_failure_preserves_primary_provider_failure_and_budget(store, worker):
    class ProviderErrorCloseTransport(FailingCloseTransport):
        def _handle(self, request):
            self.sent.append(request.url.path)
            return httpx.Response(200, json={"status": "0", "info": "boom", "infocode": "10013"})

    boundary = ProviderErrorCloseTransport()
    adapter, _ = owned_adapter(boundary)
    with TestClient(api_with(store, worker, lambda city, transport: adapter)) as api:
        data = post_live(api, "cleanup-provider").json()
        reread = api.get(f"/api/v1/travel/runs/{data['run_id']}").json()
    assert data["status"] == "failed"
    assert data["budget"]["status"] == "failed"       # 原主失败未被清理失败覆盖
    assert "exhaustion_reason" not in data["budget"]
    assert data["budget"]["tool_calls"] == len(boundary.sent) == 1
    codes = [issue["code"] for issue in data["issues"]]
    assert "TOOL_PROVIDER_ERROR" in codes and "RESOURCE_CLEANUP_FAILED" in codes
    assert boundary.close_attempts == 1
    warning = next(issue for issue in data["issues"] if issue["code"] == "RESOURCE_CLEANUP_FAILED")
    assert warning["severity"] == "warning"
    assert "OSError" in warning["message"] and "未知" in warning["message"]
    assert "已释放" not in warning["message"]
    # finally中的清理异常没有跳过保存：DB重读与响应一致，LIVE_FINISHED仍在。
    assert reread["status"] == reread["budget"]["status"] == "failed"
    assert reread["budget"]["tool_calls"] == 1
    assert any(issue["code"] == "RESOURCE_CLEANUP_FAILED" for issue in reread["issues"])
    events = store.get_events(data["run_id"])
    assert any(item["action"] == "LIVE_FINISHED" and "status=failed" in item["reason"]
               for item in events)
    dumped = json.dumps(data, ensure_ascii=False) + json.dumps(reread, ensure_ascii=False)
    assert PRIVATE_MARK not in dumped and SECRET_KEY not in dumped


def test_cleanup_failure_preserves_call_limit_category_and_exact_count(store, worker, monkeypatch):
    import app.live as live_module
    monkeypatch.setattr(live_module, "LIVE_MAX_TOOL_CALLS", 1)
    boundary = FailingCloseTransport()
    adapter, _ = owned_adapter(boundary)
    with TestClient(api_with(store, worker, lambda city, transport: adapter)) as api:
        data = post_live(api, "cleanup-limit").json()
    assert data["status"] == "failed"
    assert data["budget"]["status"] == "exhausted"
    assert data["budget"]["exhaustion_reason"] == "call_limit"
    assert data["budget"]["tool_calls"] == len(boundary.sent) == 1
    codes = [issue["code"] for issue in data["issues"]]
    assert "BUDGET_EXHAUSTED" in codes and "RESOURCE_CLEANUP_FAILED" in codes
    assert boundary.close_attempts == 1


def test_close_error_with_deadline_during_cleanup_keeps_earlier_failure(store, worker):
    """[Review Focus] close异常含敏感文本且总deadline在清理期间到达。"""
    clock = OffsetClock()

    class ProviderErrorSlowClose(FailingCloseTransport):
        def _handle(self, request):
            self.sent.append(request.url.path)
            return httpx.Response(200, json={"status": "0", "info": "boom", "infocode": "10013"})

    boundary = ProviderErrorSlowClose()
    boundary.on_close = lambda: setattr(clock, "offset", 91.0)
    adapter, _ = owned_adapter(boundary)
    with TestClient(api_with(store, worker, lambda city, transport: adapter, clock)) as api:
        data = post_live(api, "review-focus").json()
        reread = api.get(f"/api/v1/travel/runs/{data['run_id']}").json()
    assert data["status"] == "failed"
    assert data["budget"]["status"] == "failed"       # 更早主失败保留
    assert "exhaustion_reason" not in data["budget"]
    assert data["budget"]["tool_calls"] == 1
    assert data["budget"]["elapsed_seconds"] >= 90    # 清理期间确实越过deadline
    codes = [issue["code"] for issue in data["issues"]]
    assert "TOOL_PROVIDER_ERROR" in codes
    assert "BUDGET_EXHAUSTED" not in codes
    assert "RESOURCE_CLEANUP_FAILED" in codes
    warning = next(issue for issue in data["issues"] if issue["code"] == "RESOURCE_CLEANUP_FAILED")
    assert warning["message"].endswith("资源是否释放未知")
    assert PRIVATE_MARK not in json.dumps(data, ensure_ascii=False)
    assert SECRET_KEY not in json.dumps(data, ensure_ascii=False)
    # 持久化仍被尝试，且事件理由取canonical状态。
    assert reread["status"] == "failed" and reread["budget"] == data["budget"]
    finished = [item for item in store.get_events(data["run_id"])
                if item["action"] == "LIVE_FINISHED"]
    assert finished and "status=failed" in finished[-1]["reason"]
    assert boundary.close_attempts == 1


def test_cleanup_past_deadline_still_rejects_stale_success_terminal(store, worker):
    clock = OffsetClock()

    class SlowCloseSuccess(RecordingTransport):
        def close(self):
            setattr(clock, "offset", 91.0)
            super().close()

    boundary = SlowCloseSuccess()
    adapter, _ = owned_adapter(boundary)
    with TestClient(api_with(store, worker, lambda city, transport: adapter, clock)) as api:
        data = post_live(api, "stale-success").json()
    assert data["status"] == "failed"
    assert data["budget"]["status"] == "exhausted"
    assert data["budget"]["exhaustion_reason"] == "deadline"
    assert data["quality_status"] == "unverified" and data["result"] is None
    assert data["budget"]["tool_calls"] == 15            # 实际计数保留
    assert data["tool_results"]                          # 已有工具证据保留
    assert boundary.close_attempts == 1


# --------------------------------------------------------------------------- #
# 3.2 脱敏：HTTPError / provider info / 顶层异常 / 探针 / cleanup
# --------------------------------------------------------------------------- #
def _db_text(db_path: str) -> str:
    con = sqlite3.connect(db_path)
    try:
        rows = []
        for table in ("runs", "events"):
            for row in con.execute(f"SELECT * FROM {table}"):
                rows.append(" | ".join(str(value) for value in row))
        return "\n".join(rows)
    finally:
        con.close()


def _assert_no_secrets(*texts: str) -> None:
    for text in texts:
        for marker in (SECRET_KEY, "SECRET-QUERY", "PRIVATE-MARKER", "PRIVATE-PARAM",
                       "?key=", SECRET_QUERY):
            assert marker not in text, f"leaked {marker!r}"


def test_httpx_error_text_is_reduced_to_safe_category_and_type(store, worker):
    class HttpErrorTransport(RecordingTransport):
        def _handle(self, request):
            self.sent.append(request.url.path)
            raise httpx.ConnectError(
                f"connect failed {PRIVATE_MARK} {SECRET_QUERY}", request=request)

    boundary = HttpErrorTransport()
    adapter, _ = owned_adapter(boundary)
    with TestClient(api_with(store, worker, lambda city, transport: adapter)) as api:
        data = post_live(api, "http-error").json()
        reread = api.get(f"/api/v1/travel/runs/{data['run_id']}").json()
    assert data["status"] == "failed"
    assert data["budget"]["tool_calls"] == 1
    assert any(issue["code"] == "TOOL_PROVIDER_ERROR" for issue in data["issues"])  # 分类不变
    messages = [issue["message"] for issue in data["issues"]]
    assert any("ConnectError" in message for message in messages)
    _assert_no_secrets(json.dumps(data, ensure_ascii=False),
                       json.dumps(reread, ensure_ascii=False),
                       _db_text(store.db_path))


def test_provider_info_is_not_echoed_but_numeric_infocode_is_kept(store, worker):
    class ProviderTextTransport(RecordingTransport):
        def _handle(self, request):
            self.sent.append(request.url.path)
            return httpx.Response(200, json={
                "status": "0", "info": f"USER_KEY {PRIVATE_MARK} {SECRET_QUERY}",
                "infocode": "10013"})

    boundary = ProviderTextTransport()
    adapter, _ = owned_adapter(boundary)
    with TestClient(api_with(store, worker, lambda city, transport: adapter)) as api:
        data = post_live(api, "provider-text").json()
        reread = api.get(f"/api/v1/travel/runs/{data['run_id']}").json()
    issue = next(issue for issue in data["issues"] if issue["code"] == "TOOL_PROVIDER_ERROR")
    assert "10013" in issue["message"]                    # 校验后的数字码可留
    _assert_no_secrets(json.dumps(data, ensure_ascii=False),
                       json.dumps(reread, ensure_ascii=False),
                       _db_text(store.db_path))

    class BadInfocodeTransport(RecordingTransport):
        def _handle(self, request):
            self.sent.append(request.url.path)
            return httpx.Response(200, json={
                "status": "0", "info": f"{PRIVATE_MARK} {SECRET_QUERY}",
                "infocode": f"10013-{PRIVATE_MARK}"})

    boundary2 = BadInfocodeTransport()
    adapter2, _ = owned_adapter(boundary2)
    with TestClient(api_with(store, worker, lambda city, transport: adapter2)) as api:
        data2 = post_live(api, "provider-bad-code").json()
    issue2 = next(issue for issue in data2["issues"] if issue["code"] == "TOOL_PROVIDER_ERROR")
    assert "10013" not in issue2["message"]
    assert issue2["message"].endswith("provider error")
    _assert_no_secrets(json.dumps(data2, ensure_ascii=False),
                       _db_text(store.db_path))


def test_top_level_execution_exception_text_is_not_persisted(store, worker):
    adapter = ProtocolAdapter(explode=True)
    with TestClient(api_with(store, worker, lambda city, transport: adapter)) as api:
        data = post_live(api, "top-level").json()
        reread = api.get(f"/api/v1/travel/runs/{data['run_id']}").json()
    assert data["status"] == "failed"
    assert data["issues"][0]["code"] == "STAGE_EXECUTION_ERROR"
    assert "RuntimeError" in data["issues"][0]["message"]
    assert data["budget"]["tool_calls"] == 0
    assert adapter.close_calls == 1
    _assert_no_secrets(json.dumps(data, ensure_ascii=False),
                       json.dumps(reread, ensure_ascii=False),
                       _db_text(store.db_path))


def test_cancel_probe_failure_does_not_leak_raw_exception(store, worker):
    proxy = ProbeFailingStore(store)
    factory_calls: list[str] = []

    def factory(city, transport):
        factory_calls.append(city)
        return ProtocolAdapter()

    with TestClient(api_with(proxy, worker, factory)) as api:
        data = post_live(api, "probe-failure").json()
        reread = api.get(f"/api/v1/travel/runs/{data['run_id']}").json()
    assert data["status"] == "failed"
    assert data["issues"][0]["code"] == "STAGE_EXECUTION_ERROR"
    assert "CANCEL_PROBE_READ_FAILED" in data["issues"][0]["message"]
    assert "RuntimeError" in data["issues"][0]["message"]
    assert data["budget"]["tool_calls"] == 0
    assert factory_calls == []                    # 探针失败在factory之前停止
    _assert_no_secrets(json.dumps(data, ensure_ascii=False),
                       json.dumps(reread, ensure_ascii=False),
                       _db_text(store.db_path))


def test_cleanup_exception_text_is_not_persisted(store, worker):
    boundary = FailingCloseTransport()
    adapter, _ = owned_adapter(boundary)
    with TestClient(api_with(store, worker, lambda city, transport: adapter)) as api:
        data = post_live(api, "cleanup-text").json()
        reread = api.get(f"/api/v1/travel/runs/{data['run_id']}").json()
    warning = next(issue for issue in data["issues"] if issue["code"] == "RESOURCE_CLEANUP_FAILED")
    assert "OSError" in warning["message"]
    assert "未知" in warning["message"]
    _assert_no_secrets(json.dumps(data, ensure_ascii=False),
                       json.dumps(reread, ensure_ascii=False),
                       _db_text(store.db_path))


# --------------------------------------------------------------------------- #
# 直接创建路径：cleanup异常不会跳过保存（不依赖HTTP层）
# --------------------------------------------------------------------------- #
class _Factory:
    def __init__(self, adapter):
        self.adapter = adapter

    def __call__(self, city, transport):
        return self.adapter


def test_direct_create_live_run_saves_after_cleanup_failure(store):
    from app.domain import LiveTravelRequest

    boundary = FailingCloseTransport()
    adapter, _ = owned_adapter(boundary)
    request = LiveTravelRequest.model_validate(live_body())
    run, created = create_live_run(store, request, _Factory(adapter), "direct-cleanup")
    assert created is True
    persisted = store.get_run(run["run_id"])
    assert persisted is not None
    assert persisted["status"] == "completed"
    codes = [issue["code"] for issue in persisted["state"]["issues"]]
    assert "RESOURCE_CLEANUP_FAILED" in codes
    assert persisted["budget"]["tool_calls"] == len(boundary.sent) == 15
    _assert_no_secrets(json.dumps(persisted, ensure_ascii=False), _db_text(store.db_path))
