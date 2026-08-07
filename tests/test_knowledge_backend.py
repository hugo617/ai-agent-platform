"""Knowledge-tiered backend Feature B — Category CRUD + scope 分级 tests.

Plan: ``harness/docs/plan-knowledge-tiered-backend.md`` slice 01.

This slice makes the foundation's ``knowledge_categories`` table + 5 platform
seed rows actually usable via a CRUD API with scope-tiered permissions:
super_admin → platform / group_admin → group / store owner/admin → store;
everyone lists their visible tiers (platform + their group + their store).

Chapter layout (matches slice 01 AC checklist):

- C. Category schemas — scope↔group_id/tenant_id mutual exclusion (AC1).
- R. Repository list_visible — three-tier visibility (AC2 + AC5).
- S. Service scope↔role enforcement (AC3 + AC6).
- A. API endpoints — GET/POST/PUT/DELETE /knowledge/categories (AC4).
- U. Unique constraint — same (scope, name, group_id, tenant_id) live (AC7).
- P. Platform seed visibility — store sees the 5 platform Categories (AC9).
"""

import uuid

import pytest
import pytest_asyncio

pytestmark = pytest.mark.smoke

AUTH = {"Authorization": "Bearer fake"}


def _uuid(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex}"


# ----------------------------------------------- C. Schemas + scope binding (AC1)
# The scope enum is a native ``pattern`` (single field) so it stays on the
# schema. The cross-field (scope ↔ group_id/tenant_id) binding can't be a
# ``model_validator`` (it would break 422 JSON serialization — see
# BookingCreate docstring + KnowledgeCategoryCreate docstring), so it lives in
# ``KnowledgeCategoryService._check_scope_binding`` as a BizError → 400. Tested directly
# here (static method, no db/casbin needed) and again through create().


@pytest.mark.asyncio
async def test_category_schema_rejects_invalid_scope_value():
    """AC1: scope must be one of platform/group/store (native pattern)."""
    from pydantic import ValidationError

    from app.schemas.document import KnowledgeCategoryCreate

    with pytest.raises(ValidationError):
        KnowledgeCategoryCreate(name="x", scope="chain")  # not a legal scope


@pytest.mark.asyncio
async def test_category_schema_accepts_all_three_scopes():
    """AC1: the schema accepts any of the three legal scope values."""
    from app.schemas.document import KnowledgeCategoryCreate

    KnowledgeCategoryCreate(name="平台类目", scope="platform")
    KnowledgeCategoryCreate(name="集团类目", scope="group", group_id=_uuid("g"))
    KnowledgeCategoryCreate(name="门店类目", scope="store", tenant_id=_uuid("t"))


@pytest.mark.asyncio
async def test_scope_binding_rejects_group_without_group_id():
    """AC1: scope=group without group_id → BizError (cross-field, service layer)."""
    from app.services.category_service import KnowledgeCategoryService
    from app.services.errors import BizError

    with pytest.raises(BizError):
        KnowledgeCategoryService._check_scope_binding("group", group_id=None, tenant_id=None)


@pytest.mark.asyncio
async def test_scope_binding_rejects_store_without_tenant_id():
    """AC1: scope=store without tenant_id → BizError."""
    from app.services.category_service import KnowledgeCategoryService
    from app.services.errors import BizError

    with pytest.raises(BizError):
        KnowledgeCategoryService._check_scope_binding("store", group_id=None, tenant_id=None)


@pytest.mark.asyncio
async def test_scope_binding_rejects_platform_with_group_id():
    """AC1: scope=platform forbids group_id."""
    from app.services.category_service import KnowledgeCategoryService
    from app.services.errors import BizError

    with pytest.raises(BizError):
        KnowledgeCategoryService._check_scope_binding("platform", group_id=_uuid("g"), tenant_id=None)


