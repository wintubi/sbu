"""独立进程 loopback 验收：创建 + LIVE 修订的并发 POST/同键重放/cancel/GET。

用法（只在本地回环，不访问真实供应商）::

    C:/Miniconda3/python.exe scripts/live_loopback_e2e.py

脚本自己启动**独立应用进程**（子进程 uvicorn，绑定 127.0.0.1:0，端口从子进程
stdout 握手取得，不假设端口空闲）。应用进程注入真实 ``AmapAdapter`` +
``httpx.MockTransport`` 合成供应商，并用显式合成 Key ``synthetic-example``；
即使调用者环境里设置了真实 ``AMAP_API_KEY``，该 factory 也不会读取或使用它。
取消只走真实 HTTP ``POST /api/v1/travel/runs/{run_id}/cancel``，不直接写 DB。

结束时只向自己启动的子进程发送 shutdown 并等待退出；子进程退出码、SQLite
记录、发送次数、关闭尝试与 HTTP 响应逐项核对。敏感凭据不写入输出。
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from threading import Thread

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

SYNTHETIC_KEY = "synthetic-example"
CREATE_KEY = "e2e-create-key"
REVISION_KEY = "e2e-revision-key"


def live_body() -> dict:
    return {
        "mode": "live", "city": "北京", "date": "2026-11-09", "timezone": "Asia/Shanghai",
        "origin": "合成起点", "transport": "walking",
        "time_window": {"start": "2026-11-09T09:00:00+08:00",
                        "end": "2026-11-09T18:00:00+08:00"},
        "candidates": [{"name": name, "stay_seconds": 600}
                       for name in ("合成甲", "合成乙", "合成丙")],
    }


def _wait_path(path: Path, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while not path.exists():
        if time.monotonic() > deadline:
            raise TimeoutError(f"timed out waiting for {path.name}")
        time.sleep(0.01)


def _touch(path: Path) -> None:
    path.write_text("1", encoding="utf-8")


# --------------------------------------------------------------------------- #
# 子进程模式：独立 uvicorn 应用进程
# --------------------------------------------------------------------------- #
def _child_serve(args: argparse.Namespace) -> int:
    os.environ["TRAVEL_REPLAY_NO_AUTOSTART"] = "1"
    os.environ["TRAVEL_REPLAY_DB"] = args.db
    # 显式合成 Key：不管宿主环境有没有真实Key，注入factory都不读环境变量。
    os.environ["AMAP_API_KEY"] = SYNTHETIC_KEY

    import httpx
    import uvicorn

    from app.amap_tools import AmapAdapter, AmapClient
    from app.main import create_app
    from app.store import Store
    from app.worker import Worker

    log_path = Path(args.log)
    gate_dir = Path(args.gate_dir)
    gate_param_name, _, gate_param_value = args.gate_param.partition("=")
    state = {"factory_calls": 0, "close_attempts": 0, "factory_id": None}

    def log(event: dict) -> None:
        event = {"wall": round(time.time(), 3), **event}
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")
            handle.flush()

    class SyntheticProvider(httpx.MockTransport):
        """固定合成供应商；不出网，key必须是显式合成值。"""

        def __init__(self, factory_id: int):
            self.factory_id = factory_id
            super().__init__(self._handle)

        def _handle(self, request: httpx.Request):
            assert request.url.params["key"] == SYNTHETIC_KEY
            path = request.url.path
            params = dict(request.url.params)
            safe = {"kind": "send", "factory": self.factory_id, "path": path}
            for name in ("keywords", "id"):
                if name in params:
                    safe[name] = params[name]
            log(safe)
            if path == args.gate_path and params.get(gate_param_name) == gate_param_value:
                _touch(gate_dir / "reached")
                _wait_path(gate_dir / "release", 30)
            if path == "/v3/geocode/geo":
                data = {"geocodes": [{"location": "116.4,39.9", "city": "北京",
                                      "adcode": "110000"}]}
            elif path == "/v3/place/text":
                name = params["keywords"]
                pois = [{"id": name, "name": name, "cityname": "北京",
                         "location": "116.4,39.9"}]
                if name == "合成乙":  # 同名歧义：父run进入 needs_input
                    pois.append({"id": "B", "name": name, "cityname": "北京",
                                 "location": "116.5,39.9"})
                data = {"pois": pois}
            elif path == "/v3/place/detail":
                poi_id = params["id"]
                data = {"pois": [{"id": poi_id, "name": "合成乙", "cityname": "北京",
                                  "location": "116.5,39.9",
                                  "biz_ext": {"open_time": "09:00-18:00"}}]}
            elif path == "/v3/weather/weatherInfo":
                data = {"forecasts": [{"casts": [{"date": "2026-11-09",
                                                  "dayweather": "晴"}]}]}
            else:
                assert path == "/v3/direction/walking"
                data = {"route": {"paths": [{"duration": "60", "distance": "100"}]}}
            return httpx.Response(200, json={"status": "1", **data})

        def close(self) -> None:
            state["close_attempts"] += 1
            log({"kind": "close_attempt", "factory": self.factory_id,
                 "n": state["close_attempts"]})
            super().close()

    def factory(city: str, transport: str):
        state["factory_calls"] += 1
        factory_id = state["factory_calls"]
        log({"kind": "factory", "factory": factory_id, "city": city, "transport": transport})
        return AmapAdapter(
            AmapClient(key=SYNTHETIC_KEY, transport=SyntheticProvider(factory_id)),
            city=city, transport=transport, owns_client=True)

    store = Store(args.db)
    app = create_app(store=store, worker=Worker(store, autostart=False),
                     manual_drain=True, live_adapter_factory=factory)
    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error",
                            lifespan="on", access_log=False)
    server = uvicorn.Server(config)
    thread = Thread(target=server.run, daemon=False)
    thread.start()
    deadline = time.monotonic() + 20
    while not server.started:
        if time.monotonic() > deadline:
            print("PORT=0", flush=True)
            raise RuntimeError("uvicorn did not start")
        time.sleep(0.005)
    port = server.servers[0].sockets[0].getsockname()[1]
    print(f"PORT={port}", flush=True)
    for line in sys.stdin:
        if line.strip() == "shutdown":
            break
    server.should_exit = True
    thread.join(timeout=20)
    log({"kind": "exit", "port": port, "factory_calls": state["factory_calls"],
         "close_attempts": state["close_attempts"]})
    return 0


# --------------------------------------------------------------------------- #
# 父进程：启动/停止自己创建的应用进程 + 真实 loopback HTTP 编排
# --------------------------------------------------------------------------- #
class ChildApp:
    def __init__(self, db: Path, log: Path, gate_dir: Path, gate_path: str, gate_param: str):
        self.db = db
        self.log = log
        self.gate_dir = gate_dir
        self.gate_path = gate_path
        self.gate_param = gate_param
        self.proc: subprocess.Popen | None = None
        self.base_url = ""

    def __enter__(self):
        self.gate_dir.mkdir(parents=True, exist_ok=True)
        cmd = [sys.executable, str(Path(__file__).resolve()), "--serve",
               "--db", str(self.db), "--log", str(self.log),
               "--gate-dir", str(self.gate_dir), "--gate-path", self.gate_path,
               "--gate-param", self.gate_param]
        self.proc = subprocess.Popen(
            cmd, cwd=str(PROJECT_ROOT), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, bufsize=1)
        try:
            deadline = time.monotonic() + 25
            while True:
                line = self.proc.stdout.readline()
                if line.startswith("PORT="):
                    port = int(line.strip().split("=", 1)[1])
                    if port <= 0:
                        raise RuntimeError("child app did not bind a local port")
                    self.base_url = f"http://127.0.0.1:{port}"
                    break
                if line == "" and self.proc.poll() is not None:
                    stderr = self.proc.stderr.read()
                    raise RuntimeError(f"child app exited before port handshake: {stderr}")
                if time.monotonic() > deadline:
                    raise TimeoutError("child app port handshake timed out")
        except BaseException:
            # 握手失败也必须停止自己启动的子进程，避免残留服务。
            if self.proc.poll() is None:
                self.proc.kill()
                self.proc.wait(timeout=10)
            raise
        return self

    def stop(self) -> int:
        assert self.proc is not None
        if self.proc.poll() is not None:
            return self.proc.returncode if self.proc.returncode is not None else 1
        try:
            self.proc.stdin.write("shutdown\n")
            self.proc.stdin.flush()
            self.proc.stdin.close()
        except (BrokenPipeError, OSError):
            pass
        try:
            code = self.proc.wait(timeout=25)
        except subprocess.TimeoutExpired:
            # 只终止自己启动的子进程，避免残留服务。
            self.proc.kill()
            code = self.proc.wait(timeout=10)
        return code

    def __exit__(self, exc_type, exc, tb):
        if self.proc is not None and self.proc.stdin is not None and not self.proc.stdin.closed:
            code = self.stop()
            if exc_type is None and code != 0:
                stderr = self.proc.stderr.read() if self.proc.stderr else ""
                raise AssertionError(f"child app exited {code}: {stderr[-2000:]}")
        return False


def read_events(log_path: Path) -> list[dict]:
    items = []
    if log_path.exists():
        for line in log_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                items.append(json.loads(line))
    return items


def read_db(db_path: str) -> tuple[dict[str, dict], dict[str, list[dict]]]:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        runs = {}
        for row in con.execute("SELECT * FROM runs"):
            runs[row["run_id"]] = {
                "run_id": row["run_id"], "status": row["status"],
                "budget": json.loads(row["budget"]), "state": json.loads(row["state"]),
                "revision": row["revision"], "parent_run_id": row["parent_run_id"],
                "mode": row["mode"], "request": json.loads(row["request"]),
            }
        events: dict[str, list[dict]] = {}
        for row in con.execute("SELECT run_id, action, reason FROM events ORDER BY id"):
            events.setdefault(row["run_id"], []).append(
                {"action": row["action"], "reason": row["reason"]})
        return runs, events
    finally:
        con.close()


def assert_cancelled(payload: dict) -> None:
    assert payload["status"] == "cancelled", payload
    assert payload["budget"]["status"] == "cancelled"
    assert payload["quality_status"] == "unverified"
    assert payload["result"] is None
    assert "exhaustion_reason" not in payload["budget"]


def assert_live_cancel_wording(payload: dict) -> None:
    assert payload["mode"] == "live"
    assert "回放" not in payload["message"] and "无远端" not in payload["message"]
    assert "尽力" in payload["message"] and "可能仍完成" in payload["message"]


def http_clients(base_url: str):
    import httpx
    kwargs = {"base_url": base_url, "timeout": 30, "trust_env": False}
    return httpx.Client(**kwargs), httpx.Client(**kwargs)


def scenario_create(work: Path) -> dict:
    db = work / "create.sqlite3"
    log = work / "create.jsonl"
    gate = work / "gate-create"
    with ChildApp(db, log, gate, "/v3/place/text", "keywords=合成乙") as child:
        original, control = http_clients(child.base_url)
        with original, control:
            body = live_body()
            headers = {"Idempotency-Key": CREATE_KEY}
            result: dict = {}

            def post_original():
                result["response"] = original.post(
                    "/api/v1/travel/live-runs", json=body, headers=headers)

            thread = Thread(target=post_original, daemon=True)
            thread.start()
            _wait_path(gate / "reached", 20)  # 第三次发送已准入并在传输层等待
            replay = control.post("/api/v1/travel/live-runs", json=body, headers=headers)
            assert replay.status_code == 202
            assert replay.json()["replayed"] is True
            run_id = replay.json()["run_id"]
            events_before = len(replay.json()["events"])
            again = control.post("/api/v1/travel/live-runs", json=body, headers=headers)
            assert again.json()["run_id"] == run_id
            assert len(again.json()["events"]) == events_before  # 重放不新增事件
            cancel = control.post(f"/api/v1/travel/runs/{run_id}/cancel")
            assert cancel.status_code == 200
            assert_live_cancel_wording(cancel.json())
            assert_cancelled(cancel.json())
            for _ in range(3):
                assert_cancelled(control.get(f"/api/v1/travel/runs/{run_id}").json())
            _touch(gate / "release")
            thread.join(timeout=30)
            assert not thread.is_alive(), "original create POST did not return"
            response = result["response"]
            assert response.status_code == 202
            data = response.json()
            assert_cancelled(data)
            assert data["budget"]["tool_calls"] == 3  # origin + 合成甲 + 在途合成乙
            assert [item["tool"] for item in data["tool_results"]] == ["origin", "poi"]
            after = control.get(f"/api/v1/travel/runs/{run_id}").json()
            assert_cancelled(after)
            assert after["budget"] == data["budget"]
            replay_final = control.post("/api/v1/travel/live-runs", json=body,
                                       headers=headers).json()
            assert replay_final["run_id"] == run_id
            assert replay_final["events"] == data["events"]

    events = read_events(log)
    sends = [item for item in events if item["kind"] == "send" and item.get("factory") == 1]
    factories = [item for item in events if item["kind"] == "factory"]
    closes = [item for item in events if item["kind"] == "close_attempt" and item.get("factory") == 1]
    assert len(factories) == 1
    assert len(sends) == 3, sends
    assert len(closes) == 1
    runs, db_events = read_db(str(db))
    assert len(runs) == 1
    persisted = runs[run_id]
    assert persisted["status"] == "cancelled"
    assert persisted["budget"]["status"] == "cancelled"
    assert persisted["budget"]["tool_calls"] == 3
    assert persisted["state"]["result"] is None
    actions = [item["action"] for item in db_events[run_id]]
    assert "LIVE_FINISHED" in actions and "CANCELLED" in actions
    finished = [item for item in db_events[run_id] if item["action"] == "LIVE_FINISHED"][-1]
    assert "status=cancelled" in finished["reason"]
    return {"scenario": "create", "run_id": run_id, "tool_calls": 3,
            "transport_sends": len(sends), "close_attempts": len(closes),
            "status": persisted["status"]}


def scenario_revision(work: Path) -> dict:
    db = work / "revision.sqlite3"
    log = work / "revision.jsonl"
    gate = work / "gate-revision"
    with ChildApp(db, log, gate, "/v3/place/detail", "id=B") as child:
        original, control = http_clients(child.base_url)
        with original, control:
            parent = control.post("/api/v1/travel/live-runs", json=live_body(),
                                 headers={"Idempotency-Key": "e2e-parent"}).json()
            assert parent["status"] == "needs_input", parent
            assert parent["mode"] == "live"
            revision_body = {"selected_poi_ids": {"合成乙": "B"}, "reason": "选择候选"}
            url = f"/api/v1/travel/runs/{parent['run_id']}/revisions"
            headers = {"Idempotency-Key": REVISION_KEY}
            result: dict = {}

            def post_revision():
                result["response"] = original.post(url, json=revision_body, headers=headers)

            thread = Thread(target=post_revision, daemon=True)
            thread.start()
            _wait_path(gate / "reached", 20)  # 子run 的 detail(B) 已在途
            replay = control.post(url, json=revision_body, headers=headers)
            assert replay.status_code == 202
            assert replay.json()["replayed"] is True
            assert replay.json()["mode"] == "live"
            child_id = replay.json()["run_id"]
            assert replay.json()["parent_run_id"] == parent["run_id"]
            assert replay.json()["revision"] == parent["revision"] + 1
            cancel = control.post(f"/api/v1/travel/runs/{child_id}/cancel")
            assert cancel.status_code == 200
            assert_live_cancel_wording(cancel.json())
            assert_cancelled(cancel.json())
            for _ in range(2):
                assert_cancelled(control.get(f"/api/v1/travel/runs/{child_id}").json())
            _touch(gate / "release")
            thread.join(timeout=30)
            assert not thread.is_alive(), "original revision POST did not return"
            data = result["response"].json()
            assert_cancelled(data)
            assert data["budget"]["tool_calls"] == 3
            assert data["parent_run_id"] == parent["run_id"]
            parent_after = control.get(f"/api/v1/travel/runs/{parent['run_id']}").json()
            assert parent_after["status"] == "needs_input"
            child_after = control.get(f"/api/v1/travel/runs/{child_id}").json()
            assert_cancelled(child_after)

    events = read_events(log)
    factories = [item for item in events if item["kind"] == "factory"]
    closes = [item for item in events if item["kind"] == "close_attempt"]
    sends_by_factory: dict[int, list[dict]] = {}
    for item in events:
        if item["kind"] == "send":
            sends_by_factory.setdefault(item["factory"], []).append(item)
    assert len(factories) == 2 and len(closes) == 2
    # factory 1 = 父run，factory 2 = 修订子run；父run在子run启动前已完成。
    assert len(sends_by_factory.get(1, [])) == 11, sends_by_factory.get(1)
    assert len(sends_by_factory.get(2, [])) == 3, sends_by_factory.get(2)
    runs, db_events = read_db(str(db))
    assert len(runs) == 2
    assert runs[parent["run_id"]]["status"] == "needs_input"
    child_row = runs[child_id]
    assert child_row["status"] == "cancelled"
    assert child_row["budget"]["tool_calls"] == 3
    assert child_row["parent_run_id"] == parent["run_id"]
    child_actions = [item["action"] for item in db_events[child_id]]
    assert "CANCELLED" in child_actions and "LIVE_FINISHED" in child_actions
    finished = [item for item in db_events[child_id]
                if item["action"] == "LIVE_FINISHED"][-1]
    assert "status=cancelled" in finished["reason"]
    return {"scenario": "revision", "parent_run_id": parent["run_id"],
            "child_run_id": child_id, "parent_status": "needs_input",
            "child_tool_calls": 3, "transport_sends": [len(sends_by_factory[1]),
                                                       len(sends_by_factory[2])],
            "close_attempts": len(closes)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--db")
    parser.add_argument("--log")
    parser.add_argument("--gate-dir")
    parser.add_argument("--gate-path", default="")
    parser.add_argument("--gate-param", default="=")
    args = parser.parse_args()
    if args.serve:
        return _child_serve(args)

    work = Path(tempfile.mkdtemp(prefix="live-loopback-", dir=str(PROJECT_ROOT / "data")))
    exit_code = 1
    try:
        summary = {
            "scope": "independent-process loopback; real AmapAdapter + MockTransport; "
                     "synthetic key; no real provider",
            "create": scenario_create(work),
            "revision": scenario_revision(work),
        }
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
        print("E2E_OK")
        exit_code = 0
        return 0
    except Exception:
        import traceback
        traceback.print_exc()
        print(f"E2E_FAILED; artifacts kept at {work}")
        return 1
    finally:
        if exit_code == 0:
            import shutil
            shutil.rmtree(work, ignore_errors=True)
        sys.stdout.flush()


if __name__ == "__main__":
    raise SystemExit(main())
