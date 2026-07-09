"""FastAPI middleware: request ID, rate limiting, exception handling, Prometheus metrics.

Registered in ``main.py`` via ``app.add_middleware()`` and ``app.middleware('http')``.
"""

import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings
from app.core.exceptions import MentisError, RateLimitExceededError
from app.core.logger import get_logger, request_id_var

log = get_logger(__name__)


# ── Request ID ─────────────────────────────────────────────────────────


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Assign a unique ``X-Request-ID`` to every request.

    If the client sends one via ``X-Request-ID`` header, that value is used;
    otherwise a new UUID is generated.
    """

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        request_id = request.headers.get('X-Request-ID', str(uuid.uuid4()))
        token = request_id_var.set(request_id)
        try:
            response = await call_next(request)
            response.headers['X-Request-ID'] = request_id
            return response
        finally:
            request_id_var.reset(token)


# ── Request Timing ─────────────────────────────────────────────────────


class RequestTimingMiddleware(BaseHTTPMiddleware):
    """Log the duration of every request."""

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        start = time.monotonic()
        response = await call_next(request)
        elapsed_ms = (time.monotonic() - start) * 1000
        log.info(
            'request_completed',
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=round(elapsed_ms, 2),
        )
        return response


# ── Global Exception Handler ───────────────────────────────────────────


async def mentis_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch all ``MentisError`` subclasses and return structured JSON errors.

    Registered in ``main.py`` via ``app.add_exception_handler``.
    """
    if isinstance(exc, MentisError):
        log.warning(
            'mentis_error',
            code=exc.code,
            status=exc.status_code,
            message=exc.message,
            path=str(request.url.path),
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.to_dict(),
        )

    # Unhandled errors
    log.error('unhandled_error', exc_info=exc, path=str(request.url.path))
    return JSONResponse(
        status_code=500,
        content={
            'error': {
                'code': 'INTERNAL_ERROR',
                'message': 'An unexpected error occurred.',
                'details': {},
            }
        },
    )


# ── Simple In-Memory Rate Limiter ─────────────────────────────────────


class RateLimiter:
    """Sliding-window rate limiter backed by a dict (single-process only).

    For multi-process deployments, replace with Redis-based limiter.
    """

    def __init__(self, max_requests: int = 100, window_seconds: int = 60) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._buckets: dict[str, list[float]] = {}

    def check(self, key: str) -> bool:
        now = time.monotonic()
        window_start = now - self.window_seconds
        timestamps = self._buckets.get(key, [])
        timestamps = [t for t in timestamps if t > window_start]
        if len(timestamps) >= self.max_requests:
            return False
        timestamps.append(now)
        self._buckets[key] = timestamps
        return True


_rate_limiter = RateLimiter(
    max_requests=settings.rate_limit_requests,
    window_seconds=settings.rate_limit_window_seconds,
)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Apply rate limiting based on client IP or API key."""

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        if not settings.rate_limit_enabled:
            return await call_next(request)

        # Use API key or client IP as the bucket key
        api_key = request.headers.get('X-API-Key', '')
        bucket_key = api_key if api_key else request.client.host if request.client else 'unknown'

        if not _rate_limiter.check(bucket_key):
            raise RateLimitExceededError(retry_after_seconds=settings.rate_limit_window_seconds)

        return await call_next(request)


# ── Registration Helper ────────────────────────────────────────────────


def register_middleware(app: FastAPI) -> None:
    """Register all middleware and exception handlers on the FastAPI app.

    Call once in ``main.py`` during startup.
    """
    # Exception handler must be registered first (innermost)
    app.add_exception_handler(Exception, mentis_exception_handler)

    # Middleware are applied in reverse order of registration
    app.add_middleware(RequestTimingMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(RequestIDMiddleware)

    log.info('middleware_registered')