@pytest.mark.asyncio
async def test_scope_binding_rejects_platform_with_tenant_id():
    """AC1: scope=platform forbids tenant_id."""
    from app.services.category_service import KnowledgeCategoryService
    from app.services.errors import BizError

    with pytest.raises(BizError):
        KnowledgeCategoryService._check_scope_binding("platform", group_id=None, tenant_id=_uuid("t"))


@pytest.mark.asyncio
async def test_scope_binding_accepts_valid_combos():
    """AC1: the three legal (scope, group_id, tenant_id) combos all pass (no raise)."""
    from app.services.category_service import KnowledgeCategoryService

    # None should raise.
    KnowledgeCategoryService._check_scope_binding("platform", None, None)
    KnowledgeCategoryService._check_scope_binding("group", _uuid("g"), None)
    KnowledgeCategoryService._check_scope_binding("store", None, _uuid("t"))


# ----------------------------------------------------- R. Repository list_visible
# Builds a small fixture: one platform + one group (groupA, with 2 stores) +
# one other group (groupB, with 1 store), and one Category per tier. Then
# asserts each role sees exactly its visible tiers. AC2 + AC5.


async def _seed_category_fixture(db_session):
    """Seed a multi-tier multi-group layout for list_visible tests.

    Returns a dict with the ids so tests can assert against concrete rows.
    Layout:
      - 1 platform Category (visible to everyone)
      - groupA: 1 group Category + storeA1 + storeA2 (each with a store Cat)
      - groupB: 1 group Category + storeB1 (with a store Cat)
    """
    from app.models.group import Group, GroupTenant
    from app.models.knowledge_category import KnowledgeCategory
    from app.models.tenant import Tenant

    # Tenants + groups.
    t_a1 = Tenant(id=_uuid("t"), name="A1")
    t_a2 = Tenant(id=_uuid("t"), name="A2")
    t_b1 = Tenant(id=_uuid("t"), name="B1")
    g_a = Group(id=_uuid("g"), name="GroupA")
    g_b = Group(id=_uuid("g"), name="GroupB")
    db_session.add_all([t_a1, t_a2, t_b1, g_a, g_b])
    await db_session.flush()
    db_session.add_all([
        GroupTenant(group_id=g_a.id, tenant_id=t_a1.id),
        GroupTenant(group_id=g_a.id, tenant_id=t_a2.id),
        GroupTenant(group_id=g_b.id, tenant_id=t_b1.id),
    ])
    await db_session.flush()

    # Categories: 1 platform + 2 group + 3 store = 6 total.
    cats = {
        "platform": KnowledgeCategory(name="平台类目", scope="platform"),
        "groupA": KnowledgeCategory(name="A集团类目", scope="group", group_id=g_a.id),
        "groupB": KnowledgeCategory(name="B集团类目", scope="group", group_id=g_b.id),
        "storeA1": KnowledgeCategory(name="A1店类目", scope="store", tenant_id=t_a1.id),
        "storeA2": KnowledgeCategory(name="A2店类目", scope="store", tenant_id=t_a2.id),
        "storeB1": KnowledgeCategory(name="B1店类目", scope="store", tenant_id=t_b1.id),
    }
    db_session.add_all(cats.values())
    await db_session.flush()
    return {
        "t_a1": t_a1.id, "t_a2": t_a2.id, "t_b1": t_b1.id,
        "g_a": g_a.id, "g_b": g_b.id,
        **{k: v.id for k, v in cats.items()},
    }


@pytest.mark.asyncio
async def test_list_visible_store_sees_platform_plus_own_group_plus_own_store(db_session):
    """AC2/AC5: store view = platform + own group + own store (3 tiers)."""
    from app.repositories.knowledge_category import KnowledgeCategoryRepository

    ids = await _seed_category_fixture(db_session)
    repo = KnowledgeCategoryRepository(db_session)
    seen = await repo.list_visible(
        tenant_id=ids["t_a1"],
        group_id=ids["g_a"],
        include_all_tenants=False,
        is_group_admin=False,
    )
    seen_ids = {c.id for c in seen}
    assert {ids["platform"], ids["groupA"], ids["storeA1"]} <= seen_ids
    # Cannot see sibling store A2, other group B's group/store, etc.
    assert ids["storeA2"] not in seen_ids
    assert ids["groupB"] not in seen_ids
    assert ids["storeB1"] not in seen_ids


