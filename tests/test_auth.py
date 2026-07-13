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


@pytest.mark.asyncio
async def test_me_aggregates_permissions(app_client, tenant_owner):
    """/me returns the caller's effective permission codes (api + menu).

    The codes are aggregated from the user's roles via casbin's implicit-
    permissions walk. owner holds all seeded api perms (e.g. agents:read) and
    all business menu perms (e.g. menu:agents), but not menu:tenants (platform-
    level, never seeded into a tenant).
    """
    resp = await app_client.get(
        "/api/v1/auth/me", headers={"Authorization": "Bearer fake"}
    )
    assert resp.status_code == 200
    perms = set(resp.json()["permissions"])
    # api perms
    assert "agents:read" in perms
    assert "customers:read" in perms
    assert "roles:update" in perms
    # menu perms (business menus)
    assert "menu:dashboard" in perms
    assert "menu:agents" in perms
    assert "menu:users" in perms
    assert "menu:settings" in perms
    # menu:tenants is platform-level, never seeded — owner does NOT get it.
    assert "menu:tenants" not in perms


@pytest.mark.asyncio
async def test_me_member_permissions_subset(member_client):
    """A member only sees business menus + read perms, not management menus."""
    resp = await member_client.get(
        "/api/v1/auth/me", headers={"Authorization": "Bearer fake"}
    )
    assert resp.status_code == 200
    perms = set(resp.json()["permissions"])
    # business menus
    assert "menu:dashboard" in perms
    assert "menu:agents" in perms
    assert "menu:customers" in perms
    # management menus hidden
    assert "menu:users" not in perms
    assert "menu:settings" not in perms
    assert "menu:roles" not in perms
    # api: read-only
    assert "agents:read" in perms
    assert "agents:create" not in perms


@pytest.mark.asyncio
async def test_me_super_admin_empty_permissions(super_admin_client):
    """super_admin gets an empty permissions list (frontend bypasses on role)."""
    resp = await super_admin_client.get(
        "/api/v1/auth/me", headers={"Authorization": "Bearer fake"}
    )
    assert resp.status_code == 200
    assert resp.json()["permissions"] == []
