"""Tests for the ``hq_staff`` platform role — HQ read-only cross-tenant viewer.

Background (feature ``hq-platform-role``): the platform splits HQ users into
two roles via ``User.platform_role``:

- ``super_admin`` — full power (unchanged, regression-guarded here)
- ``hq_staff`` — 总部业务员:cross-tenant **read** of every store's customers
  + groups (a HQ panorama), but writes fall through to casbin (no store role
  → 403). Group writes stay behind ``require_super_admin()`` so hq_staff can
  never reshape the org tree.

Test dimensions:
1. hq_staff reads across tenants (customers store list / HQ aggregate / groups)
2. hq_staff cannot write customers (POST/PUT/DELETE → 403)
3. hq_staff cannot mutate groups (POST → 403, require_super_admin)
4. hq_staff reads other in-store resources (GET /agents → 200, check() bypass)
5. super_admin behaviour does not regress
6. plain tenant users (owner/member) are still denied the HQ endpoints
"""

import pytest

AUTH = {"Authorization": "Bearer fake"}


# =============================================================
# hq_staff reads across tenants — the core HQ panorama capability.
# =============================================================


@pytest.mark.asyncio
async def test_hq_staff_list_profiles_sees_all_stores(hq_staff_client, db_session, test_env):
    """hq_staff GET /customers/profiles/ returns profiles across all stores."""
    from app.models.customer import Customer, CustomerProfile
    from app.models.tenant import Tenant

    # Seed two profiles in two tenants (hq_staff is read-only, no store write).
    own_c = Customer(identity_key="13800000020", name="Own")
    db_session.add(own_c)
    await db_session.flush()
    db_session.add(CustomerProfile(customer_id=own_c.id, tenant_id=test_env.tenant_id))
    other = "tnt-hq-other"
    db_session.add(Tenant(id=other, name="Other"))
    other_c = Customer(identity_key="13900000020", name="Other")
    db_session.add(other_c)
    await db_session.flush()
    db_session.add(CustomerProfile(customer_id=other_c.id, tenant_id=other))
    await db_session.commit()

    resp = await hq_staff_client.get("/api/v1/customers/profiles/", headers=AUTH)
    assert resp.status_code == 200, resp.text
    names = {p["customer"]["name"] for p in resp.json()}
    assert "Own" in names
    assert "Other" in names  # cross-tenant: hq_staff sees it


@pytest.mark.asyncio
async def test_hq_staff_hq_list_customers(hq_staff_client, db_session, test_env):
    """hq_staff GET /customers/ (HQ aggregation) → 200, sees all customers."""
    from app.models.customer import Customer, CustomerProfile
    from app.models.tenant import Tenant

    other = "tnt-hq-list-other"
    db_session.add(Tenant(id=other, name="Other"))
    c = Customer(identity_key="13800000021", name="HQSee")
    db_session.add(c)
    await db_session.flush()
    # Profiles in two tenants for the same customer.
    db_session.add(CustomerProfile(customer_id=c.id, tenant_id=test_env.tenant_id))
    db_session.add(CustomerProfile(customer_id=c.id, tenant_id=other))
    await db_session.commit()

    resp = await hq_staff_client.get("/api/v1/customers/", headers=AUTH)
    assert resp.status_code == 200, resp.text
    names = {c["name"] for c in resp.json()}
    assert "HQSee" in names