@pytest.mark.asyncio
async def test_list_visible_group_admin_sees_platform_plus_group_plus_sibling_stores(db_session):
    """AC2/AC5: group_admin view = platform + own group + ALL sibling stores in group."""
    from app.repositories.knowledge_category import KnowledgeCategoryRepository

    ids = await _seed_category_fixture(db_session)
    repo = KnowledgeCategoryRepository(db_session)
    seen = await repo.list_visible(
        tenant_id=ids["t_a1"],  # HQ tenant (group_admin's home)
        group_id=ids["g_a"],
        include_all_tenants=False,
        is_group_admin=True,
    )
    seen_ids = {c.id for c in seen}
    # platform + groupA + BOTH sibling stores (A1 + A2), not B.
    assert {ids["platform"], ids["groupA"], ids["storeA1"], ids["storeA2"]} <= seen_ids
    assert ids["groupB"] not in seen_ids
    assert ids["storeB1"] not in seen_ids


@pytest.mark.asyncio
async def test_list_visible_super_admin_sees_everything(db_session):
    """AC2/AC5: super_admin/hq_staff cross-tenant viewer sees all 6 categories."""
    from app.repositories.knowledge_category import KnowledgeCategoryRepository

    ids = await _seed_category_fixture(db_session)
    repo = KnowledgeCategoryRepository(db_session)
    seen = await repo.list_visible(
        tenant_id=ids["t_a1"],
        group_id=ids["g_a"],
        include_all_tenants=True,
        is_group_admin=False,
    )
    seen_ids = {c.id for c in seen}
    assert seen_ids == {
        ids["platform"], ids["groupA"], ids["groupB"],
        ids["storeA1"], ids["storeA2"], ids["storeB1"],
    }


@pytest.mark.asyncio
async def test_list_visible_cross_group_isolation_store_a1_cannot_see_group_b(db_session):
    """AC2/AC5: a GroupA store cannot see GroupB's group Category (cross-group isolation)."""
    from app.repositories.knowledge_category import KnowledgeCategoryRepository

    ids = await _seed_category_fixture(db_session)
    repo = KnowledgeCategoryRepository(db_session)
    seen = await repo.list_visible(
        tenant_id=ids["t_a1"],
        group_id=ids["g_a"],
        include_all_tenants=False,
        is_group_admin=False,
    )
    seen_names = {c.name for c in seen}
    assert "B集团类目" not in seen_names
    assert "B1店类目" not in seen_names


@pytest.mark.asyncio
async def test_list_visible_excludes_soft_deleted(db_session):
    """AC2: list_visible filters out soft-deleted rows."""
    from app.models.knowledge_category import KnowledgeCategory
    from app.repositories.knowledge_category import KnowledgeCategoryRepository

    ids = await _seed_category_fixture(db_session)
    # Soft-delete the platform Category — it should disappear from every view.
    plat = await db_session.get(KnowledgeCategory, ids["platform"])
    plat.is_deleted = True
    await db_session.flush()

    repo = KnowledgeCategoryRepository(db_session)
    seen = await repo.list_visible(
        tenant_id=ids["t_a1"], group_id=ids["g_a"],
        include_all_tenants=False, is_group_admin=False,
    )
    assert ids["platform"] not in {c.id for c in seen}


# ------------------------------------------------- S. Service scope↔role (AC3/AC6)
# The service layer enforces who may create/edit/delete which scope (G6). Tests
# drive the service directly so the scope↔role matrix is pinned without router
# noise. The casbin act gate (read/create/delete) needs a role binding, so each
# test takes ``test_env`` and binds the impersonated actor's role via the
# shared enforcer — mirroring what conftest's ``_build_client`` does. Member is
# read-only across ALL scopes (fails at the create/delete act gate).


