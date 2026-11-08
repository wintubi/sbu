"""Structured access logging with no request bodies or image bytes."""
from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Awaitable, Callable

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger("heritage.access")
ALLOWED_HOSTS = {"127.0.0.1", "localhost", "testserver"}


async def guard_and_log(request: Request,
                        call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    host = request.headers.get("host", "").split(":")[0].strip().lower()
    if host not in ALLOWED_HOSTS:
        return JSONResponse(status_code=403, content={
            "code": "HOST_NOT_ALLOWED", "message": "拒绝非本地 Host",
            "cause": f"Host={host}", "fix": "使用 127.0.0.1/localhost 访问",
            "retryable": False,
        })
    request_id = "req_" + uuid.uuid4().hex[:12]
    started = time.perf_counter()
    response = await call_next(request)
    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    response.headers["X-Request-ID"] = request_id
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    logger.info(json.dumps({
        "request_id": request_id,
        "method": request.method,
        "path": request.url.path,
        "status": response.status_code,
        "duration_ms": duration_ms,
    }, ensure_ascii=False))
    return response
