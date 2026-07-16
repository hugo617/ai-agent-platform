"""Roles API tests."""

import pytest

AUTH = {"Authorization": "Bearer fake"}


@pytest.mark.asyncio
async def test_role_labels_empty_by_default(app_client):
    """Without tenant seeding (tests bypass create_tenant), no roles exist."""
    resp = await app_client.get("/api/v1/roles/label", headers=AUTH)
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_create_and_list_role(app_client):
    resp = await app_client.post(
        "/api/v1/roles/",
        json={"name": "Editor", "code": "editor", "description": "can edit"},
        headers=AUTH,
    )
    assert resp.status_code == 201, resp.text
    role = resp.json()
    assert role["code"] == "editor"
    assert role["is_system"] is False

    resp = await app_client.get("/api/v1/roles/", headers=AUTH)
    assert resp.status_code == 200
    assert any(r["code"] == "editor" for r in resp.json())

    resp = await app_client.get("/api/v1/roles/label", headers=AUTH)
    assert any(r["code"] == "editor" for r in resp.json())


@pytest.mark.asyncio
async def test_duplicate_role_code_rejected(app_client):
    payload = {"name": "Editor", "code": "editor_x"}
    resp = await app_client.post("/api/v1/roles/", json=payload, headers=AUTH)
    assert resp.status_code == 201
    resp = await app_client.post("/api/v1/roles/", json=payload, headers=AUTH)
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_update_and_delete_role(app_client):
    rid = (
        await app_client.post(
            "/api/v1/roles/",
            json={"name": "Temp", "code": "temp_role"},
            headers=AUTH,
        )
    ).json()["id"]

    resp = await app_client.put(
        f"/api/v1/roles/{rid}", json={"name": "Temp Renamed"}, headers=AUTH
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Temp Renamed"

    resp = await app_client.delete(f"/api/v1/roles/{rid}", headers=AUTH)
    assert resp.status_code == 204

    resp = await app_client.get("/api/v1/roles/", headers=AUTH)
    assert rid not in [r["id"] for r in resp.json()]


# --------------------------------------------------------------- permission edge


@pytest.mark.asyncio
async def test_member_cannot_create_role(member_client):
    """member has no roles:create → 403 (guard fires before the body runs)."""
    resp = await member_client.post(
        "/api/v1/roles/",
        json={"name": "Forbidden", "code": "forbidden"},
        headers=AUTH,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_member_cannot_delete_role(member_client):
    """member has no roles:delete → 403 (guard fires before lookup)."""
    resp = await member_client.delete("/api/v1/roles/any-id", headers=AUTH)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_system_role_cannot_be_deleted(app_client, db_session, tenant_owner):
    """System roles are protected from deletion → 400 (BizError)."""
    from app.models.rbac import Role

    role = Role(
        tenant_id=tenant_owner["tenant_id"],
        name="Seeded System",
        code="seeded_system",
        is_system=True,
    )
    db_session.add(role)
    await db_session.commit()

    resp = await app_client.delete(f"/api/v1/roles/{role.id}", headers=AUTH)
    assert resp.status_code == 400


# ---------------------------------------------------------------- 404 mapping


@pytest.mark.asyncio
async def test_update_nonexistent_role_returns_404(app_client):
    """NotFoundError → 404 (not the old string-match 400)."""
    resp = await app_client.put(
        "/api/v1/roles/nonexistent-id",
        json={"name": "Ghost"},
        headers=AUTH,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_nonexistent_role_returns_404(app_client):
    resp = await app_client.delete("/api/v1/roles/nonexistent-id", headers=AUTH)
    assert resp.status_code == 404


# ----------------------------------------------------------- update fields


@pytest.mark.asyncio
async def test_update_role_description_and_sort_order(app_client):
    """PUT role can update description + sort_order in one call.

    (Role.status was a dead column and has been removed; this test no longer
    exercises it.)
    """
    role = (
        await app_client.post(
            "/api/v1/roles/",
            json={"name": "Updater", "code": "updater"},
            headers=AUTH,
        )
    ).json()
    resp = await app_client.put(
        f"/api/v1/roles/{role['id']}",
        json={"description": "updated desc", "sort_order": 9},
        headers=AUTH,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["description"] == "updated desc"
    assert body["sort_order"] == 9


@pytest.mark.asyncio
async def test_list_roles_excludes_soft_deleted(app_client):
    """Soft-deleted roles don't appear in the list."""
    role = (
        await app_client.post(
            "/api/v1/roles/",
            json={"name": "Doomed", "code": "doomed"},
            headers=AUTH,
        )
    ).json()
    await app_client.delete(f"/api/v1/roles/{role['id']}", headers=AUTH)

    resp = await app_client.get("/api/v1/roles/", headers=AUTH)
    ids = [r["id"] for r in resp.json()]
    assert role["id"] not in ids


@pytest.mark.asyncio
async def test_role_labels_after_create(app_client):
    """The /roles/label endpoint returns {id, name, code} triples."""
    await app_client.post(
        "/api/v1/roles/",
        json={"name": "Labeled", "code": "labeled"},
        headers=AUTH,
    )
    resp = await app_client.get("/api/v1/roles/label", headers=AUTH)
    assert resp.status_code == 200
    labels = resp.json()
    found = next(item for item in labels if item["code"] == "labeled")
    assert "id" in found
    assert found["name"] == "Labeled"


# ----------------------------------------------- role ↔ permission grant CRUD


@pytest.mark.asyncio
async def test_grant_list_revoke_permission(app_client):
    """Full permission-grant lifecycle on a role: grant → list → revoke."""
    role = (
        await app_client.post(
            "/api/v1/roles/",
            json={"name": "Grantee", "code": "grantee"},
            headers=AUTH,
        )
    ).json()

    # grant (obj, act)
    resp = await app_client.post(
        f"/api/v1/roles/{role['id']}/permissions",
        json={"obj": "documents", "act": "read"},
        headers=AUTH,
    )
    assert resp.status_code == 201, resp.text
    grant = resp.json()
    assert grant["obj"] == "documents"
    assert grant["act"] == "read"

    # list reflects the grant
    resp = await app_client.get(
        f"/api/v1/roles/{role['id']}/permissions", headers=AUTH
    )
    assert resp.status_code == 200
    perms = resp.json()
    assert any(p["obj"] == "documents" and p["act"] == "read" for p in perms)

    # revoke
    resp = await app_client.delete(
        f"/api/v1/roles/{role['id']}/permissions/{grant['permission_id']}",
        headers=AUTH,
    )
    assert resp.status_code == 204

    # list now empty
    resp = await app_client.get(
        f"/api/v1/roles/{role['id']}/permissions", headers=AUTH
    )
    assert resp.json() == []


@pytest.mark.asyncio
async def test_revoke_non_granted_permission_returns_404(app_client):
    """Revoking a permission that isn't active → NotFoundError → 404."""
    role = (
        await app_client.post(
            "/api/v1/roles/",
            json={"name": "Empty", "code": "empty_role"},
            headers=AUTH,
        )
    ).json()
    resp = await app_client.delete(
        f"/api/v1/roles/{role['id']}/permissions/nonexistent-perm",
        headers=AUTH,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_permission_endpoints_404_for_missing_role(app_client):
    """Grant/list on a role_id that doesn't exist → 404."""
    resp = await app_client.get(
        "/api/v1/roles/nonexistent-role/permissions", headers=AUTH
    )
    assert resp.status_code == 404

    resp = await app_client.post(
        "/api/v1/roles/nonexistent-role/permissions",
        json={"obj": "x", "act": "read"},
        headers=AUTH,
    )
    assert resp.status_code == 404