def _bind_role(enforcer, user_id: str, role: str, tenant_id: str) -> None:
    """Bind a (user, tenant, role) + seed that role's knowledge policies.

    ``_make_casbin`` only seeds policies for ``test_env.tenant_id``; direct
    tests that operate on a different tenant need the (role, tenant, knowledge,
    act) policies added too. We seed the full knowledge read/create/delete set
    for owner/admin (member gets read-only) so the casbin act gate passes for
    the scope↔role logic under test. ``enforcer`` is the test's casbin
    enforcer (yielded by the ``patched_enforcer`` fixture, which also points
    the global ``get_enforcer`` at it).
    """
    e = enforcer
    e.add_role_for_user_in_domain(user_id, role, tenant_id)
    # Seed knowledge policies for THIS tenant (owner/admin: read+create+delete;
    # member: read only). Matches DEFAULT_*_PERMS knowledge rows.
    write_acts = [("knowledge", "read"), ("knowledge", "create"), ("knowledge", "delete")] \
        if role in ("owner", "admin") else [("knowledge", "read")]
    for obj, act in write_acts:
        # add_policy is idempotent in pycasbin (duplicate adds are no-ops).
        e.add_policy(role, tenant_id, obj, act)


@pytest_asyncio.fixture
async def patched_enforcer(test_env, monkeypatch):
    """Point ``check()`` at ``test_env.enforcer`` for direct-service tests.

    ``conftest._build_client`` does the same patch for HTTP tests; this fixture
    mirrors it so KnowledgeCategoryService called directly (not via ASGI) consults the
    test's seeded enforcer instead of the unrelated global one.
    """
    from app.core import casbin_enforcer as casbin_mod
    monkeypatch.setattr(casbin_mod, "get_enforcer", lambda: test_env.enforcer)
    yield test_env.enforcer


@pytest.mark.asyncio
async def test_service_create_store_category_by_store_owner_succeeds(patched_enforcer, db_session):
    """AC3/AC6: a store owner can create a scope=store Category for their store."""
    from app.schemas.document import KnowledgeCategoryCreate
    from app.services.category_service import KnowledgeCategoryService

    ids = await _seed_category_fixture(db_session)
    _bind_role(patched_enforcer, "u-owner-a1", "owner", ids["t_a1"])
    svc = KnowledgeCategoryService(db_session)
    cat = await svc.create(
        actor_id="u-owner-a1",
        tenant_id=ids["t_a1"],
        payload=KnowledgeCategoryCreate(name="A1新类目", scope="store", tenant_id=ids["t_a1"]),
        platform_role=None,
    )
    assert cat.scope == "store"
    assert cat.tenant_id == ids["t_a1"]


@pytest.mark.asyncio
async def test_service_create_platform_category_by_store_owner_rejected(patched_enforcer, db_session):
    """AC3/AC6: a store owner CANNOT create scope=platform (needs super_admin)."""
    from app.schemas.document import KnowledgeCategoryCreate
    from app.services.category_service import KnowledgeCategoryService
    from app.services.errors import BizError

    ids = await _seed_category_fixture(db_session)
    _bind_role(patched_enforcer, "u-owner-a1", "owner", ids["t_a1"])
    svc = KnowledgeCategoryService(db_session)
    with pytest.raises(BizError):
        await svc.create(
            actor_id="u-owner-a1",
            tenant_id=ids["t_a1"],
            payload=KnowledgeCategoryCreate(name="不该有的平台类目", scope="platform"),
            platform_role=None,
        )


