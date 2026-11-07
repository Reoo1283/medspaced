from __future__ import annotations

import logging
import re
import time
from uuid import uuid4

from fastapi import Request
from fastapi.responses import JSONResponse

from app.core import metrics
from app.core.log_config import request_id_var
from app.core.telemetry import capture_exception

logger = logging.getLogger("medspaced.http")

_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
}
_SKIP_ACCESS_LOG = {"/health", "/ready"}


def _request_id(request: Request) -> str:
    supplied = request.headers.get("X-Request-ID", "")
    return supplied if _REQUEST_ID_PATTERN.fullmatch(supplied) else uuid4().hex


async def request_context_middleware(request: Request, call_next):
    request_id = _request_id(request)
    token = request_id_var.set(request_id)
    started = time.perf_counter()
    metrics.request_started()
    try:
        try:
            response = await call_next(request)
        except Exception as exc:
            metrics.request_finished(request.method, 500, time.perf_counter() - started)
            capture_exception(exc, request_id=request_id)
            logger.exception(
                "request_failed method=%s path=%s request_id=%s",
                request.method,
                request.url.path,
                request_id,
            )
            response = JSONResponse(status_code=500, content={"detail": "Sunucu hatası"})
            response.headers["X-Request-ID"] = request_id
            for name, value in _SECURITY_HEADERS.items():
                response.headers.setdefault(name, value)
            return response
        elapsed = time.perf_counter() - started
        metrics.request_finished(request.method, response.status_code, elapsed)
        elapsed_ms = elapsed * 1000
        response.headers["X-Request-ID"] = request_id
        for name, value in _SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        if request.url.path not in _SKIP_ACCESS_LOG:
            logger.info(
                "request method=%s path=%s status=%s duration_ms=%.1f request_id=%s",
                request.method,
                request.url.path,
                response.status_code,
                elapsed_ms,
                request_id,
            )
        return response
    finally:
        request_id_var.reset(token)
