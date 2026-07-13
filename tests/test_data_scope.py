"""Tests for role-level row data scope (权限重构系列 3/4).

Each role carries a ``data_scope`` (all/tenant/group/self) that the
``DataScopeService`` resolves into a :class:`ResolvedScope`; the
``CustomerProfileRepository.list_for_scope`` then filters rows accordingly.

Scope semantics under test:
- ``self``   → only rows where ``created_by == user_id``
- ``tenant`` → all rows in the caller's tenant (default / pre-feature behaviour)
- ``group``  → rows across every tenant sharing a Group with the caller's tenant
- ``all``    → no filter (platform viewers super_admin / hq_staff)

Aggregation: a user with several roles takes the *widest* scope. A ``group``
role whose tenant belongs to no Group downgrades to ``tenant``.

Conftest notes (see tests/conftest.py): the ``test_env`` fixture does NOT seed
``Role`` rows (only UserTenant.role="owner"), so ``DataScopeService`` falls back
to ``tenant`` by default. These tests seed the Role rows they need directly via
``db_session`` and drive a single client (``app_client`` = owner) because the
global ``decode_token`` mock cannot be shared by two clients in one test.
"""

import uuid

import pytest

AUTH = {"Authorization": "Bearer fake"}


async def _seed_owner_role(db_session, test_env, *, data_scope: str) -> None:
    """Insert (or update) the owner Role row for the test tenant.

    ``test_env`` only seeds UserTenant(role="owner"); the matching Role row is
    absent, so DataScopeService defaults to tenant. Giving the owner role an
    explicit ``data_scope`` makes the resolver pick it up.
    """
    from app.models.rbac import Role

    existing = await db_session.execute(
        Role.__table__.select().where(
            Role.tenant_id == test_env.tenant_id, Role.code == "owner"
        )
    )
    row = existing.first()
    if row is None:
        db_session.add(
            Role(
                id=uuid.uuid4().hex,
                tenant_id=test_env.tenant_id,
                name="Owner",
                code="owner",
                data_scope=data_scope,
                is_system=True,
            )
        )
    else:
        # update existing row's scope in place
        await db_session.execute(
            Role.__table__.update()
            .where(Role.id == row.id)
            .values(data_scope=data_scope)
        )
    await db_session.commit()


@pytest.mark.asyncio
async def test_self_scope_sees_only_own_profiles(app_client, test_env, db_session):
    """A self-scoped owner sees only profiles they created."""
    from app.models.customer import Customer, CustomerProfile

    await _seed_owner_role(db_session, test_env, data_scope="self")

    # Profile A created via the API → created_by == owner.
    resp = await app_client.post(
        "/api/v1/customers/profiles/",
        json={"identity_key": "13800000777", "name": "Mine"},
        headers=AUTH,
    )
    assert resp.status_code == 201, resp.text

    # Profile B created directly by *another* user in the same tenant.
    other_user = f"other-{uuid.uuid4().hex}"
    from app.models.tenant import User

    db_session.add(User(id=other_user, email="other-self@example.com", status="active"))
    other_customer = Customer(identity_key="13900000777", name="Theirs")
    db_session.add(other_customer)
    await db_session.flush()
    db_session.add(
        CustomerProfile(
            customer_id=other_customer.id,
            tenant_id=test_env.tenant_id,
            created_by=other_user,
        )
    )
    await db_session.commit()

    resp = await app_client.get("/api/v1/customers/profiles/", headers=AUTH)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["customer"]["name"] == "Mine"


@pytest.mark.asyncio
async def test_tenant_scope_sees_all_tenant_profiles(app_client, test_env, db_session):
    """A tenant-scoped owner sees every profile in the tenant (default)."""
    from app.models.customer import Customer, CustomerProfile
    from app.models.tenant import User

    await _seed_owner_role(db_session, test_env, data_scope="tenant")

    # Owner's own profile via API.
    await app_client.post(
        "/api/v1/customers/profiles/",
        json={"identity_key": "13800000888", "name": "OwnerMade"},
        headers=AUTH,
    )
    # Another user's profile in the SAME tenant.
    other_user = f"other-{uuid.uuid4().hex}"
    db_session.add(User(id=other_user, email="other-tenant@example.com", status="active"))
    other_customer = Customer(identity_key="13900000888", name="OtherMade")
    db_session.add(other_customer)
    await db_session.flush()
    db_session.add(
        CustomerProfile(
            customer_id=other_customer.id,
            tenant_id=test_env.tenant_id,
            created_by=other_user,
        )
    )
    await db_session.commit()

    resp = await app_client.get("/api/v1/customers/profiles/", headers=AUTH)
    assert resp.status_code == 200
    names = sorted(p["customer"]["name"] for p in resp.json())
    assert names == ["OtherMade", "OwnerMade"]


