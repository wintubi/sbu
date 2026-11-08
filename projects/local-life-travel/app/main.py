"""FastAPI entry point for the replay single-day travel judge.

All paths are relative to this package, so the whole project directory can be
copied anywhere and still run. No live external calls are made.
"""
from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import ValidationError

from .amap_tools import AmapAdapter, AmapClient
from .domain import (
    REPLAY_NOTICE,
    ErrorResponse,
    LiveTravelRequest,
    RevisionRequest,
    TravelRequest,
    canonical_hash,
)
from .engine import build_run, create_run, derive_revision, new_id
from .live import create_live_run
from .replay_tools import scenario_index
from .store import Store
from .worker import Worker

ROOT = Path(__file__).resolve().parent.parent
WEB_INDEX = ROOT / "web" / "index.html"
DEFAULT_DB = ROOT / "data" / "replay.sqlite3"
NO_AUTOSTART = os.environ.get("TRAVEL_REPLAY_NO_AUTOSTART", "") == "1"


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, *,
                 retryable: bool = False, run_id: str | None = None,
                 field_errors: list[dict[str, str]] | None = None):
        self.status = status
        self.body = ErrorResponse(
            code=code, message=message, retryable=retryable,
            run_id=run_id, field_errors=field_errors,
        ).model_dump(mode="json")


async def read_json(request: Request) -> Any:
    """Malformed JSON must be a uniform 422, never an unhandled 500."""
    try:
        return await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
        raise ApiError(422, "VALIDATION_ERROR", "请求体不是合法 JSON",
                       field_errors=[{"field": "body", "message": str(exc)}]) from exc


def _validation_field_errors(exc: ValidationError) -> list[dict[str, str]]:
    out = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err.get("loc", ())) or "body"
        out.append({"field": loc, "message": err.get("msg", "invalid")})
    return out


def validate_request(body: Any) -> dict[str, Any]:
    if not isinstance(body, dict):
        raise ApiError(422, "VALIDATION_ERROR", "请求体必须是 JSON 对象")
    if body.get("mode", "replay") != "replay":
        raise ApiError(400, "LIVE_MODE_DISABLED",
                       "本切片仅支持 replay 模式；不连接任何真实外部服务")
    try:
        return TravelRequest.model_validate(body).model_dump(mode="json")
    except ValidationError as exc:
        raise ApiError(422, "VALIDATION_ERROR", "请求字段校验失败（T-01）",
                       field_errors=_validation_field_errors(exc)) from exc