@pytest.mark.asyncio
async def test_service_create_group_category_by_group_admin_succeeds(patched_enforcer, db_session):
    """AC3/AC6: a group_admin (HQ owner) can create scope=group for their group."""
    from sqlalchemy import select

    from app.models.group import Group
    from app.models.tenant import UserTenant
    from app.schemas.document import KnowledgeCategoryCreate
    from app.services.category_service import KnowledgeCategoryService

    ids = await _seed_category_fixture(db_session)
    # Promote A1's owner to be GroupA's HQ owner → derives group_admin.
    g_a = (await db_session.execute(select(Group).where(Group.id == ids["g_a"]))).scalar_one()
    g_a.headquarters_tenant_id = ids["t_a1"]
    db_session.add(UserTenant(user_id="u-ga-admin", tenant_id=ids["t_a1"], role="owner", valid_to=None))
    await db_session.flush()
    _bind_role(patched_enforcer, "u-ga-admin", "owner", ids["t_a1"])

    svc = KnowledgeCategoryService(db_session)
    cat = await svc.create(
        actor_id="u-ga-admin",
        tenant_id=ids["t_a1"],
        payload=KnowledgeCategoryCreate(name="GA新集团类目", scope="group", group_id=ids["g_a"]),
        platform_role=None,
    )
    assert cat.scope == "group"
    assert cat.group_id == ids["g_a"]


@pytest.mark.asyncio
async def test_service_create_group_category_by_non_group_admin_rejected(patched_enforcer, db_session):
    """AC3/AC6: a plain store owner (not group_admin) CANNOT create scope=group."""
    from app.schemas.document import KnowledgeCategoryCreate
    from app.services.category_service import KnowledgeCategoryService
    from app.services.errors import BizError

    ids = await _seed_category_fixture(db_session)
    _bind_role(patched_enforcer, "u-owner-a1", "owner", ids["t_a1"])
    svc = KnowledgeCategoryService(db_session)
    with pytest.raises(BizError):
        await svc.create(
            actor_id="u-owner-a1",
            tenant_id=ids["t_a1"],
            payload=KnowledgeCategoryCreate(name="不该有的集团类目", scope="group", group_id=ids["g_a"]),
            platform_role=None,
        )


@pytest.mark.asyncio
async def test_service_create_platform_category_by_group_admin_rejected(patched_enforcer, db_session):
    """AC6: a derived group_admin (NOT super_admin) cannot create scope=platform.

    ``_enforce_scope_role`` only short-circuits ``platform_role == "super_admin"``;
    a group_admin's platform_role is None, so it falls through to the
    scope=platform branch and is refused. Pins the last AC6 boundary.
    """
    from sqlalchemy import select

    from app.models.group import Group
    from app.models.tenant import UserTenant
    from app.schemas.document import KnowledgeCategoryCreate
    from app.services.category_service import KnowledgeCategoryService
    from app.services.errors import BizError

    ids = await _seed_category_fixture(db_session)
    # Promote A1's owner to GroupA's HQ owner → derives group_admin.
    g_a = (await db_session.execute(select(Group).where(Group.id == ids["g_a"]))).scalar_one()
    g_a.headquarters_tenant_id = ids["t_a1"]
    db_session.add(UserTenant(user_id="u-ga-admin", tenant_id=ids["t_a1"], role="owner", valid_to=None))
    await db_session.flush()
    _bind_role(patched_enforcer, "u-ga-admin", "owner", ids["t_a1"])

    svc = KnowledgeCategoryService(db_session)
    with pytest.raises(BizError):
        await svc.create(
            actor_id="u-ga-admin",
            tenant_id=ids["t_a1"],
            payload=KnowledgeCategoryCreate(name="GA不该有的平台类目", scope="platform"),
            platform_role=None,  # group_admin's platform_role is None, NOT super_admin
        )


