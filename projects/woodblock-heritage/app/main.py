"""FastAPI boundary for the local heritage review slice."""
from __future__ import annotations

import os
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from .errors import ApiError
from .logging_utils import guard_and_log
from .models import PublicationCreate, ReviewCreate, SourceCreate, WorkCreate
from .service import (
    create_source,
    create_work,
    get_publication,
    get_work,
    knowledge,
    publications_for_work,
    publish_work,
    review_work,
)
from .store import Store

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
DEFAULT_DB = ROOT / "data" / "heritage.sqlite3"
LOCAL_ORIGIN = re.compile(r"^http://(127\.0\.0\.1|localhost)(:\d+)?$")
CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; "
       "connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")


def _field_errors(exc: ValidationError) -> list[dict[str, str]]:
    return [
        {"field": ".".join(str(part) for part in error.get("loc", ())) or "body",
         "message": error.get("msg", "invalid")}
        for error in exc.errors()
    ]


def _validate(model, body: Any):
    try:
        return model.model_validate(body)
    except ValidationError as exc:
        raise ApiError(422, "VALIDATION_ERROR", "请求字段校验失败",
                       cause="字段缺失或类型不符", fix="按错误字段修正后重试",
                       field_errors=_field_errors(exc)) from exc


async def _read_json(request: Request) -> Any:
    try:
        return await request.json()
    except (ValueError, UnicodeDecodeError) as exc:
        raise ApiError(422, "INVALID_JSON", "请求体不是合法 JSON",
                       cause=str(exc), fix="检查 JSON 语法") from exc