def run_view(run: dict[str, Any], events: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    state = run["state"]
    mode = run.get("mode", "replay")
    return {
        "mode": mode,
        "replay_notice": REPLAY_NOTICE if mode == "replay" else (
            "LIVE / 真实渠道：调用高德 Web 服务；结果取决于供应商返回，不表示已经人工核验。"),
        "run_id": run["run_id"],
        "request_id": run["request_id"],
        "parent_run_id": run["parent_run_id"],
        "request_hash": run["request_hash"],
        "status": run["status"],
        "current_stage": run["current_stage"],
        "revision": run["revision"],
        "versions": run["versions"],
        "budget": run["budget"],
        "request": run["request"],
        "scenario_id": run["scenario_id"],
        "created_at": run["created_at"],
        "updated_at": run["updated_at"],
        "completed_stages": state["completed_stages"],
        "executed_stages": state["executed_stages"],
        "tool_results": state["tool_results"],
        "poi_records": state["poi_records"],
        "facts": state["facts"],
        "legs": state["legs"],
        "candidates_for_input": state["candidates_for_input"],
        "issues": state["issues"],
        "changes": state["changes"],
        "quality_status": state["quality_status"],
        "result": state["result"],
        "events": events if events is not None else [],
    }


def create_app(*, store: Store | None = None, worker: Worker | None = None,
               autostart: bool = False, manual_drain: bool = False,
               owns_resources: bool = False, live_adapter_factory=None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if app.state.store is None:
            db = os.environ.get("TRAVEL_REPLAY_DB", str(DEFAULT_DB))
            app.state.store = Store(db)
        if app.state.worker is None:
            app.state.worker = Worker(app.state.store, autostart=app.state.autostart)
        try:
            yield
        finally:
            if app.state.worker is not None:
                app.state.worker.stop()
            if app.state.owns_resources and app.state.store is not None:
                app.state.store.close()

    app = FastAPI(title="单日行程判官（REPLAY）", version="1.0.0",
                  description="本地固定回放切片；不连接真实地图/天气/模型服务",
                  lifespan=lifespan)
    app.state.store = store
    app.state.worker = worker
    app.state.autostart = autostart
    app.state.manual_drain = manual_drain
    app.state.owns_resources = owns_resources
    app.state.live_adapter_factory = live_adapter_factory

    def state(request: Request) -> tuple[Store, Worker]:
        if request.app.state.store is None:
            db = os.environ.get("TRAVEL_REPLAY_DB", str(DEFAULT_DB))
            request.app.state.store = Store(db)
        if request.app.state.worker is None:
            request.app.state.worker = Worker(request.app.state.store,
                                               autostart=request.app.state.autostart)
        return request.app.state.store, request.app.state.worker

    def live_factory(request: Request):
        factory = request.app.state.live_adapter_factory
        if factory is not None:
            return factory
        if not os.environ.get("AMAP_API_KEY"):
            raise ApiError(503, "LIVE_NOT_CONFIGURED",
                           "真实渠道未配置 AMAP_API_KEY；请先创建高德 Web 服务 Key 并设置环境变量",
                           retryable=False)
        return lambda city, transport: AmapAdapter(AmapClient(), city=city, transport=transport)

    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(status_code=exc.status, content=exc.body)

    @app.exception_handler(RequestValidationError)
    async def _request_validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        body = ErrorResponse(
            code="VALIDATION_ERROR", message="请求参数校验失败",
            field_errors=[{"field": ".".join(str(p) for p in e.get("loc", ())),
                           "message": e.get("msg", "invalid")} for e in exc.errors()],
        ).model_dump(mode="json")
        return JSONResponse(status_code=422, content=body)

    # -- health ------------------------------------------------------------ #
    @app.get("/health/live")
    def health_live() -> dict[str, Any]:
        return {"status": "ok", "mode": "replay", "replay_notice": REPLAY_NOTICE,
                "note": "进程存活检查；不执行任何外部或收费请求"}

    @app.get("/health/ready")
    def health_ready(request: Request) -> dict[str, Any]:
        st, wk = state(request)
        try:
            st.count_runs()
            db_ok = True
        except Exception:
            db_ok = False
        if request.app.state.manual_drain:
            worker_state, worker_healthy = "manual-drain (explicit test mode)", True
        elif wk.is_alive:
            worker_state, worker_healthy = "running", True
        else:
            worker_state, worker_healthy = "stopped", False
        return {
            "status": "ready" if db_ok and worker_healthy else "degraded",
            "mode": "replay", "replay_notice": REPLAY_NOTICE,
            "database": "ok" if db_ok else "error",
            "worker": worker_state,
            "worker_healthy": worker_healthy,
            "live_mode_enabled": False,
            "fixtures": len(scenario_index()),
            "note": "replay 与 live 分开报告；live 未启用；非测试模式下后台 worker 停止即视为 degraded",
        }

    @app.get("/fixtures")
    def fixtures() -> dict[str, Any]:
        items = scenario_index()
        return {"mode": "replay", "replay_notice": REPLAY_NOTICE,
                "count": len(items), "scenarios": items}

    # -- runs -------------------------------------------------------------- #
    @app.post("/api/v1/travel/live-runs", status_code=202)
    async def create_live_travel_run(request: Request, idempotency_key: str | None = Header(
            default=None, alias="Idempotency-Key")):
        body = await read_json(request)
        try:
            live_request = LiveTravelRequest.model_validate(body)
        except ValidationError as exc:
            raise ApiError(422, "VALIDATION_ERROR", "真实渠道请求校验失败（T-01）",
                           field_errors=_validation_field_errors(exc)) from exc
        factory = live_factory(request)
        store, _ = state(request)
        scoped_key = f"live:create:{idempotency_key}" if idempotency_key else None
        try:
            run, created = create_live_run(store, live_request, factory, scoped_key)
        except RuntimeError as exc:
            if str(exc) == "IDEMPOTENCY_CONFLICT":
                raise ApiError(409, "IDEMPOTENCY_CONFLICT",
                               "同一幂等键对应不同真实渠道请求；请重试原请求或使用新键") from exc
            raise
        view = run_view(run, store.get_events(run["run_id"]))
        view["replayed"] = not created
        return JSONResponse(status_code=202, content=view)

    @app.post("/api/v1/travel/runs", status_code=202)
    async def create_travel_run(request: Request) -> JSONResponse:
        store, _ = state(request)
        body = await read_json(request)
        normalized = validate_request(body)
        request_hash = canonical_hash(normalized)
        key = request.headers.get("Idempotency-Key")

        if key:
            candidate = build_run(normalized, idempotency_key=key, run_id=new_id("run"))
            outcome, prior = store.create_run_atomic(candidate, key, request_hash)
            if outcome == "existing":
                if prior["request_hash"] != request_hash:
                    raise ApiError(409, "IDEMPOTENCY_CONFLICT",
                                   "同一幂等键对应不同请求；请换用新的 Idempotency-Key",
                                   run_id=prior["run_id"])
                existing = store.get_run(prior["run_id"])
                if existing is None:
                    raise ApiError(409, "IDEMPOTENCY_CONFLICT",
                                   "幂等键已登记但运行尚未落盘，请稍后重试", run_id=prior["run_id"])
                view = run_view(existing, store.get_events(existing["run_id"]))
                view["replayed"] = True
                return JSONResponse(status_code=202, content=view)
            run = candidate
        else:
            run = create_run(store, normalized)

        view = run_view(run, store.get_events(run["run_id"]))
        view["replayed"] = False
        return JSONResponse(status_code=202, content=view)

    @app.get("/api/v1/travel/runs/{run_id}")
    def get_travel_run(run_id: str, request: Request) -> dict[str, Any]:
        store, _ = state(request)
        run = store.get_run(run_id)
        if run is None:
            raise ApiError(404, "RUN_NOT_FOUND", f"运行 {run_id} 不存在", run_id=run_id)
        return run_view(run, store.get_events(run_id))

    @app.post("/api/v1/travel/runs/{run_id}/revisions", status_code=202)
    async def create_revision(run_id: str, request: Request,
                              idempotency_key: str | None = Header(
                                  default=None, alias="Idempotency-Key")) -> JSONResponse:
        store, _ = state(request)
        parent = store.get_run(run_id)
        if parent is None:
            raise ApiError(404, "RUN_NOT_FOUND", f"运行 {run_id} 不存在", run_id=run_id)
        raw = await read_json(request)
        try:
            body = RevisionRequest.model_validate(raw)
        except ValidationError as exc:
            raise ApiError(422, "VALIDATION_ERROR", "修订请求校验失败",
                           field_errors=_validation_field_errors(exc)) from exc
        derived = derive_revision(parent, body.model_dump(mode="json"))
        if parent.get("mode") == "live":
            try:
                live_request = LiveTravelRequest.model_validate(derived)
            except ValidationError as exc:
                raise ApiError(422, "VALIDATION_ERROR", "live 修订请求校验失败",
                               field_errors=_validation_field_errors(exc)) from exc
            factory = live_factory(request)
            revision = parent["revision"] + 1
            versions = list(parent["versions"]) + [{"revision": revision, "run_id": "pending"}]
            scoped_key = (f"live:revision:{parent['run_id']}:{revision}:{idempotency_key}"
                          if idempotency_key else None)
            try:
                run, created = create_live_run(store, live_request, factory, scoped_key,
                                               parent_run_id=parent["run_id"], revision=revision,
                                               versions=versions)
            except RuntimeError as exc:
                if str(exc) == "IDEMPOTENCY_CONFLICT":
                    raise ApiError(409, "IDEMPOTENCY_CONFLICT",
                                   "同一幂等键对应不同修订请求") from exc
                raise
            if not created:
                if (run.get("parent_run_id") != parent["run_id"]
                        or run.get("revision") != revision):
                    raise ApiError(409, "IDEMPOTENCY_CONFLICT",
                                   "幂等键命中了不同父运行/修订号")
                view = run_view(run, store.get_events(run["run_id"]))
                view["replayed"] = True
                return JSONResponse(status_code=202, content=view)
            store.add_event(run["run_id"], "intake", "REVISION_CREATED",
                            f"由 {parent['run_id']} 修订而来（live）；原因：{body.reason or '未提供'}")
            store.add_event(parent["run_id"], "intake", "REVISION_REQUESTED",
                            f"用户提交 live 修订，新运行 {run['run_id']}；旧结果保留")
            view = run_view(run, store.get_events(run["run_id"]))
            view["replayed"] = False
            return JSONResponse(status_code=202, content=view)
        normalized = validate_request(derived)
        revision = parent["revision"] + 1
        versions = list(parent["versions"]) + [{"revision": revision, "run_id": "pending"}]
        scoped_key = (f"replay:revision:{parent['run_id']}:{revision}:{idempotency_key}"
                      if idempotency_key else None)
        run = build_run(normalized, parent_run_id=parent["run_id"], revision=revision,
                        versions=versions, idempotency_key=scoped_key)
        if scoped_key:
            outcome, prior = store.create_run_atomic(run, scoped_key, run["request_hash"])
            if outcome == "existing":
                if prior["request_hash"] != run["request_hash"]:
                    raise ApiError(409, "IDEMPOTENCY_CONFLICT",
                                   "同一幂等键对应不同修订请求")
                existing = store.get_run(prior["run_id"])
                if existing is None:
                    raise ApiError(500, "CORRUPT_STATE", "幂等记录指向不存在的运行")
                view = run_view(existing, store.get_events(existing["run_id"]))
                view["replayed"] = True
                return JSONResponse(status_code=202, content=view)
        else:
            store.create_run(run)
            store.add_event(run["run_id"], "intake", "RUN_CREATED",
                            f"回放修订运行；由 {parent['run_id']} 修订，未调用工具或模型")
        run["versions"] = list(parent["versions"]) + [{"revision": revision, "run_id": run["run_id"]}]
        store.save_run(run)
        store.add_event(run["run_id"], "intake", "REVISION_CREATED",
                        f"由 {parent['run_id']} 修订而来；原因：{body.reason or '未提供'}")
        store.add_event(parent["run_id"], "intake", "REVISION_REQUESTED",
                        f"用户提交修订，新运行 {run['run_id']}；旧结果保留")
        view = run_view(run, store.get_events(run["run_id"]))
        view["replayed"] = False
        return JSONResponse(status_code=202, content=view)

    @app.post("/api/v1/travel/runs/{run_id}/cancel")
    def cancel_travel_run(run_id: str, request: Request) -> dict[str, Any]:
        store, _ = state(request)
        run = store.get_run(run_id)
        if run is None:
            raise ApiError(404, "RUN_NOT_FOUND", f"运行 {run_id} 不存在", run_id=run_id)
        outcome = store.cancel_run(run_id)
        if outcome == "terminal":
            raise ApiError(409, "RUN_NOT_CANCELLABLE",
                           f"运行已处于终态 {run['status']}，不能取消", run_id=run_id)
        store.add_event(run_id, run["current_stage"], "CANCELLED",
                        "尽力停止后续调用；已执行阶段保留；本地回放无远端操作需要撤销")
        return {
            "mode": "replay", "replay_notice": REPLAY_NOTICE,
            "run_id": run_id, "status": "cancelled",
            "executed_stages": run["state"]["executed_stages"],
            "message": "已停止后续处理；已执行阶段与已得结果保留。本地回放不涉及远端操作，不声称撤销远端已执行调用。",
        }

    # -- UI ---------------------------------------------------------------- #
    @app.get("/", response_class=HTMLResponse)
    def index() -> HTMLResponse:
        if not WEB_INDEX.exists():
            return HTMLResponse("<h1>缺少 web/index.html</h1>", status_code=500)
        return HTMLResponse(WEB_INDEX.read_text(encoding="utf-8"))

    return app


app = create_app(autostart=not NO_AUTOSTART, owns_resources=True)
