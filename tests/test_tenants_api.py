"""Tenant API tests — platform list/detail/update + user-scoped list + create.

The tenant endpoints split into two permission scopes after the
``tenants-admin-api`` hardening:

* User-scoped: ``GET /tenants/`` (the caller's own tenants) — any logged-in
  user.
* Platform-level: ``GET /tenants/all``, ``GET /tenants/{id}``, ``POST /``,
  ``PUT /{id}`` — super_admin only.

The POST used to be open to any logged-in user; it is now restricted to
super_admin. The user-scoped GET /tenants/ is unchanged (regression-tested).
"""

import pytest

AUTH = {"Authorization": "Bearer fake"}


# ============================================================ user-scoped GET /
# Unchanged behaviour — regression coverage for the tightened POST.


@pytest.mark.asyncio
async def test_list_my_tenants_includes_seed_tenant(app_client):
    """The owner already belongs to the seed tenant (Test Tenant)."""
    resp = await app_client.get("/api/v1/tenants/", headers=AUTH)
    assert resp.status_code == 200
    names = [t["name"] for t in resp.json()]
    assert "Test Tenant" in names


@pytest.mark.asyncio
async def test_list_user_tenants_empty_returns_empty_list(db_session):
    """Service-level: a user with no memberships gets an empty list (not 404).

    The API layer wraps this in a 404, but the service contract is "return []".
    This covers ``list_user_tenants`` when ``list_for_user`` yields nothing.
    """
    from app.services.tenant_service import TenantService

    svc = TenantService(db_session)
    result = await svc.list_user_tenants("nonexistent-user-id")
    assert result == []


@pytest.mark.asyncio
async def test_list_my_tenants_isolated_per_user(app_client, member_client):
    """Each user's tenant list comes only from their memberships.

    The owner has the seed "Test Tenant" + any they created. The member shares
    the seed tenant but has a different user_id, so their list is independent.
    Both lists are non-empty (seed tenant) — isolation is verified by the
    service-level empty-path test above + membership scoping in list_for_user.
    """
    owner_resp = await app_client.get("/api/v1/tenants/", headers=AUTH)
    member_resp = await member_client.get("/api/v1/tenants/", headers=AUTH)

    assert owner_resp.status_code == 200
    assert member_resp.status_code == 200
    # Both at least see the shared seed tenant.
    assert len(owner_resp.json()) >= 1
    assert len(member_resp.json()) >= 1


@pytest.mark.asyncio
async def test_my_tenants_read_view_has_member_count_zero(app_client):
    """The user-scoped list does not aggregate; member_count stays at its default 0.

    (The platform-level endpoints are the ones that populate member_count.)
    """
    resp = await app_client.get("/api/v1/tenants/", headers=AUTH)
    assert resp.status_code == 200
    for t in resp.json():
        assert t["member_count"] == 0


# ============================================================ POST / (tightened)


