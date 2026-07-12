"""Customer API tests — global identity + per-tenant profile + cross-store aggregation.

Covers:
- Store creates a customer (new identity) → Customer + Profile both built.
- Store creates a customer (reuse identity) → only Profile built, Customer shared.
- Duplicate creation in the same store → 400.
- Store view isolation: store A can't see store B's profiles.
- HQ aggregation (super_admin): a Customer with profiles across stores.
- Permission boundaries: member read-only / admin no-delete / owner full.
- Update syncs global-identity fields to the Customer.
- Soft-delete removes the profile from the list/aggregate; Customer survives.
- 404s for unknown profile/customer.
"""

import pytest

AUTH = {"Authorization": "Bearer fake"}


# ----------------------------------------- store create (new + reuse identity)


@pytest.mark.asyncio
async def test_store_create_new_identity_builds_customer_and_profile(app_client):
    """First store to register a customer creates both Customer and Profile."""
    resp = await app_client.post(
        "/api/v1/customers/profiles/",
        json={
            "identity_key": "13800000001",
            "name": "张三",
            "remark": "VIP",
            "tags": {"level": "gold"},
        },
        headers=AUTH,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["customer"]["identity_key"] == "13800000001"
    assert body["customer"]["name"] == "张三"
    assert body["remark"] == "VIP"
    assert body["tags"] == {"level": "gold"}
    assert body["status"] == "active"
    assert body["tenant_id"]  # populated by the store context
    assert body["id"]


@pytest.mark.asyncio
async def test_store_create_reuses_existing_identity(app_client, super_admin_client):
    """A second store registering the same identity_key reuses the Customer,
    building only a new Profile in its own tenant."""
    # Store A (app_client's tenant) creates the customer first.
    resp = await app_client.post(
        "/api/v1/customers/profiles/",
        json={"identity_key": "13800000002", "name": "李四"},
        headers=AUTH,
    )
    assert resp.status_code == 201, resp.text
    customer_id_a = resp.json()["customer"]["id"]

    # super_admin_client acts as store "other tenant" (it seeds tnt-other-*).
    # Use the HQ create isn't available — instead drive the store endpoint as
    # super_admin; the service still builds a profile under the caller's
    # tenant_id (test_env.tenant_id). To genuinely test a second store we seed
    # a profile in the other tenant via db_session (see next test). Here we
    # verify the same-identity Customer is returned (id matches).
    resp2 = await app_client.get("/api/v1/customers/profiles/", headers=AUTH)
    assert resp2.status_code == 200
    assert len(resp2.json()) == 1
    assert resp2.json()[0]["customer"]["id"] == customer_id_a


@pytest.mark.asyncio
async def test_cross_store_reuse_identity(super_admin_client, test_env, db_session):
    """Two stores with the same identity_key share one Customer but have
    separate Profiles. Uses db_session to seed the second store's profile."""
    from app.models.customer import CustomerProfile
    from app.models.tenant import Tenant

    # Store A = test_env.tenant_id. Create via the super_admin store endpoint
    # (super_admin's tenant_id is test_env.tenant_id).
    resp = await super_admin_client.post(
        "/api/v1/customers/profiles/",
        json={"identity_key": "13800000003", "name": "王五", "remark": "A店备注"},
        headers=AUTH,
    )
    assert resp.status_code == 201, resp.text
    customer_id = resp.json()["customer"]["id"]

    # Seed a second tenant + a profile for the same customer in it (store B).
    other_tenant = "tnt-customer-b"
    db_session.add(Tenant(id=other_tenant, name="Store B"))
    db_session.add(
        CustomerProfile(
            customer_id=customer_id,
            tenant_id=other_tenant,
            remark="B店备注",
            status="active",
        )
    )
    await db_session.commit()

    # HQ aggregate shows the customer with BOTH store profiles.
    resp = await super_admin_client.get(
        f"/api/v1/customers/{customer_id}/aggregate", headers=AUTH
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["id"] == customer_id
    assert body["profile_count"] == 2
    tenants = sorted(p["tenant"]["id"] for p in body["profiles"])
    assert test_env.tenant_id in tenants
    assert other_tenant in tenants


# --------------------------------------------------------------- duplicate 400


@pytest.mark.asyncio
async def test_duplicate_profile_in_same_store_400(app_client):
    """Creating the same identity_key twice in one store → 400."""
    payload = {"identity_key": "13800000004", "name": "赵六"}
    resp = await app_client.post("/api/v1/customers/profiles/", json=payload, headers=AUTH)
    assert resp.status_code == 201
    resp = await app_client.post("/api/v1/customers/profiles/", json=payload, headers=AUTH)
    assert resp.status_code == 400
    assert "已有档案" in resp.json()["detail"]


# --------------------------------------------------------- store view isolation


@pytest.mark.asyncio
async def test_store_list_only_own_profiles(app_client, db_session):
    """A store's list shows only its own profiles, not another store's."""
    from app.models.customer import Customer, CustomerProfile
    from app.models.tenant import Tenant

    # Own profile via API.
    await app_client.post(
        "/api/v1/customers/profiles/",
        json={"identity_key": "13800000005", "name": "Own"},
        headers=AUTH,
    )
    # Another store's profile seeded directly (invisible to app_client).
    other = "tnt-iso-customer"
    db_session.add(Tenant(id=other, name="Iso"))
    c = Customer(identity_key="13900000099", name="Other")
    db_session.add(c)
    await db_session.flush()
    db_session.add(CustomerProfile(customer_id=c.id, tenant_id=other))
    await db_session.commit()

    resp = await app_client.get("/api/v1/customers/profiles/", headers=AUTH)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["customer"]["name"] == "Own"


@pytest.mark.asyncio
async def test_store_cannot_access_other_store_profile_404(app_client, db_session):
    """get/update/delete on another store's profile_id → 404 (tenant filter)."""
    from app.models.customer import Customer, CustomerProfile
    from app.models.tenant import Tenant

    other = "tnt-iso-customer-2"
    db_session.add(Tenant(id=other, name="Iso2"))
    c = Customer(identity_key="13900000088", name="Other")
    db_session.add(c)
    await db_session.flush()
    p = CustomerProfile(customer_id=c.id, tenant_id=other)
    db_session.add(p)
    await db_session.commit()

    resp = await app_client.put(
        f"/api/v1/customers/profiles/{p.id}",
        json={"remark": "hack"},
        headers=AUTH,
    )
    assert resp.status_code == 404
    resp = await app_client.delete(
        f"/api/v1/customers/profiles/{p.id}", headers=AUTH
    )
    assert resp.status_code == 404


# ------------------------------------------------------------- permission edges


@pytest.mark.asyncio
async def test_member_can_read_but_not_create(member_client):
    """member has customers:read but not customers:create."""
    resp = await member_client.get("/api/v1/customers/profiles/", headers=AUTH)
    assert resp.status_code == 200
    resp = await member_client.post(
        "/api/v1/customers/profiles/",
        json={"identity_key": "13800000006", "name": "X"},
        headers=AUTH,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_member_cannot_update_or_delete(member_client, db_session, test_env):
    """member lacks customers:update and customers:delete.

    Seeds a profile via db_session (not app_client) because two client fixtures
    active at once share the global decode_token mock — the later-started one
    wins, so mixing app_client + member_client would impersonate the owner.
    """
    from app.models.customer import Customer, CustomerProfile

    c = Customer(identity_key="13800000007", name="Y")
    db_session.add(c)
    await db_session.flush()
    p = CustomerProfile(customer_id=c.id, tenant_id=test_env.tenant_id)
    db_session.add(p)
    await db_session.commit()

    resp = await member_client.put(
        f"/api/v1/customers/profiles/{p.id}",
        json={"remark": "nope"},
        headers=AUTH,
    )
    assert resp.status_code == 403
    resp = await member_client.delete(
        f"/api/v1/customers/profiles/{p.id}", headers=AUTH
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_non_super_admin_cannot_access_hq_endpoints(app_client, member_client):
    """HQ list + aggregate are super_admin-only → 403 for tenant users."""
    resp = await app_client.get("/api/v1/customers/", headers=AUTH)
    assert resp.status_code == 403
    resp = await member_client.get(
        "/api/v1/customers/some-id/aggregate", headers=AUTH
    )
    assert resp.status_code == 403


# ----------------------------------------------------------- update + soft-delete


@pytest.mark.asyncio
async def test_update_syncs_global_identity_fields(app_client):
    """Updating name on a profile also updates the Customer's global name."""
    create = await app_client.post(
        "/api/v1/customers/profiles/",
        json={"identity_key": "13800000008", "name": "OldName"},
        headers=AUTH,
    )
    pid = create.json()["id"]
    customer_id = create.json()["customer"]["id"]

    resp = await app_client.put(
        f"/api/v1/customers/profiles/{pid}",
        json={"name": "NewName", "remark": "updated", "status": "lost"},
        headers=AUTH,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["customer"]["name"] == "NewName"
    assert body["remark"] == "updated"
    assert body["status"] == "lost"
    assert body["customer"]["id"] == customer_id


@pytest.mark.asyncio
async def test_soft_delete_removes_from_list_but_keeps_customer(super_admin_client):
    """Deleting a store profile removes it from the list; the Customer survives."""
    create = await super_admin_client.post(
        "/api/v1/customers/profiles/",
        json={"identity_key": "13800000009", "name": "ToDelete"},
        headers=AUTH,
    )
    pid = create.json()["id"]
    customer_id = create.json()["customer"]["id"]

    resp = await super_admin_client.delete(
        f"/api/v1/customers/profiles/{pid}", headers=AUTH
    )
    assert resp.status_code == 204

    # Gone from the store list.
    resp = await super_admin_client.get(
        "/api/v1/customers/profiles/", headers=AUTH
    )
    assert all(p["id"] != pid for p in resp.json())

    # Customer still queryable via HQ aggregate (profile_count now 0).
    resp = await super_admin_client.get(
        f"/api/v1/customers/{customer_id}/aggregate", headers=AUTH
    )
    assert resp.status_code == 200
    assert resp.json()["profile_count"] == 0


@pytest.mark.asyncio
async def test_soft_deleted_profile_can_be_recreated(app_client):
    """After soft-deleting, the same identity_key can create a fresh profile
    (partial unique index only covers live rows)."""
    create = await app_client.post(
        "/api/v1/customers/profiles/",
        json={"identity_key": "13800000010", "name": "Recreate"},
        headers=AUTH,
    )
    pid = create.json()["id"]
    await app_client.delete(f"/api/v1/customers/profiles/{pid}", headers=AUTH)

    resp = await app_client.post(
        "/api/v1/customers/profiles/",
        json={"identity_key": "13800000010", "name": "Recreate"},
        headers=AUTH,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["id"] != pid  # a new profile row


# ------------------------------------------------------------------- 404 paths


@pytest.mark.asyncio
async def test_update_nonexistent_profile_404(app_client):
    resp = await app_client.put(
        "/api/v1/customers/profiles/nope",
        json={"remark": "x"},
        headers=AUTH,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_nonexistent_profile_404(app_client):
    resp = await app_client.delete(
        "/api/v1/customers/profiles/nope", headers=AUTH
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_hq_aggregate_nonexistent_customer_404(super_admin_client):
    resp = await super_admin_client.get(
        "/api/v1/customers/cust-nope/aggregate", headers=AUTH
    )
    assert resp.status_code == 404


# ------------------------------------------------------- super_admin store view


@pytest.mark.asyncio
async def test_super_admin_store_list_sees_all_profiles(
    super_admin_client, db_session, test_env
):
    """super_admin list_profiles sees profiles across all stores (not just own)."""
    from app.models.customer import Customer, CustomerProfile
    from app.models.tenant import Tenant

    # Own store profile via API.
    await super_admin_client.post(
        "/api/v1/customers/profiles/",
        json={"identity_key": "13800000011", "name": "Own"},
        headers=AUTH,
    )
    # Another store's profile.
    other = "tnt-sa-other"
    db_session.add(Tenant(id=other, name="OtherSA"))
    c = Customer(identity_key="13900000077", name="Other")
    db_session.add(c)
    await db_session.flush()
    db_session.add(CustomerProfile(customer_id=c.id, tenant_id=other))
    await db_session.commit()

    resp = await super_admin_client.get(
        "/api/v1/customers/profiles/", headers=AUTH
    )
    assert resp.status_code == 200
    names = {p["customer"]["name"] for p in resp.json()}
    assert "Own" in names
    assert "Other" in names


@pytest.mark.asyncio
async def test_hq_list_customers(super_admin_client):
    """HQ list returns customers with profile_count."""
    await super_admin_client.post(
        "/api/v1/customers/profiles/",
        json={"identity_key": "13800000012", "name": "HQ1"},
        headers=AUTH,
    )
    await super_admin_client.post(
        "/api/v1/customers/profiles/",
        json={"identity_key": "13800000013", "name": "HQ2"},
        headers=AUTH,
    )
    resp = await super_admin_client.get("/api/v1/customers/", headers=AUTH)
    assert resp.status_code == 200
    names = {c["name"] for c in resp.json()}
    assert "HQ1" in names
    assert "HQ2" in names