@pytest.mark.asyncio
async def test_service_create_platform_category_by_super_admin_succeeds(db_session):
    """AC3/AC6: super_admin can create scope=platform (bypasses casbin gate)."""
    from app.schemas.document import KnowledgeCategoryCreate
    from app.services.category_service import KnowledgeCategoryService

    ids = await _seed_category_fixture(db_session)
    svc = KnowledgeCategoryService(db_session)
    cat = await svc.create(
        actor_id="u-super",
        tenant_id=ids["t_a1"],
        payload=KnowledgeCategoryCreate(name="超管平台类目", scope="platform"),
        platform_role="super_admin",
    )
    assert cat.scope == "platform"
    assert cat.group_id is None and cat.tenant_id is None


@pytest.mark.asyncio
async def test_service_member_cannot_create_any_scope(patched_enforcer, db_session):
    """AC3/AC6: member is read-only across ALL scopes (store too).

    Member has no knowledge:create grant → the casbin act gate refuses before
    the scope check runs. No BizError (scope check) is reached.
    """
    from app.schemas.document import KnowledgeCategoryCreate
    from app.services.category_service import KnowledgeCategoryService

    ids = await _seed_category_fixture(db_session)
    _bind_role(patched_enforcer, "u-member-a1", "member", ids["t_a1"])
    svc = KnowledgeCategoryService(db_session)
    with pytest.raises(PermissionError):
        await svc.create(
            actor_id="u-member-a1",
            tenant_id=ids["t_a1"],
            payload=KnowledgeCategoryCreate(name="member尝试", scope="store", tenant_id=ids["t_a1"]),
            platform_role=None,
        )


@pytest.mark.asyncio
async def test_service_member_cannot_update_or_delete(patched_enforcer, db_session):
    """AC3/AC6: member cannot update or delete any Category (write act gate)."""
    from app.schemas.document import KnowledgeCategoryUpdate
    from app.services.category_service import KnowledgeCategoryService

    ids = await _seed_category_fixture(db_session)
    _bind_role(patched_enforcer, "u-member-a1", "member", ids["t_a1"])
    svc = KnowledgeCategoryService(db_session)
    with pytest.raises(PermissionError):
        await svc.update(
            actor_id="u-member-a1", tenant_id=ids["t_a1"],
            category_id=ids["storeA1"],
            payload=KnowledgeCategoryUpdate(name="改名"),
            platform_role=None,
        )
    with pytest.raises(PermissionError):
        await svc.delete(
            actor_id="u-member-a1", tenant_id=ids["t_a1"],
            category_id=ids["storeA1"],
            platform_role=None,
        )


@pytest.mark.asyncio
async def test_service_create_duplicate_name_in_same_scope_rejected(patched_enforcer, db_session):
    """AC7: duplicate (scope, name, group_id/tenant_id) live row → BizError."""
    from app.schemas.document import KnowledgeCategoryCreate
    from app.services.category_service import KnowledgeCategoryService
    from app.services.errors import BizError

    ids = await _seed_category_fixture(db_session)
    _bind_role(patched_enforcer, "u-owner-a1", "owner", ids["t_a1"])
    svc = KnowledgeCategoryService(db_session)
    # storeA1 already has "A1店类目"; creating another with the same name fails.
    with pytest.raises(BizError):
        await svc.create(
            actor_id="u-owner-a1",
            tenant_id=ids["t_a1"],
            payload=KnowledgeCategoryCreate(name="A1店类目", scope="store", tenant_id=ids["t_a1"]),
            platform_role=None,
        )


@pytest.mark.asyncio
async def test_service_delete_soft_deletes_and_allows_name_reuse(patched_enforcer, db_session):
    """AC7: delete is soft; the name can be reused after deletion."""
    from app.schemas.document import KnowledgeCategoryCreate
    from app.services.category_service import KnowledgeCategoryService

    ids = await _seed_category_fixture(db_session)
    _bind_role(patched_enforcer, "u-owner-a1", "owner", ids["t_a1"])
    svc = KnowledgeCategoryService(db_session)
    await svc.delete(
        actor_id="u-owner-a1", tenant_id=ids["t_a1"],
        category_id=ids["storeA1"], platform_role=None,
    )
    # Name reuse now works (the soft-deleted row is exempt from the unique index).
    cat = await svc.create(
        actor_id="u-owner-a1",
        tenant_id=ids["t_a1"],
        payload=KnowledgeCategoryCreate(name="A1店类目", scope="store", tenant_id=ids["t_a1"]),
        platform_role=None,
    )
    assert cat.name == "A1店类目"
    assert cat.is_deleted is False