def create_app(*, db_path: str | None = None, store: Store | None = None) -> FastAPI:
    owns_store = store is None

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if app.state.store is None:
            app.state.store = Store(db_path or os.environ.get("HERITAGE_DB", str(DEFAULT_DB)))
        try:
            yield
        finally:
            if app.state.owns_store and app.state.store is not None:
                app.state.store.close()

    app = FastAPI(title="木版年画证据审核（本地切片）", version="0.1.0",
                  description="LOCAL REVIEW / 合成演示；不调用真实OCR/VLM/Neo4j",
                  lifespan=lifespan)
    app.state.store = store
    app.state.owns_store = owns_store
    if WEB.is_dir():
        app.mount("/static", StaticFiles(directory=str(WEB)), name="static")

    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(status_code=exc.status, content=exc.body())

    @app.exception_handler(RequestValidationError)
    async def _request_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(status_code=422, content={
            "code": "VALIDATION_ERROR", "message": "请求参数校验失败",
            "cause": "路径/查询参数不合法", "fix": "检查参数后重试",
            "retryable": False,
            "field_errors": [{"field": ".".join(str(p) for p in e.get("loc", ())),
                              "message": e.get("msg", "invalid")} for e in exc.errors()],
        })

    @app.middleware("http")
    async def _local_origin(request: Request, call_next):
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            origin = request.headers.get("origin")
            if origin and not LOCAL_ORIGIN.match(origin):
                return JSONResponse(status_code=403, content={
                    "code": "ORIGIN_NOT_ALLOWED", "message": "拒绝非本地同源写入",
                    "cause": f"Origin={origin}", "fix": "从 127.0.0.1/localhost 页面操作",
                    "retryable": False,
                })
        return await call_next(request)

    app.middleware("http")(guard_and_log)

    def _store(request: Request) -> Store:
        if request.app.state.store is None:
            request.app.state.store = Store(db_path or os.environ.get(
                "HERITAGE_DB", str(DEFAULT_DB)))
        return request.app.state.store

    @app.get("/")
    def index():
        target = WEB / "index.html"
        if not target.is_file():
            raise ApiError(500, "UI_NOT_INSTALLED", "审核页面文件缺失")
        return FileResponse(target, media_type="text/html",
                            headers={"Content-Security-Policy": CSP,
                                     "X-Content-Type-Options": "nosniff",
                                     "Cache-Control": "no-store"})

    @app.get("/health/live")
    def live() -> dict[str, Any]:
        return {"status": "ok", "mode": "local-review", "live_models": False, "neo4j": False}

    @app.get("/health/ready")
    def ready(request: Request) -> dict[str, Any]:
        try:
            st = _store(request)
            with st.transaction() as conn:
                conn.execute("SELECT 1").fetchone()
            db_ok = True
        except Exception:
            db_ok = False
        return {"status": "ready" if db_ok else "degraded", "database": "ok" if db_ok else "error",
                "mode": "local-review", "live_models": False, "neo4j": False,
                "note": "本地审核切片；候选与审核状态不进入真实图谱"}

    @app.post("/api/v1/heritage/sources")
    async def post_source(request: Request):
        body = _validate(SourceCreate, await _read_json(request))
        view, status = create_source(_store(request), body)
        return JSONResponse(status_code=status, content=view)

    @app.get("/api/v1/heritage/sources/{source_id}")
    def get_source(source_id: str, request: Request):
        source = _store(request).get_source(source_id)
        if source is None:
            raise ApiError(404, "SOURCE_NOT_FOUND", f"来源不存在：{source_id}")
        from .service import _source_view
        return _source_view(source)

    @app.get("/api/v1/heritage/sources/{source_id}/image")
    def get_source_image(source_id: str, request: Request):
        source = _store(request).get_source(source_id)
        if source is None:
            raise ApiError(404, "SOURCE_NOT_FOUND", f"来源不存在：{source_id}")
        return Response(content=source["content"], media_type=source["media_type"],
                        headers={"X-Content-Type-Options": "nosniff",
                                 "Cache-Control": "no-store"})

    @app.post("/api/v1/heritage/works")
    async def post_work(request: Request, idempotency_key: str | None = Header(
            default=None, alias="Idempotency-Key")):
        body = _validate(WorkCreate, await _read_json(request))
        view, status = create_work(_store(request), body, idempotency_key)
        return JSONResponse(status_code=status, content=view)

    @app.get("/api/v1/heritage/works")
    def list_works(request: Request, limit: int = Query(20, ge=1, le=100),
                   offset: int = Query(0, ge=0)):
        st = _store(request)
        items = []
        for work in st.list_works():
            try:
                view = get_work(st, work["id"])
            except ApiError:
                continue
            payload = view["payload"]
            title = next((str((claim.get("object") or {}).get("value"))
                          for claim in payload["claims"]
                          if claim.get("predicate") == "source_title"
                          and (claim.get("object") or {}).get("value")), None)
            items.append({"work_id": view["work_id"], "current_version": view["current_version"],
                          "title": title, "claim_count": len(payload["claims"]),
                          "issue_count": len(payload["issues"]),
                          "created_at": work["created_at"]})
        total = len(items)
        page = items[offset:offset + limit]
        return {"items": page, "count": len(page), "total": total,
                "limit": limit, "offset": offset, "has_more": offset + limit < total}

    @app.get("/api/v1/heritage/works/{work_id}")
    def work_detail(work_id: str, request: Request, version: int | None = None):
        return get_work(_store(request), work_id, version)

    @app.get("/api/v1/heritage/works/{work_id}/publications")
    def work_publications(work_id: str, request: Request):
        return publications_for_work(_store(request), work_id)

    @app.post("/api/v1/heritage/works/{work_id}/reviews")
    async def post_review(work_id: str, request: Request, idempotency_key: str | None = Header(
            default=None, alias="Idempotency-Key")):
        body = _validate(ReviewCreate, await _read_json(request))
        view, status = review_work(_store(request), work_id, body, idempotency_key)
        return JSONResponse(status_code=status, content=view)

    @app.post("/api/v1/heritage/publications")
    async def post_publication(request: Request, idempotency_key: str | None = Header(
            default=None, alias="Idempotency-Key")):
        body = _validate(PublicationCreate, await _read_json(request))
        view, status = publish_work(_store(request), body.work_id, body.expected_version,
                                    idempotency_key)
        return JSONResponse(status_code=status, content=view)

    @app.get("/api/v1/heritage/publications/{publication_id}")
    def publication_detail(publication_id: str, request: Request):
        return get_publication(_store(request), publication_id)

    @app.get("/api/v1/heritage/knowledge")
    def knowledge_view(request: Request, title: str | None = None,
                       limit: int = Query(20, ge=1, le=100),
                       offset: int = Query(0, ge=0)):
        return knowledge(_store(request), title, limit, offset)

    return app
