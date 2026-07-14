"""Tests for the observability endpoints: /health, /ready, /metrics.

- /health (liveness): always 200, includes a best-effort db field.
- /ready (readiness): 200 when DB is reachable, 503 when it isn't (simulated
  by overriding get_db with a session whose execute raises).
- /metrics: Prometheus text format, contains the request counter after a
  business request has flowed through the middleware.
"""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

AUTH = {"Authorization": "Bearer fake"}


@asynccontextmanager
async def _noop_lifespan(_app):
    yield


def _fake_decode(test_env):
    async def _decode(token: str):
        return {
            "sub": test_env.owner_user,
            "tenant_id": test_env.tenant_id,
            "email": "owner@example.com",
        }

    return _decode


@pytest.mark.asyncio
async def test_health_returns_ok_with_db_field(app_client):
    """/health is always 200 (liveness) and reports the DB ping best-effort."""
    resp = await app_client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["db"] == "ok"
    assert "app" in body and "env" in body


@pytest.mark.asyncio
async def test_ready_returns_200_when_db_ok(app_client):
    """/ready is 200 when the DB ping succeeds."""
    resp = await app_client.get("/ready")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ready"
    assert body["checks"]["db"] == "ok"


@pytest.mark.asyncio
async def test_ready_returns_503_when_db_fails(test_env):
    """/ready returns 503 when the DB ping raises (dependency is unhealthy).

    We override get_db with a session whose execute() raises, simulating a DB
    outage — without needing to actually break Postgres.
    """
    from app.api import deps as deps_mod
    from app.core import casbin_enforcer as casbin_mod
    from app.core.database import get_db
    from app.main import create_app

    class _BrokenSession:
        async def execute(self, *_a, **_kw):
            raise RuntimeError("simulated DB outage")

    @asynccontextmanager
    async def broken_db():
        yield _BrokenSession()

    app = create_app()
    app.router.lifespan_context = _noop_lifespan
    app.dependency_overrides[get_db] = broken_db

    with patch.object(casbin_mod, "get_enforcer", return_value=test_env.enforcer), \
         patch.object(deps_mod, "decode_token", new=AsyncMock(side_effect=_fake_decode(test_env))):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/ready")
            assert resp.status_code == 503
            body = resp.json()
            assert body["status"] == "not_ready"
            assert body["checks"]["db"] == "fail"

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_metrics_returns_prometheus_format(app_client):
    """/metrics exposes Prometheus text-format metrics."""
    resp = await app_client.get("/metrics")
    assert resp.status_code == 200
    assert "text/plain" in resp.headers.get("content-type", "")
    body = resp.text
    # The Counter/Histogram are declared even with zero observations.
    assert "http_requests_total" in body
    assert "http_request_duration_seconds" in body


@pytest.mark.asyncio
async def test_metrics_records_business_requests(app_client):
    """A non-exempt request increments http_requests_total."""
    # /api/v1/agents requires auth; an unauthenticated call still flows through
    # the middleware and returns 401, which is recorded as a request.
    resp = await app_client.get("/api/v1/agents/")
    assert resp.status_code == 401

    metrics_resp = await app_client.get("/metrics")
    body = metrics_resp.text
    assert "http_requests_total" in body
    # The 401 response should be reflected in the counter labels.
    assert 'status="401"' in body


@pytest.mark.asyncio
async def test_metrics_endpoint_is_exempt(app_client):
    """/metrics itself is not counted (no self-inflation on scrape)."""
    await app_client.get("/metrics")
    await app_client.get("/metrics")
    resp = await app_client.get("/metrics")
    body = resp.text
    # No /metrics path should appear as a label value in the counter lines.
    for line in body.splitlines():
        if line.startswith("http_requests_total{") or line.startswith(
            "http_requests_total "
        ):
            assert "/metrics" not in line


@pytest.mark.asyncio
async def test_metrics_in_progress_gauge(app_client):
    """The in-progress gauge is declared and exposed."""
    resp = await app_client.get("/metrics")
    assert "http_requests_in_progress" in resp.text
