"""Prometheus metrics for the HTTP layer.

Three base signals cover the operational essentials:
- ``http_requests_total`` (Counter, labelled by method/path/status): traffic +
  error-rate dashboards.
- ``http_request_duration_seconds`` (Histogram, labelled by path): latency
  percentiles.
- ``http_requests_in_progress`` (Gauge): current concurrency for capacity
  planning.

The middleware in ``app.main`` populates these per request. The ``/metrics``
endpoint exposes them in Prometheus exposition format.

Label cardinality note: ``path`` is the *route template* (e.g. ``/api/v1/agents``
or ``/api/v1/agents/{agent_id}``), NOT the raw URL — using raw URLs would blow
up cardinality on path-parameterised routes (one series per agent id).
"""

from __future__ import annotations

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

# Total request count, broken down by HTTP method, route template, and status.
REQUESTS = Counter(
    "http_requests_total",
    "Total HTTP requests handled.",
    ["method", "path", "status"],
)

# Request latency histogram (seconds). Buckets are the prometheus_client
# defaults, which span ~1ms to ~10s — fine for a request/response API.
LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds.",
    ["method", "path"],
)

# In-flight request gauge — how many requests are being served right now.
IN_PROGRESS = Gauge(
    "http_requests_in_progress",
    "Number of HTTP requests currently being served.",
)


def render_metrics() -> tuple[bytes, str]:
    """Return ``(body, content_type)`` for the ``/metrics`` endpoint."""
    return generate_latest(), CONTENT_TYPE_LATEST
