from __future__ import annotations

import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.observability import log_event, reset_trace_id, set_trace_id

logger = logging.getLogger(__name__)


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        trace_id = set_trace_id(request.headers.get("X-Request-ID"))
        request.state.trace_id = trace_id
        start = time.perf_counter()
        try:
            response: Response = await call_next(request)
        finally:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            log_event(
                getattr(request.app, "logger", logger),
                20,
                "request.completed",
                method=request.method,
                path=request.url.path,
                duration_ms=duration_ms,
            )
            reset_trace_id()
        response.headers["X-Request-ID"] = trace_id
        return response
