"""Per-request access logging with a correlation id."""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("app.request")

REQUEST_ID_HEADER = "X-Request-ID"


def _level_for(status_code: int) -> int:
    if status_code >= 500:
        return logging.ERROR
    if status_code >= 400:
        return logging.WARNING
    return logging.INFO


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log one line per request: id, client, method, path, status, duration.

    An inbound `X-Request-ID` is honoured so a caller can correlate its own
    logs with ours; otherwise a short id is generated. Either way the id is
    exposed as `request.state.request_id` and echoed on the response.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or uuid4().hex[:12]
        request.state.request_id = request_id

        path = request.url.path
        if request.url.query:
            path = f"{path}?{request.url.query}"
        client = request.client.host if request.client else "-"

        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            elapsed_ms = (time.perf_counter() - start) * 1000
            logger.exception(
                "%s %s %s %s -> unhandled exception in %.2fms",
                request_id,
                client,
                request.method,
                path,
                elapsed_ms,
            )
            raise

        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.log(
            _level_for(response.status_code),
            "%s %s %s %s -> %d in %.2fms",
            request_id,
            client,
            request.method,
            path,
            response.status_code,
            elapsed_ms,
        )

        response.headers[REQUEST_ID_HEADER] = request_id
        return response