@pytest.mark.asyncio
async def test_hq_staff_customer_aggregate(hq_staff_client, db_session, test_env):
    """hq_staff GET /customers/{id}/aggregate → 200, cross-store profile_count."""
    from app.models.customer import Customer, CustomerProfile
    from app.models.tenant import Tenant

    other = "tnt-hq-agg-other"
    db_session.add(Tenant(id=other, name="Other"))
    c = Customer(identity_key="13800000022", name="Agg")
    db_session.add(c)
    await db_session.flush()
    db_session.add(CustomerProfile(customer_id=c.id, tenant_id=test_env.tenant_id))
    db_session.add(CustomerProfile(customer_id=c.id, tenant_id=other))
    await db_session.commit()

    resp = await hq_staff_client.get(
        f"/api/v1/customers/{c.id}/aggregate", headers=AUTH
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["id"] == c.id
    assert body["profile_count"] == 2


@pytest.mark.asyncio
async def test_hq_staff_list_groups_sees_all(hq_staff_client, db_session):
    """hq_staff GET /groups/ → 200, returns every group (cross-tenant read)."""
    from app.models.group import Group
    from app.models.tenant import Tenant

    db_session.add(Tenant(id="tnt-grp-a", name="A"))
    db_session.add(Tenant(id="tnt-grp-b", name="B"))
    g1 = Group(name="Group1", code="g1")
    g2 = Group(name="Group2", code="g2")
    db_session.add_all([g1, g2])
    await db_session.commit()

    resp = await hq_staff_client.get("/api/v1/groups/", headers=AUTH)
    assert resp.status_code == 200, resp.text
    names = {g["name"] for g in resp.json()}
    assert {"Group1", "Group2"} <= names


@pytest.mark.asyncio
async def test_hq_staff_read_agent(hq_staff_client):
    """hq_staff GET /agents/ → 200 (check() bypasses read for any object)."""
    resp = await hq_staff_client.get("/api/v1/agents/", headers=AUTH)
    assert resp.status_code == 200, resp.text


# =============================================================
# hq_staff writes — must be denied (read-only HQ viewer).
# =============================================================


@pytest.mark.asyncio
async def test_hq_staff_cannot_create_customer_profile(hq_staff_client):
    """hq_staff POST /customers/profiles/ → 403 (no customers:create policy)."""
    resp = await hq_staff_client.post(
        "/api/v1/customers/profiles/",
        json={"identity_key": "13800000023", "name": "NoCreate"},
        headers=AUTH,
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_hq_staff_cannot_update_customer_profile(hq_staff_client, db_session, test_env):
    """hq_staff PUT /customers/profiles/{id} → 403."""
    from app.models.customer import Customer, CustomerProfile

    c = Customer(identity_key="13800000024", name="NoUpd")
    db_session.add(c)
    await db_session.flush()
    p = CustomerProfile(customer_id=c.id, tenant_id=test_env.tenant_id)
    db_session.add(p)
    await db_session.commit()

    resp = await hq_staff_client.put(
        f"/api/v1/customers/profiles/{p.id}",
        json={"remark": "hack"},
        headers=AUTH,
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_hq_staff_cannot_delete_customer_profile(hq_staff_client, db_session, test_env):
    """hq_staff DELETE /customers/profiles/{id} → 403."""
    from app.models.customer import Customer, CustomerProfile

    c = Customer(identity_key="13800000025", name="NoDel")
    db_session.add(c)
    await db_session.flush()
    p = CustomerProfile(customer_id=c.id, tenant_id=test_env.tenant_id)
    db_session.add(p)
    await db_session.commit()

    resp = await hq_staff_client.delete(
        f"/api/v1/customers/profiles/{p.id}", headers=AUTH
    )
    assert resp.status_code == 403, resp.text


# =============================================================
# hq_staff vs Group writes — org tree is super_admin-only.
# =============================================================


@pytest.mark.asyncio
async def test_hq_staff_cannot_create_group(hq_staff_client):
    """hq_staff POST /groups/ → 403 (require_super_admin, org tree immutable)."""
    resp = await hq_staff_client.post(
        "/api/v1/groups/",
        json={"name": "NoGroup", "code": "nogroup"},
        headers=AUTH,
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_hq_staff_cannot_delete_group(hq_staff_client, db_session):
    """hq_staff DELETE /groups/{id} → 403 (require_super_admin)."""
    from app.models.group import Group

    g = Group(name="ToDelete", code="todelete")
    db_session.add(g)
    await db_session.commit()

    resp = await hq_staff_client.delete(f"/api/v1/groups/{g.id}", headers=AUTH)
    assert resp.status_code == 403, resp.text


# =============================================================
# hq_staff cannot reach platform-config endpoints (super_admin only).
# =============================================================


@pytest.mark.asyncio
async def test_hq_staff_cannot_manage_platform_llm_config(hq_staff_client):
    """hq_staff GET platform-level /settings/llm/platform → 403 (super_admin only)."""
    resp = await hq_staff_client.get("/api/v1/settings/llm/platform", headers=AUTH)
    assert resp.status_code == 403, resp.text


# =============================================================
# super_admin non-regression — behaviour unchanged.
# =============================================================


@pytest.mark.asyncio
async def test_super_admin_still_reads_hq_customers(super_admin_client):
    """super_admin HQ list still works after the guard broadened to hq_staff."""
    resp = await super_admin_client.get("/api/v1/customers/", headers=AUTH)
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_super_admin_still_creates_group(super_admin_client):
    """super_admin can still create groups (require_super_admin unchanged)."""
    resp = await super_admin_client.post(
        "/api/v1/groups/",
        json={"name": "SA-Group", "code": "sa-group"},
        headers=AUTH,
    )
    assert resp.status_code == 201, resp.text


# =============================================================
# Plain tenant users still denied the HQ panorama endpoints.
# =============================================================


@pytest.mark.asyncio
async def test_owner_denied_hq_customer_list(app_client):
    """owner (no platform_role) GET /customers/ → 403 (not a cross-tenant viewer)."""
    resp = await app_client.get("/api/v1/customers/", headers=AUTH)
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_member_denied_hq_customer_aggregate(member_client):
    """member GET /customers/{id}/aggregate → 403 (not a cross-tenant viewer)."""
    resp = await member_client.get(
        "/api/v1/customers/some-id/aggregate", headers=AUTH
    )
    assert resp.status_code == 403, resp.text


# =============================================================
# is_cross_tenant_viewer unit contract.
# =============================================================


def test_is_cross_tenant_viewer_contract():
    """The helper recognises super_admin + hq_staff and rejects everything else."""
    from app.services.permission_service import is_cross_tenant_viewer

    assert is_cross_tenant_viewer("super_admin") is True
    assert is_cross_tenant_viewer("hq_staff") is True
    assert is_cross_tenant_viewer(None) is False
    assert is_cross_tenant_viewer("owner") is False
    assert is_cross_tenant_viewer("member") is False
    assert is_cross_tenant_viewer("") is False
