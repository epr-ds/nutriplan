"""Structured logging, request tracing, and Prometheus metrics (COM-906).

Three concerns are handled here, all keyed off a per-request context so an on-call engineer can
correlate a log line with the trace and the metrics it produced:

* **Structured logs** — every request emits one JSON line carrying the request id, trace id,
  method, route, status, and latency, plus the authenticated user when one is known.
* **Traces** — a W3C ``traceparent`` header, when present, has its trace id adopted so this
  service's spans join the caller's trace; otherwise a fresh trace id is minted. The ids ride
  along on the response (``X-Request-ID``) and in every log line.
* **Metrics** — Prometheus counters/histograms exposed at ``/metrics``: request totals and a
  duration histogram (for p95 latency). These back the commerce dashboard and the
  ``commerce_http_request_duration_seconds`` alert (see ``docs/OBSERVABILITY.md`` and
  ``docs/ALERTING.md``).

Conventions match the rest of the observability docs: Prometheus text exposition on the default
registry, and metric names prefixed with the service (``commerce_``).
"""

from __future__ import annotations

import json
import logging
import re
import time
import uuid

from prometheus_client import Counter, Histogram
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

SERVICE = "commerce"

logger = logging.getLogger("commerce.request")

# W3C trace context: version-traceid-spanid-flags (all lowercase hex).
_TRACEPARENT_RE = re.compile(r"^[0-9a-f]{2}-([0-9a-f]{32})-[0-9a-f]{16}-[0-9a-f]{2}$")

# --- Metrics ---------------------------------------------------------------------------------

http_requests_total = Counter(
    "commerce_http_requests_total",
    "Total HTTP requests.",
    ["method", "route", "status"],
)

http_request_duration_seconds = Histogram(
    "commerce_http_request_duration_seconds",
    "HTTP request duration in seconds.",
    ["method", "route"],
)


# --- Structured logging ----------------------------------------------------------------------


class JsonFormatter(logging.Formatter):
    """Renders a log record as a single JSON object, lifting traced fields to the top level."""

    _FIELDS = (
        "request_id",
        "trace_id",
        "span_id",
        "method",
        "path",
        "status",
        "duration_ms",
        "user_id",
    )

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "service": SERVICE,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field in self._FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging() -> None:
    """Attach the JSON handler to the root logger once (idempotent)."""
    root = logging.getLogger()
    if any(getattr(handler, "_nutriplan_json", False) for handler in root.handlers):
        return
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    handler._nutriplan_json = True  # type: ignore[attr-defined]
    root.addHandler(handler)
    root.setLevel(logging.INFO)


# --- Middleware ------------------------------------------------------------------------------


def _trace_context(request: Request) -> tuple[str, str, str]:
    """Return ``(request_id, trace_id, span_id)``, adopting an inbound ``traceparent`` trace id."""
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
    span_id = uuid.uuid4().hex[:16]
    trace_id = uuid.uuid4().hex
    match = _TRACEPARENT_RE.match(request.headers.get("traceparent", "").strip().lower())
    if match:
        trace_id = match.group(1)
    return request_id, trace_id, span_id


def _route_template(request: Request) -> str:
    """The matched route path, falling back to the raw path."""
    route = request.scope.get("route")
    return getattr(route, "path", request.url.path)


class TelemetryMiddleware(BaseHTTPMiddleware):
    """Observes every request: metrics, structured access log, and trace propagation."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id, trace_id, span_id = _trace_context(request)
        request.state.request_id = request_id
        request.state.trace_id = trace_id
        start = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception:
            self._record(
                request,
                status=500,
                duration=time.perf_counter() - start,
                ids=(request_id, trace_id, span_id),
            )
            raise

        response.headers["X-Request-ID"] = request_id
        self._record(
            request,
            status=response.status_code,
            duration=time.perf_counter() - start,
            ids=(request_id, trace_id, span_id),
        )
        return response

    def _record(
        self,
        request: Request,
        *,
        status: int,
        duration: float,
        ids: tuple[str, str, str],
    ) -> None:
        request_id, trace_id, span_id = ids
        route = _route_template(request)

        http_requests_total.labels(request.method, route, str(status)).inc()
        http_request_duration_seconds.labels(request.method, route).observe(duration)

        logger.log(
            logging.ERROR if status >= 500 else logging.INFO,
            "request completed",
            extra={
                "request_id": request_id,
                "trace_id": trace_id,
                "span_id": span_id,
                "method": request.method,
                "path": request.url.path,
                "status": status,
                "duration_ms": round(duration * 1000, 2),
                "user_id": getattr(request.state, "user_id", None),
            },
        )