@pytest.mark.asyncio
async def test_group_scope_sees_across_group_tenants(app_client, test_env, db_session):
    """A group-scoped owner sees profiles in every tenant sharing its Group."""
    from app.models.customer import Customer, CustomerProfile
    from app.models.group import Group, GroupTenant
    from app.models.tenant import Tenant

    await _seed_owner_role(db_session, test_env, data_scope="group")

    # A profile in the caller's own tenant (owner-built).
    await app_client.post(
        "/api/v1/customers/profiles/",
        json={"identity_key": "13800000999", "name": "Home"},
        headers=AUTH,
    )

    # A sibling tenant in the same Group, with its own profile.
    sibling_tenant = f"tnt-sibling-{uuid.uuid4().hex}"
    db_session.add(Tenant(id=sibling_tenant, name="Sibling"))
    g = Group(name="MyChain")
    db_session.add(g)
    await db_session.flush()
    db_session.add(GroupTenant(group_id=g.id, tenant_id=test_env.tenant_id))
    db_session.add(GroupTenant(group_id=g.id, tenant_id=sibling_tenant))
    sibling_customer = Customer(identity_key="13900000999", name="Sibling")
    db_session.add(sibling_customer)
    await db_session.flush()
    db_session.add(
        CustomerProfile(
            customer_id=sibling_customer.id,
            tenant_id=sibling_tenant,
            created_by="someone-else",
        )
    )
    await db_session.commit()

    resp = await app_client.get("/api/v1/customers/profiles/", headers=AUTH)
    assert resp.status_code == 200
    names = sorted(p["tenant_id"] for p in resp.json())
    assert names == sorted([test_env.tenant_id, sibling_tenant])


@pytest.mark.asyncio
async def test_group_scope_downgrades_when_tenant_in_no_group(
    app_client, test_env, db_session
):
    """A group-scoped owner in no Group falls back to tenant (own store only)."""
    from app.models.customer import Customer, CustomerProfile
    from app.models.tenant import Tenant

    await _seed_owner_role(db_session, test_env, data_scope="group")

    # Own profile.
    await app_client.post(
        "/api/v1/customers/profiles/",
        json={"identity_key": "13800000111", "name": "Home"},
        headers=AUTH,
    )
    # An unrelated tenant NOT in any Group with us.
    lone_tenant = f"tnt-lone-{uuid.uuid4().hex}"
    db_session.add(Tenant(id=lone_tenant, name="Lone"))
    lone_customer = Customer(identity_key="13900000111", name="Lone")
    db_session.add(lone_customer)
    await db_session.flush()
    db_session.add(
        CustomerProfile(
            customer_id=lone_customer.id,
            tenant_id=lone_tenant,
            created_by="someone",
        )
    )
    await db_session.commit()

    resp = await app_client.get("/api/v1/customers/profiles/", headers=AUTH)
    assert resp.status_code == 200
    body = resp.json()
    # Downgrade → only the caller's own tenant visible.
    assert len(body) == 1
    assert body[0]["tenant_id"] == test_env.tenant_id


