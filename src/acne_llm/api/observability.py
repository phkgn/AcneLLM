from __future__ import annotations

import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Callable

from fastapi import Request, Response
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware


@dataclass
class MetricsRegistry:
    request_count: dict[tuple[str, str, int], int] = field(default_factory=lambda: defaultdict(int))
    request_latency_ms: list[float] = field(default_factory=list)
    ollama_error_count: int = 0
    guardrail_trigger_count: int = 0

    def record_request(self, method: str, path: str, status_code: int, latency_ms: float) -> None:
        self.request_count[(method, path, status_code)] += 1
        self.request_latency_ms.append(latency_ms)
        if len(self.request_latency_ms) > 10_000:
            self.request_latency_ms = self.request_latency_ms[-5_000:]
        if status_code >= 500:
            self.ollama_error_count += 1

    def render_prometheus(self) -> str:
        lines = [
            "# HELP acnellm_requests_total Total HTTP requests.",
            "# TYPE acnellm_requests_total counter",
        ]
        for (method, path, status), count in sorted(self.request_count.items()):
            lines.append(
                f'acnellm_requests_total{{method="{method}",path="{path}",status="{status}"}} {count}'
            )
        lines.extend([
            "# HELP acnellm_request_latency_ms Request latency in milliseconds.",
            "# TYPE acnellm_request_latency_ms summary",
        ])
        values = sorted(self.request_latency_ms)
        if values:
            p50 = values[len(values) // 2]
            p95 = values[int((len(values) - 1) * 0.95)]
            mean = sum(values) / len(values)
        else:
            p50 = p95 = mean = 0.0
        lines.append(f'acnellm_request_latency_ms{{quantile="0.50"}} {p50:.3f}')
        lines.append(f'acnellm_request_latency_ms{{quantile="0.95"}} {p95:.3f}')
        lines.append(f"acnellm_request_latency_ms_sum {sum(values):.3f}")
        lines.append(f"acnellm_request_latency_ms_count {len(values)}")
        lines.append(f"acnellm_request_latency_ms_mean {mean:.3f}")
        lines.append("# HELP acnellm_guardrail_triggers_total Guardrail trigger count.")
        lines.append("# TYPE acnellm_guardrail_triggers_total counter")
        lines.append(f"acnellm_guardrail_triggers_total {self.guardrail_trigger_count}")
        lines.append("# HELP acnellm_ollama_errors_total Backend error count.")
        lines.append("# TYPE acnellm_ollama_errors_total counter")
        lines.append(f"acnellm_ollama_errors_total {self.ollama_error_count}")
        return "\n".join(lines) + "\n"


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, metrics: MetricsRegistry):
        super().__init__(app)
        self.metrics = metrics

    async def dispatch(self, request: Request, call_next: Callable):
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        started = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            latency_ms = (time.perf_counter() - started) * 1000
            self.metrics.record_request(
                request.method,
                request.url.path,
                status_code,
                latency_ms,
            )
            logger.info(
                "request_id={} method={} path={} status={} latency_ms={:.1f}",
                request_id,
                request.method,
                request.url.path,
                status_code,
                latency_ms,
            )
            if "response" in locals():
                response.headers["X-Request-ID"] = request_id


class APIKeyMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, api_key: str):
        super().__init__(app)
        self.api_key = api_key

    async def dispatch(self, request: Request, call_next: Callable):
        if not self.api_key or request.url.path in {"/", "/metrics", "/api/v1/health"}:
            return await call_next(request)
        header_key = request.headers.get("x-api-key")
        bearer = request.headers.get("authorization", "")
        if header_key == self.api_key or bearer == f"Bearer {self.api_key}":
            return await call_next(request)
        return Response("Unauthorized", status_code=401)


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, per_minute: int):
        super().__init__(app)
        self.per_minute = per_minute
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        # Bug #7 fix: asyncio.Lock để tránh race condition khi concurrent requests
        # cùng đọc/ghi _hits dict
        import asyncio
        self._lock = asyncio.Lock()

    async def dispatch(self, request: Request, call_next: Callable):
        if self.per_minute <= 0 or request.url.path in {"/metrics", "/api/v1/health"}:
            return await call_next(request)
        now = time.monotonic()
        client = request.client.host if request.client else "unknown"
        async with self._lock:
            hits = self._hits[client]
            while hits and now - hits[0] > 60:
                hits.popleft()
            if len(hits) >= self.per_minute:
                return Response("Rate limit exceeded", status_code=429)
            hits.append(now)
        return await call_next(request)