@pytest.mark.asyncio
async def test_service_update_name_and_sort_by_owner(patched_enforcer, db_session):
    """AC3: store owner can update name/sort_order on their store Category."""
    from app.schemas.document import KnowledgeCategoryUpdate
    from app.services.category_service import KnowledgeCategoryService

    ids = await _seed_category_fixture(db_session)
    _bind_role(patched_enforcer, "u-owner-a1", "owner", ids["t_a1"])
    svc = KnowledgeCategoryService(db_session)
    cat = await svc.update(
        actor_id="u-owner-a1", tenant_id=ids["t_a1"],
        category_id=ids["storeA1"],
        payload=KnowledgeCategoryUpdate(name="A1改名", sort_order=5),
        platform_role=None,
    )
    assert cat.name == "A1改名"
    assert cat.sort_order == 5


# ----------------------------------------------------- A. API endpoints (AC4)
# HTTP end-to-end through the FastAPI router. The owner/app_client is bound to
# ``test_env.tenant_id`` (casbin seeded there), so scope=store uses that tenant.
# super_admin_client exercises the scope=platform path.


@pytest.mark.asyncio
async def test_api_list_categories_empty_returns_200(app_client):
    """AC4: GET /knowledge/categories returns 200 + a list (possibly empty)."""
    resp = await app_client.get("/api/v1/knowledge/categories", headers=AUTH)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_api_create_store_category_by_owner_then_list(app_client):
    """AC4: owner POSTs a scope=store Category, then sees it in GET."""
    # Resolve the caller's tenant id from /auth/me (app_client is the owner).
    me = (await app_client.get("/api/v1/auth/me", headers=AUTH)).json()
    tenant_id = me["tenant_id"]
    payload = {"name": "门店话术集", "scope": "store", "tenant_id": tenant_id}
    resp = await app_client.post("/api/v1/knowledge/categories", json=payload, headers=AUTH)
    assert resp.status_code == 201, resp.text
    created = resp.json()
    assert created["scope"] == "store"
    assert created["tenant_id"] == tenant_id

    listed = (await app_client.get("/api/v1/knowledge/categories", headers=AUTH)).json()
    names = [c["name"] for c in listed]
    assert "门店话术集" in names


@pytest.mark.asyncio
async def test_api_create_platform_category_by_super_admin(super_admin_client, app_client):
    """AC4: super_admin POSTs scope=platform; a store owner then sees it listed.

    The platform Category is visible to every store (AC9 spirit: platform tier
    flows down to all stores in list_visible).
    """
    resp = await super_admin_client.post(
        "/api/v1/knowledge/categories",
        json={"name": "API平台类目", "scope": "platform"},
        headers=AUTH,
    )
    assert resp.status_code == 201, resp.text
    plat = resp.json()
    assert plat["scope"] == "platform"
    assert plat["group_id"] is None and plat["tenant_id"] is None

    # The owner (store view) now sees the platform Category.
    listed = (await app_client.get("/api/v1/knowledge/categories", headers=AUTH)).json()
    assert any(c["name"] == "API平台类目" and c["scope"] == "platform" for c in listed)