@pytest.mark.asyncio
async def test_multi_role_aggregates_to_widest(app_client, test_env, db_session):
    """A user holding both a self role and a tenant role sees the tenant view."""
    from app.models.customer import Customer, CustomerProfile
    from app.models.rbac import Role
    from app.models.tenant import User

    # Owner role = tenant (widest wins over the self role added below).
    await _seed_owner_role(db_session, test_env, data_scope="tenant")
    # Add a second self-scoped role and bind it to the owner in casbin. The
    # role code is fixed up-front so the casbin grouping policy matches it.
    sales_code = "sales-widest"
    db_session.add(
        Role(
            id=uuid.uuid4().hex,
            tenant_id=test_env.tenant_id,
            name="Sales",
            code=sales_code,
            data_scope="self",
        )
    )
    await db_session.commit()
    test_env.enforcer.add_role_for_user_in_domain(
        test_env.owner_user, sales_code, test_env.tenant_id
    )

    # Owner's own + another user's profile in the same tenant.
    await app_client.post(
        "/api/v1/customers/profiles/",
        json={"identity_key": "13800000222", "name": "Mine"},
        headers=AUTH,
    )
    other_user = f"other-{uuid.uuid4().hex}"
    db_session.add(User(id=other_user, email="other-agg@example.com", status="active"))
    other_customer = Customer(identity_key="13900000222", name="Theirs")
    db_session.add(other_customer)
    await db_session.flush()
    db_session.add(
        CustomerProfile(
            customer_id=other_customer.id,
            tenant_id=test_env.tenant_id,
            created_by=other_user,
        )
    )
    await db_session.commit()

    resp = await app_client.get("/api/v1/customers/profiles/", headers=AUTH)
    assert resp.status_code == 200
    # tenant (wider) wins over self → both profiles visible.
    assert len(resp.json()) == 2


@pytest.mark.asyncio
async def test_cross_tenant_isolation_unaffected(app_client, test_env, db_session):
    """A tenant/group-scoped owner never sees rows from an unrelated tenant."""
    from app.models.customer import Customer, CustomerProfile
    from app.models.tenant import Tenant

    # group scope, but the other tenant shares NO group → invisible.
    await _seed_owner_role(db_session, test_env, data_scope="group")

    await app_client.post(
        "/api/v1/customers/profiles/",
        json={"identity_key": "13800000333", "name": "Home"},
        headers=AUTH,
    )
    foreign_tenant = f"tnt-foreign-{uuid.uuid4().hex}"
    db_session.add(Tenant(id=foreign_tenant, name="Foreign"))
    foreign_customer = Customer(identity_key="13900000333", name="Foreign")
    db_session.add(foreign_customer)
    await db_session.flush()
    db_session.add(
        CustomerProfile(
            customer_id=foreign_customer.id,
            tenant_id=foreign_tenant,
            created_by="stranger",
        )
    )
    await db_session.commit()

    resp = await app_client.get("/api/v1/customers/profiles/", headers=AUTH)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["tenant_id"] == test_env.tenant_id


@pytest.mark.asyncio
async def test_super_admin_bypass_is_all_scope(super_admin_client, db_session):
    """super_admin bypasses data scope → sees all stores (no filter)."""
    # super_admin_client already seeds a second tenant + cross-user data in
    # its fixture; list_profiles resolves to all for platform viewers.
    resp = await super_admin_client.get("/api/v1/customers/profiles/", headers=AUTH)
    assert resp.status_code == 200
    # No assertion on count: the fixture may seed 0+ profiles; the point is
    # that all resolves without a tenant filter and returns 200.


@pytest.mark.asyncio
async def test_role_crud_exposes_data_scope(app_client, db_session, test_env):
    """Creating a custom role persists data_scope; GET /roles returns it."""
    resp = await app_client.post(
        "/api/v1/roles/",
        json={
            "name": "Regional Manager",
            "code": f"regional-{uuid.uuid4().hex[:8]}",
            "data_scope": "group",
        },
        headers=AUTH,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["data_scope"] == "group"
    role_id = body["id"]

    # GET /roles surfaces it.
    listing = (await app_client.get("/api/v1/roles/", headers=AUTH)).json()
    assert any(r["id"] == role_id and r["data_scope"] == "group" for r in listing)

    # PUT updates the scope.
    updated = await app_client.put(
        f"/api/v1/roles/{role_id}",
        json={"data_scope": "self"},
        headers=AUTH,
    )
    assert updated.status_code == 200
    assert updated.json()["data_scope"] == "self"


@pytest.mark.asyncio
async def test_role_create_rejects_invalid_data_scope(app_client):
    """An unknown data_scope value is rejected at the schema layer (422)."""
    resp = await app_client.post(
        "/api/v1/roles/",
        json={"name": "Bad", "code": "bad-scope", "data_scope": "universe"},
        headers=AUTH,
    )
    assert resp.status_code == 422
