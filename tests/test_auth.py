"""Auth & /me tests."""

import pytest


@pytest.mark.asyncio
async def test_health(app_client):
    resp = await app_client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_missing_token_rejected(app_client):
    resp = await app_client.get("/api/v1/auth/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_malformed_token_rejected(app_client):
    resp = await app_client.get(
        "/api/v1/auth/me", headers={"Authorization": "NotBearer xxx"}
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_returns_current_identity(app_client, tenant_owner):
    resp = await app_client.get(
        "/api/v1/auth/me", headers={"Authorization": "Bearer fake"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["user_id"] == tenant_owner["user_id"]
    assert body["tenant_id"] == tenant_owner["tenant_id"]
    assert "owner" in body["roles"]