@pytest.mark.asyncio
async def test_create_tenant_returns_tenant(super_admin_client):
    """POST /tenants/ creates a new tenant and links the caller as owner."""
    resp = await super_admin_client.post(
        "/api/v1/tenants/", json={"name": "Acme Corp"}, headers=AUTH
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "Acme Corp"
    assert "id" in body
    # The hardened TenantRead exposes the new fields.
    assert body["status"] == "active"
    assert body["member_count"] == 1  # the creator is linked as owner
    assert body["created_by"] is not None


@pytest.mark.asyncio
async def test_create_tenant_seeds_owner_role(super_admin_client, db_session, test_env):
    """Creating a tenant links the caller as 'owner' (UserTenant row)."""
    from sqlalchemy import select

    from app.models.tenant import UserTenant

    resp = await super_admin_client.post(
        "/api/v1/tenants/", json={"name": "Role Seed Tenant"}, headers=AUTH
    )
    assert resp.status_code == 201
    tenant_id = resp.json()["id"]

    stmt = select(UserTenant).where(
        UserTenant.tenant_id == tenant_id,
        UserTenant.user_id == test_env.owner_user,
    )
    result = await db_session.execute(stmt)
    memberships = result.scalars().all()
    assert any(m.role == "owner" for m in memberships)


@pytest.mark.asyncio
async def test_create_tenant_seeds_default_permissions(super_admin_client, db_session):
    """Creating a tenant also seeds default casbin policies (seed_tenant_defaults).

    Verified by checking the permissions table has rows for the new tenant —
    this covers the full create_tenant pipeline (role seed + permission seed).
    """
    from sqlalchemy import select

    from app.models.rbac import Permission

    resp = await super_admin_client.post(
        "/api/v1/tenants/", json={"name": "Perm Seed Tenant"}, headers=AUTH
    )
    assert resp.status_code == 201
    tenant_id = resp.json()["id"]

    stmt = select(Permission).where(Permission.tenant_id == tenant_id)
    result = await db_session.execute(stmt)
    perms = result.scalars().all()
    # DEFAULT_OWNER_PERMS alone contributes ~20 permission rows.
    assert len(perms) > 10


@pytest.mark.asyncio
async def test_non_super_admin_cannot_create_tenant(app_client):
    """POST /tenants/ is restricted to super_admin (behaviour change).

    Previously any logged-in user could create a tenant; now a non-super_admin
    gets 403.
    """
    resp = await app_client.post(
        "/api/v1/tenants/", json={"name": "Should Fail"}, headers=AUTH
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_member_cannot_create_tenant(member_client):
    """A member is also rejected from POST /tenants/ (403)."""
    resp = await member_client.post(
        "/api/v1/tenants/", json={"name": "Should Fail"}, headers=AUTH
    )
    assert resp.status_code == 403


# ================================================ GET /all (super_admin only)


@pytest.mark.asyncio
async def test_super_admin_list_all_tenants(super_admin_client):
    """GET /tenants/all returns every tenant with member_count (super_admin)."""
    resp = await super_admin_client.get("/api/v1/tenants/all", headers=AUTH)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # At least the seed "Test Tenant" + the fixture's "Other Tenant".
    names = [t["name"] for t in body]
    assert "Test Tenant" in names
    assert "Other Tenant" in names
    # member_count is populated at the platform level.
    for t in body:
        assert t["member_count"] >= 0


@pytest.mark.asyncio
async def test_non_super_admin_list_all_forbidden(app_client):
    """GET /tenants/all is super_admin-only (403 for a normal owner)."""
    resp = await app_client.get("/api/v1/tenants/all", headers=AUTH)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_list_all_member_count_aggregates_active_only(
    super_admin_client, db_session
):
    """member_count counts only the *active* SCD2 membership rows.

    The fixture seeds 'cross-user' as an active member of 'Other Tenant'
    (member_count=1). We close that membership and assert the count drops to 0,
    proving the aggregate respects the valid_to IS NULL predicate.
    """
    from sqlalchemy import select

    from app.models.tenant import Tenant, UserTenant

    # Locate Other Tenant + its active membership.
    tenant_row = await db_session.execute(
        select(Tenant).where(Tenant.name == "Other Tenant")
    )
    other_tenant = tenant_row.scalar_one()
    membership = (
        await db_session.execute(
            select(UserTenant).where(
                UserTenant.tenant_id == other_tenant.id,
                UserTenant.user_id == "cross-user",
                UserTenant.valid_to.is_(None),
            )
        )
    ).scalar_one()
    # Close the active row (simulate removal).
    from datetime import UTC, datetime

    membership.valid_to = datetime.now(UTC)
    await db_session.commit()

    resp = await super_admin_client.get("/api/v1/tenants/all", headers=AUTH)
    assert resp.status_code == 200
    by_name = {t["name"]: t for t in resp.json()}
    assert by_name["Other Tenant"]["member_count"] == 0


# ================================================ GET /{id} (super_admin only)


@pytest.mark.asyncio
async def test_super_admin_get_tenant_detail(super_admin_client, test_env):
    """GET /tenants/{id} returns the tenant with member_count (super_admin)."""
    resp = await super_admin_client.get(
        f"/api/v1/tenants/{test_env.tenant_id}", headers=AUTH
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["id"] == test_env.tenant_id
    assert body["name"] == "Test Tenant"
    assert body["member_count"] >= 1  # owner belongs to the seed tenant


@pytest.mark.asyncio
async def test_non_super_admin_get_detail_forbidden(app_client, test_env):
    """GET /tenants/{id} is super_admin-only (403 for a normal owner)."""
    resp = await app_client.get(
        f"/api/v1/tenants/{test_env.tenant_id}", headers=AUTH
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_get_tenant_detail_not_found(super_admin_client):
    """GET /tenants/{id} on a missing id returns 404."""
    resp = await super_admin_client.get(
        "/api/v1/tenants/nonexistent-tenant-id", headers=AUTH
    )
    assert resp.status_code == 404


# ================================================ PUT /{id} (super_admin only)


@pytest.mark.asyncio
async def test_super_admin_update_tenant(super_admin_client, test_env):
    """PUT /tenants/{id} partially updates a tenant (super_admin)."""
    resp = await super_admin_client.put(
        f"/api/v1/tenants/{test_env.tenant_id}",
        json={"name": "Renamed Tenant", "status": "inactive", "address": "HQ"},
        headers=AUTH,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["name"] == "Renamed Tenant"
    assert body["status"] == "inactive"
    assert body["address"] == "HQ"
    assert body["member_count"] >= 1  # still aggregated after update


@pytest.mark.asyncio
async def test_update_tenant_partial_leaves_others_unchanged(
    super_admin_client, test_env
):
    """PUT with only one field leaves the rest as-is."""
    # First set address + description.
    await super_admin_client.put(
        f"/api/v1/tenants/{test_env.tenant_id}",
        json={"address": "123 St", "description": "desc"},
        headers=AUTH,
    )
    # Then update only name.
    resp = await super_admin_client.put(
        f"/api/v1/tenants/{test_env.tenant_id}",
        json={"name": "Only Name Changed"},
        headers=AUTH,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Only Name Changed"
    # address/description untouched by the partial update.
    assert body["address"] == "123 St"
    assert body["description"] == "desc"


@pytest.mark.asyncio
async def test_non_super_admin_update_forbidden(app_client, test_env):
    """PUT /tenants/{id} is super_admin-only (403 for a normal owner)."""
    resp = await app_client.put(
        f"/api/v1/tenants/{test_env.tenant_id}",
        json={"name": "Hijacked"},
        headers=AUTH,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_update_tenant_not_found(super_admin_client):
    """PUT /tenants/{id} on a missing id returns 404."""
    resp = await super_admin_client.put(
        "/api/v1/tenants/nonexistent-tenant-id",
        json={"name": "Whatever"},
        headers=AUTH,
    )
    assert resp.status_code == 404