@pytest.mark.asyncio
async def test_api_create_platform_category_by_owner_forbidden(app_client):
    """AC4/AC6: a store owner POSTing scope=platform is rejected (needs super_admin)."""
    me = (await app_client.get("/api/v1/auth/me", headers=AUTH)).json()
    tenant_id = me["tenant_id"]
    payload = {"name": "不该有的平台类目", "scope": "platform", "tenant_id": tenant_id}
    resp = await app_client.post("/api/v1/knowledge/categories", json=payload, headers=AUTH)
    # schema rejects platform+tenant_id; service would reject platform by non-super.
    # Either way it's a 4xx, never 201.
    assert resp.status_code in (400, 422), resp.text


@pytest.mark.asyncio
async def test_api_update_category_by_owner(app_client):
    """AC4: owner PUTs name/sort on their store Category."""
    me = (await app_client.get("/api/v1/auth/me", headers=AUTH)).json()
    tenant_id = me["tenant_id"]
    created = (await app_client.post(
        "/api/v1/knowledge/categories",
        json={"name": "待改名", "scope": "store", "tenant_id": tenant_id},
        headers=AUTH,
    )).json()
    resp = await app_client.put(
        f"/api/v1/knowledge/categories/{created['id']}",
        json={"name": "已改名", "sort_order": 3},
        headers=AUTH,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["name"] == "已改名"
    assert resp.json()["sort_order"] == 3


@pytest.mark.asyncio
async def test_api_delete_category_by_owner(app_client):
    """AC4: owner DELETEs their store Category (soft-delete; vanishes from list)."""
    me = (await app_client.get("/api/v1/auth/me", headers=AUTH)).json()
    tenant_id = me["tenant_id"]
    created = (await app_client.post(
        "/api/v1/knowledge/categories",
        json={"name": "待删除", "scope": "store", "tenant_id": tenant_id},
        headers=AUTH,
    )).json()
    resp = await app_client.delete(
        f"/api/v1/knowledge/categories/{created['id']}", headers=AUTH
    )
    assert resp.status_code == 204, resp.text
    listed = (await app_client.get("/api/v1/knowledge/categories", headers=AUTH)).json()
    assert all(c["id"] != created["id"] for c in listed)


@pytest.mark.asyncio
async def test_api_member_cannot_create_category(member_client):
    """AC4/AC6: member POST is rejected at the casbin gate (no knowledge:create)."""
    me = (await member_client.get("/api/v1/auth/me", headers=AUTH)).json()
    tenant_id = me["tenant_id"]
    resp = await member_client.post(
        "/api/v1/knowledge/categories",
        json={"name": "member尝试", "scope": "store", "tenant_id": tenant_id},
        headers=AUTH,
    )
    assert resp.status_code == 403, resp.text


# --------------------------------------------- P. Platform seed visibility (AC9)
# create_all (test DB) skips the migration's INSERT...WHERE NOT EXISTS seed, so
# the 5 platform Categories are absent unless a test inserts them. This chapter
# seeds them manually (mirroring the migration's names) and asserts a store sees
# all 5 via list_visible — pinning that the seed ↔ list_visible contract holds.


@pytest.mark.asyncio
async def test_list_visible_store_sees_all_5_platform_seeds(db_session):
    """AC9: a store sees the 5 platform seed Categories the migration inserts."""
    from app.models.knowledge_category import KnowledgeCategory
    from app.models.tenant import Tenant
    from app.repositories.knowledge_category import KnowledgeCategoryRepository

    # Mirror the migration's 5 platform seed names (plan-foundation slice 01).
    seed_names = ["产品手册", "FAQ", "话术脚本", "服务规范", "促销文案"]
    store = Tenant(id=_uuid("t"), name="Store")
    db_session.add(store)
    await db_session.flush()
    db_session.add_all([
        KnowledgeCategory(name=n, scope="platform") for n in seed_names
    ])
    await db_session.flush()

    repo = KnowledgeCategoryRepository(db_session)
    seen = await repo.list_visible(
        tenant_id=store.id, group_id=None, include_all_tenants=False, is_group_admin=False,
    )
    seen_names = {c.name for c in seen}
    # All 5 platform seeds are visible from a store with no group.
    assert set(seed_names) <= seen_names
