"""Middleware de contexte de requête : identifiant, durée et log JSON."""

from __future__ import annotations

import re
import time

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from workhub.interfaces.rest.logging import get_logger
from workhub.shared.api import new_id

_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
_REQUEST_ID_HEADER = "X-Request-ID"


def _resolve_request_id(request: Request) -> str:
    candidate = request.headers.get(_REQUEST_ID_HEADER)
    if candidate is not None and _REQUEST_ID_PATTERN.fullmatch(candidate):
        return candidate
    return str(new_id())


def _duration_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 2)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Attache un `request_id` à la requête, le journalise et l'expose en réponse."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = _resolve_request_id(request)
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)
        request.state.request_id = request_id

        logger = get_logger("workhub.http")
        started = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "http.request",
                request_id=request_id,
                method=request.method,
                path=request.url.path,
                status_code=500,
                duration_ms=_duration_ms(started),
            )
            raise
        else:
            response.headers[_REQUEST_ID_HEADER] = request_id
            logger.info(
                "http.request",
                request_id=request_id,
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=_duration_ms(started),
            )
            return response
        finally:
            structlog.contextvars.clear_contextvars()
