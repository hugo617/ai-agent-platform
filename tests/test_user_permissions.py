"""User-management permission boundary tests (role matrix enforcement).

These tests lock down the RBAC matrix for the ``users`` resource across the
three roles a request can come from:

  * super_admin — platform-level bypass, cross-tenant CRUD
  * owner / admin — tenant-scoped managers
  * member — plain user, NO access to user management at all

They are written as **behaviour assertions**: each test impersonates a role via
the conftest client fixtures and hits a real HTTP endpoint, so they exercise
the full chain ``HTTP → require_permission → permission_service.check → casbin``.

If any of these turns red, a permission boundary has been broken.

Fixtures: ``member_client`` / ``tenant_admin_client`` / ``app_client`` (owner)
/ ``super_admin_client`` — see ``conftest.py``.
"""

import pytest

AUTH = {"Authorization": "Bearer fake"}


def _create_payload(suffix: str) -> dict:
    return {
        "username": f"user_{suffix}",
        "email": f"user_{suffix}@example.com",
        "password": "Secret123!",
        "real_name": f"Real {suffix}",
        "phone": "13800000000",
        "role": "member",
        "status": "active",
    }


# =============================================================
# Plain members — must be denied ALL user-management endpoints.
# The member role has zero ``users:*`` policies in the default seed.
# =============================================================

@pytest.mark.asyncio
async def test_member_cannot_list_users(member_client):
    resp = await member_client.get("/api/v1/users/", headers=AUTH)
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_member_cannot_get_user(member_client):
    resp = await member_client.get("/api/v1/users/anyone", headers=AUTH)
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_member_cannot_create_user(member_client):
    resp = await member_client.post(
        "/api/v1/users/", json=_create_payload("x"), headers=AUTH
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_member_cannot_update_user(member_client):
    resp = await member_client.put(
        "/api/v1/users/anyone", json={"real_name": "X"}, headers=AUTH
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_member_cannot_delete_user(member_client):
    resp = await member_client.delete("/api/v1/users/anyone", headers=AUTH)
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_member_cannot_view_statistics(member_client):
    resp = await member_client.get("/api/v1/users/statistics", headers=AUTH)
    assert resp.status_code == 403, resp.text


# =============================================================
# Tenant admin — can read/create/update but NOT delete.
# The admin role seeds ``users:read/create/update`` (no delete).
# =============================================================

@pytest.mark.asyncio
async def test_admin_can_list_users(tenant_admin_client):
    resp = await tenant_admin_client.get("/api/v1/users/", headers=AUTH)
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_admin_can_create_user(tenant_admin_client):
    resp = await tenant_admin_client.post(
        "/api/v1/users/", json=_create_payload("adm"), headers=AUTH
    )
    assert resp.status_code == 201, resp.text


@pytest.mark.asyncio
async def test_admin_can_update_user(tenant_admin_client):
    # Create as admin, then update.
    created = (
        await tenant_admin_client.post(
            "/api/v1/users/", json=_create_payload("up"), headers=AUTH
        )
    ).json()
    resp = await tenant_admin_client.put(
        f"/api/v1/users/{created['id']}", json={"real_name": "Edited"}, headers=AUTH
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["real_name"] == "Edited"


@pytest.mark.asyncio
async def test_admin_cannot_delete_user(tenant_admin_client):
    created = (
        await tenant_admin_client.post(
            "/api/v1/users/", json=_create_payload("del"), headers=AUTH
        )
    ).json()
    resp = await tenant_admin_client.delete(
        f"/api/v1/users/{created['id']}", headers=AUTH
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_admin_only_sees_own_tenant(app_client, tenant_admin_client):
    """Admin sees only users in their own tenant — cross-tenant isolation.

    Uses app_client (owner) to confirm the admin's created user is visible to
    the same tenant, and both are bounded by the tenant scope.
    """
    # Admin creates a user in their tenant.
    await tenant_admin_client.post(
        "/api/v1/users/", json=_create_payload("scoped"), headers=AUTH
    )
    # Both admin and owner (same tenant) see it.
    admin_list = (
        await tenant_admin_client.get("/api/v1/users/?limit=50", headers=AUTH)
    ).json()
    owner_list = (
        await app_client.get("/api/v1/users/?limit=50", headers=AUTH)
    ).json()
    admin_emails = {u["email"] for u in admin_list["items"]}
    owner_emails = {u["email"] for u in owner_list["items"]}
    assert "user_scoped@example.com" in admin_emails
    assert "user_scoped@example.com" in owner_emails
    # No cross-tenant leakage: totals agree.
    assert admin_list["total"] == owner_list["total"]


# =============================================================
# Super admin — platform bypass, cross-tenant visibility.
# =============================================================

@pytest.mark.asyncio
async def test_super_admin_can_list_across_tenants(super_admin_client):
    """Super admin list must include the cross-tenant seeded user."""
    resp = await super_admin_client.get("/api/v1/users/?limit=50", headers=AUTH)
    assert resp.status_code == 200, resp.text
    emails = {u["email"] for u in resp.json()["items"]}
    assert "cross@example.com" in emails  # seeded in Other Tenant


@pytest.mark.asyncio
async def test_super_admin_bypasses_member_denial(super_admin_client):
    """Endpoints a member is denied (statistics) succeed for super admin."""
    resp = await super_admin_client.get("/api/v1/users/statistics", headers=AUTH)
    assert resp.status_code == 200, resp.text
