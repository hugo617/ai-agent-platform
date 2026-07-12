"""Group API tests — cross-tenant business org management.

Covers: super_admin CRUD + tenant attach/detach, tenant-user read scoping,
write-guard (403 for non-super_admin), 404s, duplicate-attach (400), and
cross-tenant isolation (a tenant cannot see groups it doesn't belong to).
"""

import pytest

AUTH = {"Authorization": "Bearer fake"}


# ----------------------------------------------------- super_admin CRUD


@pytest.mark.asyncio
async def test_super_admin_create_and_get_group(super_admin_client):
    resp = await super_admin_client.post(
        "/api/v1/groups/",
        json={"name": "Acme Chain", "code": "ACME", "address": "1 HQ St"},
        headers=AUTH,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "Acme Chain"
    assert body["code"] == "ACME"
    assert body["tenant_ids"] == []
    assert body["status"] == "active"
    group_id = body["id"]

    resp = await super_admin_client.get(f"/api/v1/groups/{group_id}", headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()["id"] == group_id


@pytest.mark.asyncio
async def test_super_admin_list_groups_empty_then_populated(super_admin_client):
    resp = await super_admin_client.get("/api/v1/groups/", headers=AUTH)
    assert resp.status_code == 200
    assert resp.json() == []

    await super_admin_client.post(
        "/api/v1/groups/", json={"name": "G1"}, headers=AUTH
    )
    await super_admin_client.post(
        "/api/v1/groups/", json={"name": "G2"}, headers=AUTH
    )
    resp = await super_admin_client.get("/api/v1/groups/", headers=AUTH)
    assert resp.status_code == 200
    assert len(resp.json()) == 2


@pytest.mark.asyncio
async def test_super_admin_create_with_tenant_ids(super_admin_client, test_env):
    # test_env.tenant_id is a live tenant; attach at creation time.
    resp = await super_admin_client.post(
        "/api/v1/groups/",
        json={"name": "WithStore", "tenant_ids": [test_env.tenant_id]},
        headers=AUTH,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["tenant_ids"] == [test_env.tenant_id]
    assert body["tenants"][0]["id"] == test_env.tenant_id
    # Tenant name is "Test Tenant" (seeded in conftest).
    assert body["tenants"][0]["name"] == "Test Tenant"


@pytest.mark.asyncio
async def test_super_admin_create_with_unknown_tenant_404(super_admin_client):
    resp = await super_admin_client.post(
        "/api/v1/groups/",
        json={"name": "Ghost", "tenant_ids": ["tnt-does-not-exist"]},
        headers=AUTH,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_super_admin_update_group(super_admin_client):
    create = await super_admin_client.post(
        "/api/v1/groups/", json={"name": "Old"}, headers=AUTH
    )
    gid = create.json()["id"]
    resp = await super_admin_client.put(
        f"/api/v1/groups/{gid}",
        json={"name": "New", "address": "2 New St"},
        headers=AUTH,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "New"
    assert body["address"] == "2 New St"


@pytest.mark.asyncio
async def test_super_admin_update_duplicate_code_400(super_admin_client):
    await super_admin_client.post(
        "/api/v1/groups/", json={"name": "A", "code": "DUP"}, headers=AUTH
    )
    create_b = await super_admin_client.post(
        "/api/v1/groups/", json={"name": "B"}, headers=AUTH
    )
    bid = create_b.json()["id"]
    resp = await super_admin_client.put(
        f"/api/v1/groups/{bid}", json={"code": "DUP"}, headers=AUTH
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_super_admin_delete_group_soft(super_admin_client):
    create = await super_admin_client.post(
        "/api/v1/groups/", json={"name": "ToDelete"}, headers=AUTH
    )
    gid = create.json()["id"]
    resp = await super_admin_client.delete(f"/api/v1/groups/{gid}", headers=AUTH)
    assert resp.status_code == 204
    # Deleted group no longer in list.
    resp = await super_admin_client.get("/api/v1/groups/", headers=AUTH)
    assert all(g["id"] != gid for g in resp.json())
    # Direct get → 404.
    resp = await super_admin_client.get(f"/api/v1/groups/{gid}", headers=AUTH)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_super_admin_get_nonexistent_404(super_admin_client):
    resp = await super_admin_client.get("/api/v1/groups/nope", headers=AUTH)
    assert resp.status_code == 404


# ----------------------------------------------------- tenant attach/detach


@pytest.mark.asyncio
async def test_super_admin_attach_and_detach_tenant(super_admin_client, test_env):
    create = await super_admin_client.post(
        "/api/v1/groups/", json={"name": "G"}, headers=AUTH
    )
    gid = create.json()["id"]
    tid = test_env.tenant_id

    # Attach.
    resp = await super_admin_client.post(
        f"/api/v1/groups/{gid}/tenants/{tid}", headers=AUTH
    )
    assert resp.status_code == 201
    resp = await super_admin_client.get(f"/api/v1/groups/{gid}", headers=AUTH)
    assert resp.json()["tenant_ids"] == [tid]

    # Duplicate attach → 400.
    resp = await super_admin_client.post(
        f"/api/v1/groups/{gid}/tenants/{tid}", headers=AUTH
    )
    assert resp.status_code == 400

    # Detach.
    resp = await super_admin_client.delete(
        f"/api/v1/groups/{gid}/tenants/{tid}", headers=AUTH
    )
    assert resp.status_code == 204
    resp = await super_admin_client.get(f"/api/v1/groups/{gid}", headers=AUTH)
    assert resp.json()["tenant_ids"] == []


@pytest.mark.asyncio
async def test_super_admin_attach_unknown_tenant_404(super_admin_client):
    create = await super_admin_client.post(
        "/api/v1/groups/", json={"name": "G"}, headers=AUTH
    )
    gid = create.json()["id"]
    resp = await super_admin_client.post(
        f"/api/v1/groups/{gid}/tenants/tnt-nope", headers=AUTH
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_super_admin_detach_not_attached_404(super_admin_client, test_env):
    create = await super_admin_client.post(
        "/api/v1/groups/", json={"name": "G"}, headers=AUTH
    )
    gid = create.json()["id"]
    resp = await super_admin_client.delete(
        f"/api/v1/groups/{gid}/tenants/{test_env.tenant_id}", headers=AUTH
    )
    assert resp.status_code == 404


# --------------------------------------------- write guard (non-super_admin)


@pytest.mark.asyncio
async def test_tenant_owner_cannot_write(app_client):
    """Tenant owner (no platform_role) is blocked from all writes."""
    resp = await app_client.post(
        "/api/v1/groups/", json={"name": "X"}, headers=AUTH
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_member_cannot_write(member_client):
    resp = await member_client.post(
        "/api/v1/groups/", json={"name": "X"}, headers=AUTH
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_member_cannot_attach(member_client, test_env):
    # Even with a valid group+tenant, non-super_admin can't attach.
    resp = await member_client.post(
        f"/api/v1/groups/anything/tenants/{test_env.tenant_id}", headers=AUTH
    )
    assert resp.status_code == 403


# --------------------------------------------- tenant read scoping / isolation


@pytest.mark.asyncio
async def test_tenant_user_sees_only_own_groups(app_client, db_session, test_env):
    """A tenant user (non-super_admin) sees only groups their tenant belongs to."""
    # No groups yet → empty.
    resp = await app_client.get("/api/v1/groups/", headers=AUTH)
    assert resp.status_code == 200
    assert resp.json() == []

    # Create a group directly in the DB (bypassing the super_admin API) and
    # attach the test tenant to it.
    from app.models.group import Group, GroupTenant

    g = Group(name="MyGroup")
    db_session.add(g)
    await db_session.flush()
    db_session.add(GroupTenant(group_id=g.id, tenant_id=test_env.tenant_id))
    await db_session.commit()

    resp = await app_client.get("/api/v1/groups/", headers=AUTH)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["name"] == "MyGroup"

    # Can GET it (belongs to this tenant).
    resp = await app_client.get(f"/api/v1/groups/{g.id}", headers=AUTH)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_tenant_user_cannot_read_unrelated_group(app_client, db_session):
    """A group the tenant does NOT belong to is invisible (404 on direct get,
    absent from list)."""
    from app.models.group import Group, GroupTenant
    from app.models.tenant import Tenant

    # A second tenant + a group attached only to it.
    other_tenant = Tenant(id="tnt-isolated", name="Isolated")
    db_session.add(other_tenant)
    g = Group(name="OtherGroup")
    db_session.add(g)
    await db_session.flush()
    db_session.add(GroupTenant(group_id=g.id, tenant_id="tnt-isolated"))
    await db_session.commit()

    # The app_client's tenant (test_env.tenant_id) does not see it.
    resp = await app_client.get("/api/v1/groups/", headers=AUTH)
    assert all(item["id"] != g.id for item in resp.json())

    # Direct GET → 404 (not a member).
    resp = await app_client.get(f"/api/v1/groups/{g.id}", headers=AUTH)
    assert resp.status_code == 404
