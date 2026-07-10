"""Permission matrix + catalogue API tests.

The test DB is NOT seeded with roles/permissions (``seed_tenant_defaults`` is
never called by the conftest), so each test builds the data it needs via the
existing ``roles`` grant endpoint — exactly the pattern in ``test_rbac_api``.
The matrix/catalogue endpoints then read that SCD2 state back.
"""

import pytest

AUTH = {"Authorization": "Bearer fake"}


async def _create_role(client, code: str, name: str | None = None) -> dict:
    resp = await client.post(
        "/api/v1/roles/",
        json={"name": name or code.title(), "code": code},
        headers=AUTH,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _grant(client, role_id: str, obj: str, act: str) -> dict:
    resp = await client.post(
        f"/api/v1/roles/{role_id}/permissions",
        json={"obj": obj, "act": act},
        headers=AUTH,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.mark.asyncio
async def test_matrix_reflects_grant(app_client):
    """A granted permission shows True; ungranted permissions show False."""
    role = await _create_role(app_client, "editor")
    await _grant(app_client, role["id"], "documents", "read")

    resp = await app_client.get("/api/v1/permissions/matrix", headers=AUTH)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    # roles include the one we created
    assert any(r["code"] == "editor" for r in body["roles"])
    # catalogue includes the granted permission unit
    codes = [p["code"] for p in body["permissions"]]
    assert "documents:read" in codes

    # matrix cell for the grant is True
    assert body["matrix"]["editor"]["documents:read"] is True
    # obj/act parsed from code
    perm = next(p for p in body["permissions"] if p["code"] == "documents:read")
    assert perm["obj"] == "documents"
    assert perm["act"] == "read"


@pytest.mark.asyncio
async def test_catalogue_lists_permission_items(app_client):
    """Catalogue returns all permission rows with parsed obj/act."""
    role = await _create_role(app_client, "viewer")
    await _grant(app_client, role["id"], "reports", "read")
    await _grant(app_client, role["id"], "reports", "export")

    resp = await app_client.get("/api/v1/permissions/catalogue", headers=AUTH)
    assert resp.status_code == 200, resp.text
    items = {p["code"]: p for p in resp.json()}
    assert "reports:read" in items
    assert "reports:export" in items
    assert items["reports:export"]["obj"] == "reports"
    assert items["reports:export"]["act"] == "export"


@pytest.mark.asyncio
async def test_matrix_updates_after_grant(app_client):
    """Granting a second permission flips its matrix cell to True."""
    role = await _create_role(app_client, "auditor")
    await _grant(app_client, role["id"], "logs", "read")

    resp = await app_client.get("/api/v1/permissions/matrix", headers=AUTH)
    assert resp.json()["matrix"]["auditor"]["logs:read"] is True

    await _grant(app_client, role["id"], "logs", "export")
    resp = await app_client.get("/api/v1/permissions/matrix", headers=AUTH)
    assert resp.json()["matrix"]["auditor"]["logs:export"] is True


@pytest.mark.asyncio
async def test_matrix_updates_after_revoke(app_client):
    """Revoking flips the matrix cell back to False."""
    role = await _create_role(app_client, "temp")
    grant = await _grant(app_client, role["id"], "widgets", "read")

    resp = await app_client.get("/api/v1/permissions/matrix", headers=AUTH)
    assert resp.json()["matrix"]["temp"]["widgets:read"] is True

    resp = await app_client.delete(
        f"/api/v1/roles/{role['id']}/permissions/{grant['permission_id']}",
        headers=AUTH,
    )
    assert resp.status_code == 204

    resp = await app_client.get("/api/v1/permissions/matrix", headers=AUTH)
    assert resp.json()["matrix"]["temp"]["widgets:read"] is False


@pytest.mark.asyncio
async def test_matrix_isolated_across_tenants(app_client, db_session, tenant_owner):
    """A role/permission in another tenant is invisible from this tenant."""
    from app.models.rbac import Role, RolePermission
    from app.models.tenant import Tenant

    other_tenant = "tnt-other-cross-wall"
    db_session.add(Tenant(id=other_tenant, name="Other"))
    other_role = Role(tenant_id=other_tenant, name="Spy", code="spy_role")
    db_session.add(other_role)
    await db_session.flush()
    # Grant a permission unit in the other tenant directly.
    from app.models.rbac import Permission

    perm = Permission(
        tenant_id=other_tenant, name="secret read", code="secret:read"
    )
    db_session.add(perm)
    await db_session.flush()
    db_session.add(
        RolePermission(
            role_id=other_role.id,
            permission_id=perm.id,
            tenant_id=other_tenant,
        )
    )
    await db_session.commit()

    # Matrix/catalogue for THIS tenant must not leak the other tenant's data.
    resp = await app_client.get("/api/v1/permissions/matrix", headers=AUTH)
    assert resp.status_code == 200
    body = resp.json()
    assert "spy_role" not in body["matrix"]
    assert all(p["code"] != "secret:read" for p in body["permissions"])

    resp = await app_client.get("/api/v1/permissions/catalogue", headers=AUTH)
    assert all(p["code"] != "secret:read" for p in resp.json())


@pytest.mark.asyncio
async def test_member_without_roles_read_is_forbidden(member_client):
    """The matrix/catalogue are guarded by roles:read.

    The conftest member lacks roles:read (only agents/conversations perms), so
    both endpoints return 403 — the guard fires before the handler runs.
    """
    resp = await member_client.get("/api/v1/permissions/matrix", headers=AUTH)
    assert resp.status_code == 403
    resp = await member_client.get("/api/v1/permissions/catalogue", headers=AUTH)
    assert resp.status_code == 403
