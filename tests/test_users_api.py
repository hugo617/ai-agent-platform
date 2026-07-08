"""Tenant membership API tests — CRUD over the membership table.

The member endpoints moved from ``/users`` to ``/tenants/me/members`` when
``/users`` became a full user-profile CRUD. These tests follow the new path.
"""

import pytest


@pytest.mark.asyncio
async def test_list_members_includes_owner(app_client):
    # The test environment seeds casbin but not the user_tenants row, so add
    # the owner as a member first to verify listing reflects DB state.
    await app_client.post(
        "/api/v1/tenants/me/members/",
        json={"user_id": "owner-1", "role": "owner"},
        headers={"Authorization": "Bearer fake"},
    )
    resp = await app_client.get(
        "/api/v1/tenants/me/members/", headers={"Authorization": "Bearer fake"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert any(m["role"] == "owner" for m in body)


@pytest.mark.asyncio
async def test_add_and_update_member(app_client):
    # add alice as member
    resp = await app_client.post(
        "/api/v1/tenants/me/members/",
        json={"user_id": "alice", "role": "member", "email": "a@x.com"},
        headers={"Authorization": "Bearer fake"},
    )
    assert resp.status_code == 201
    assert resp.json()["role"] == "member"

    # promote alice to a custom role
    resp = await app_client.patch(
        "/api/v1/tenants/me/members/alice",
        json={"role": "admin"},
        headers={"Authorization": "Bearer fake"},
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == "admin"


@pytest.mark.asyncio
async def test_add_member_is_idempotent(app_client):
    # adding the same user twice updates role instead of erroring
    await app_client.post(
        "/api/v1/tenants/me/members/",
        json={"user_id": "carol", "role": "member"},
        headers={"Authorization": "Bearer fake"},
    )
    resp = await app_client.post(
        "/api/v1/tenants/me/members/",
        json={"user_id": "carol", "role": "owner"},
        headers={"Authorization": "Bearer fake"},
    )
    assert resp.status_code == 201
    assert resp.json()["role"] == "owner"


@pytest.mark.asyncio
async def test_delete_member(app_client):
    await app_client.post(
        "/api/v1/tenants/me/members/",
        json={"user_id": "dan", "role": "member"},
        headers={"Authorization": "Bearer fake"},
    )
    resp = await app_client.delete(
        "/api/v1/tenants/me/members/dan", headers={"Authorization": "Bearer fake"}
    )
    assert resp.status_code == 204

    # gone from the list
    resp = await app_client.get(
        "/api/v1/tenants/me/members/", headers={"Authorization": "Bearer fake"}
    )
    ids = [m["user_id"] for m in resp.json()]
    assert "dan" not in ids


@pytest.mark.asyncio
async def test_cannot_remove_self(app_client, tenant_owner):
    resp = await app_client.delete(
        f"/api/v1/tenants/me/members/{tenant_owner['user_id']}",
        headers={"Authorization": "Bearer fake"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_update_nonexistent_member_returns_404(app_client):
    resp = await app_client.patch(
        "/api/v1/tenants/me/members/ghost",
        json={"role": "member"},
        headers={"Authorization": "Bearer fake"},
    )
    assert resp.status_code == 404
