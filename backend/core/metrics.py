"""Prometheus instrumentation for FastAPI. Falls back gracefully if not installed."""
from __future__ import annotations
import time
from fastapi import Response

try:
    from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
    _OK = True
except ImportError:
    _OK = False

if _OK:
    REQUEST_COUNT = Counter("gramsetu_http_requests_total", "Total HTTP requests", ["method", "path", "status"])
    REQUEST_LATENCY = Histogram("gramsetu_http_request_duration_seconds", "HTTP request latency", ["method", "path"])
else:
    REQUEST_COUNT = None
    REQUEST_LATENCY = None


def instrument_fastapi(app):
    if not _OK:
        return
    @app.middleware("http")
    async def _metrics_middleware(request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        path = request.url.path
        REQUEST_COUNT.labels(request.method, path, str(response.status_code)).inc()
        REQUEST_LATENCY.labels(request.method, path).observe(time.perf_counter() - start)
        return response

    @app.get("/metrics", include_in_schema=False)
    async def metrics():
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
