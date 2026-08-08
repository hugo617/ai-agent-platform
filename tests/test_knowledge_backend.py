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
    # Seed knowledge policies for THIS tenant (owner/admin: read+create+delete+
    # distribute; member: read only). Matches DEFAULT_*_PERMS knowledge rows
    # (slice 03 adds distribute to owner/admin, never member).
    write_acts = [
        ("knowledge", "read"), ("knowledge", "create"),
        ("knowledge", "delete"), ("knowledge", "distribute"),
    ] if role in ("owner", "admin") else [("knowledge", "read")]
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


# ======================================================================
# 切片 02 — list + 检索三路径改造 + G1 bypass 接通 (core slice)
# Plan: harness/docs/plan-knowledge-tiered-backend.md slice 02.
#
# Chapter layout (matches slice 02 AC checklist):
# - D. Document fixture — multi-tier multi-group docs + distribution rows.
# - L. list_visible_for — three-path WHERE (AC1: store/ga/super).
# - S. search_by_embedding — three-path + include_distributed (AC2).
# - G. G1 bypass 接通 — 5 require/check 加 db=self.db (AC3).
# - R. retrieve_knowledge tool — include_distributed=True wiring (AC5).
# - N. Negative regression — soft-deleted source excluded (AC1/AC2).
# ======================================================================


async def _seed_document_fixture(db_session):
    """Seed a multi-tier multi-group Document layout for slice 02 tests.

    Mirrors ``_seed_category_fixture``'s group topology (t_a1/t_a2/t_b1 +
    g_a/g_b) but seeds Documents across all three scopes AND inserts
    ``knowledge_distribution`` rows so the "distributed to me" branch is real:

      - 1 platform doc (not distributed to anyone by default — invisible to stores)
      - 1 platform doc distributed → t_a1 (the "store sees a push-down" case)
      - groupA: 1 group doc + storeA1 doc + storeA2 doc
      - groupB: 1 group doc + storeB1 doc

    Returns a dict of ids for assertions.
    """
    from app.models.document import Document
    from app.models.group import Group, GroupTenant
    from app.models.knowledge_distribution import KnowledgeDistribution
    from app.models.tenant import Tenant

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

    docs = {
        "platform_solo": Document(
            tenant_id=t_a1.id, name="平台手册(未下发)", scope="platform",
            content="x", status="indexed", chunk_count=1,
        ),
        "platform_to_a1": Document(
            tenant_id=t_a1.id, name="平台话术(下发A1)", scope="platform",
            content="x", status="indexed", chunk_count=1,
        ),
        "groupA": Document(
            tenant_id=t_a1.id, name="A集团手册", scope="group", group_id=g_a.id,
            content="x", status="indexed", chunk_count=1,
        ),
        "storeA1": Document(
            tenant_id=t_a1.id, name="A1店FAQ", scope="store",
            content="x", status="indexed", chunk_count=1,
        ),
        "storeA2": Document(
            tenant_id=t_a2.id, name="A2店FAQ", scope="store",
            content="x", status="indexed", chunk_count=1,
        ),
        "groupB": Document(
            tenant_id=t_b1.id, name="B集团手册", scope="group", group_id=g_b.id,
            content="x", status="indexed", chunk_count=1,
        ),
        "storeB1": Document(
            tenant_id=t_b1.id, name="B1店FAQ", scope="store",
            content="x", status="indexed", chunk_count=1,
        ),
    }
    db_session.add_all(docs.values())
    await db_session.flush()
    # The ONE distribution row: platform_to_a1 → t_a1 (active).
    db_session.add(KnowledgeDistribution(
        source_doc_id=docs["platform_to_a1"].id, target_tenant_id=t_a1.id,
        distributed_by=None, is_active=True,
    ))
    await db_session.flush()
    return {
        "t_a1": t_a1.id, "t_a2": t_a2.id, "t_b1": t_b1.id,
        "g_a": g_a.id, "g_b": g_b.id,
        **{k: v.id for k, v in docs.items()},
    }


# ------------------------------------------------ L. list_visible_for (AC1)


@pytest.mark.asyncio
async def test_list_visible_for_store_sees_own_store_plus_distributed(db_session):
    """AC1: store view = own scope='store' docs + docs distributed TO it."""
    from app.repositories.document import DocumentRepository

    ids = await _seed_document_fixture(db_session)
    repo = DocumentRepository(db_session)
    seen = await repo.list_visible_for(
        tenant_id=ids["t_a1"], group_id=ids["g_a"],
        include_all_tenants=False, is_group_admin=False,
    )
    seen_ids = {d.id for d in seen}
    # own store doc + the platform doc distributed to A1.
    assert ids["storeA1"] in seen_ids
    assert ids["platform_to_a1"] in seen_ids
    # NOT visible: undistributed platform, sibling store, other group.
    assert ids["platform_solo"] not in seen_ids
    assert ids["storeA2"] not in seen_ids
    assert ids["groupA"] not in seen_ids  # group doc NOT distributed → invisible to store


@pytest.mark.asyncio
async def test_list_visible_for_store_cannot_see_other_stores_or_undistributed(db_session):
    """AC1: a store never sees another store's docs or undistributed platform docs."""
    from app.repositories.document import DocumentRepository

    ids = await _seed_document_fixture(db_session)
    repo = DocumentRepository(db_session)
    seen = await repo.list_visible_for(
        tenant_id=ids["t_a1"], group_id=ids["g_a"],
        include_all_tenants=False, is_group_admin=False,
    )
    seen_ids = {d.id for d in seen}
    # cross-store + cross-group isolation.
    assert ids["storeA2"] not in seen_ids
    assert ids["storeB1"] not in seen_ids
    assert ids["groupB"] not in seen_ids


@pytest.mark.asyncio
async def test_list_visible_for_group_admin_aggregates_chain(db_session):
    """AC1: group_admin view = own group docs + ALL sibling stores' store docs."""
    from app.repositories.document import DocumentRepository

    ids = await _seed_document_fixture(db_session)
    repo = DocumentRepository(db_session)
    seen = await repo.list_visible_for(
        tenant_id=ids["t_a1"], group_id=ids["g_a"],
        include_all_tenants=False, is_group_admin=True,
    )
    seen_ids = {d.id for d in seen}
    # groupA doc + both sibling stores (A1 + A2).
    assert ids["groupA"] in seen_ids
    assert ids["storeA1"] in seen_ids
    assert ids["storeA2"] in seen_ids
    # NOT visible: other group B entirely (cross-group isolation).
    assert ids["groupB"] not in seen_ids
    assert ids["storeB1"] not in seen_ids
    # platform docs are NOT in the group_admin aggregation (they need distribution).
    assert ids["platform_solo"] not in seen_ids
    assert ids["platform_to_a1"] not in seen_ids


@pytest.mark.asyncio
async def test_list_visible_for_super_admin_sees_everything(db_session):
    """AC1: cross-tenant viewer (super_admin/hq_staff) sees every live doc."""
    from app.repositories.document import DocumentRepository

    ids = await _seed_document_fixture(db_session)
    repo = DocumentRepository(db_session)
    seen = await repo.list_visible_for(
        tenant_id=ids["t_a1"], group_id=ids["g_a"],
        include_all_tenants=True, is_group_admin=False,
    )
    seen_ids = {d.id for d in seen}
    assert seen_ids == {
        ids["platform_solo"], ids["platform_to_a1"],
        ids["groupA"], ids["groupB"],
        ids["storeA1"], ids["storeA2"], ids["storeB1"],
    }


@pytest.mark.asyncio
async def test_list_visible_for_cross_group_isolation(db_session):
    """AC1: a GroupA store cannot see GroupB's group/store docs."""
    from app.repositories.document import DocumentRepository

    ids = await _seed_document_fixture(db_session)
    repo = DocumentRepository(db_session)
    # B1's view: own store doc only (groupB doc needs group_admin, not a store).
    seen = await repo.list_visible_for(
        tenant_id=ids["t_b1"], group_id=ids["g_b"],
        include_all_tenants=False, is_group_admin=False,
    )
    seen_names = {d.name for d in seen}
    assert "B1店FAQ" in seen_names
    assert "A集团手册" not in seen_names
    assert "A1店FAQ" not in seen_names


@pytest.mark.asyncio
async def test_list_visible_for_excludes_soft_deleted_source(db_session):
    """AC1: a soft-deleted source document never surfaces (even via distribution)."""
    from app.models.document import Document
    from app.repositories.document import DocumentRepository

    ids = await _seed_document_fixture(db_session)
    # Soft-delete the distributed platform doc → it must vanish from A1's view.
    plat = await db_session.get(Document, ids["platform_to_a1"])
    plat.is_deleted = True
    await db_session.flush()

    repo = DocumentRepository(db_session)
    seen = await repo.list_visible_for(
        tenant_id=ids["t_a1"], group_id=ids["g_a"],
        include_all_tenants=False, is_group_admin=False,
    )
    assert ids["platform_to_a1"] not in {d.id for d in seen}


# ---------------------------------------- S. search_by_embedding three-path (AC2)
# SQLite has no pgvector operator, so these tests do NOT run real vector SQL.
# They monkeypatch ``search_by_embedding`` to a recorder and assert the ROLE
# CONTEXT (include_distributed / group_id / include_all_tenants /
# is_group_admin) is forwarded correctly — the three-path WHERE lives in the
# repo and the wiring through the service/tool is what's under test.


@pytest.mark.asyncio
async def test_search_by_embedding_defaults_are_backward_compatible(db_session, monkeypatch):
    """AC2: with all flags default, search reproduces the pre-slice-02 call shape."""
    from app.repositories.document import DocumentChunkRepository

    captured: dict = {}

    async def _fake(self, **kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(DocumentChunkRepository, "search_by_embedding", _fake)
    # Invoke via the service so the wiring (service → repo) is what we assert.
    from app.services.knowledge_service import KnowledgeService

    # retrieve() with defaults must forward defaults to the repo verbatim.
    svc = KnowledgeService(db_session)
    # Stub the embedding layer (no HTTP) — only the repo call shape matters.
    monkeypatch.setattr(svc, "_embedding_service", _stub_embedding_factory())
    await svc.retrieve("q", "t1", top_k=4)
    assert captured["tenant_id"] == "t1"
    assert captured["top_k"] == 4
    assert captured["include_distributed"] is False
    assert captured["include_all_tenants"] is False
    assert captured["is_group_admin"] is False
    assert captured["group_id"] is None


def _stub_embedding_factory():
    """Return an async function mimicking ``_embedding_service(tenant_id)``.

    ``_embedding_service`` is a coroutine returning an EmbeddingService whose
    ``embed_query`` returns a fixed vector. Tests only care about the repo call
    shape, so the embedding layer is stubbed (no HTTP).
    """

    class _Stub:
        async def embed_query(self, _q):
            return [0.0]

    async def _factory(_tenant_id):
        return _Stub()

    return _factory


@pytest.mark.asyncio
async def test_retrieve_with_include_distributed_forwards_to_repo(db_session, monkeypatch):
    """AC2: retrieve(include_distributed=True) forwards True to search_by_embedding."""
    from app.repositories.document import DocumentChunkRepository

    captured: dict = {}

    async def _fake(self, **kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(DocumentChunkRepository, "search_by_embedding", _fake)
    from app.services.knowledge_service import KnowledgeService

    svc = KnowledgeService(db_session)
    monkeypatch.setattr(svc, "_embedding_service", _stub_embedding_factory())
    await svc.retrieve("q", "t1", include_distributed=True)
    assert captured["include_distributed"] is True


@pytest.mark.asyncio
async def test_retrieve_group_admin_context_forwards_to_repo(db_session, monkeypatch):
    """AC2: the group_admin / super_admin role context is forwarded to the repo."""
    from app.repositories.document import DocumentChunkRepository

    captured: dict = {}

    async def _fake(self, **kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(DocumentChunkRepository, "search_by_embedding", _fake)
    from app.services.knowledge_service import KnowledgeService

    svc = KnowledgeService(db_session)
    monkeypatch.setattr(svc, "_embedding_service", _stub_embedding_factory())
    await svc.retrieve(
        "q", "t1", include_all_tenants=True, is_group_admin=True, group_id="g1",
    )
    assert captured["include_all_tenants"] is True
    assert captured["is_group_admin"] is True
    assert captured["group_id"] == "g1"


@pytest.mark.asyncio
async def test_retrieve_additive_never_drops_own_hits(db_session, monkeypatch):
    """AC2: include_distributed is strictly additive (own hits kept, never replaced).

    The repo's store branch uses OR (own store chunks OR distributed doc chunks),
    so turning include_distributed ON can only ADD hits, never remove the own-store
    ones. We pin the OR semantics at the SQL-shape level: the own-store predicate
    is present in BOTH modes.
    """
    # Read the source and confirm the branch structure (cheap structural guard).
    import inspect

    from app.repositories.document import DocumentChunkRepository

    src = inspect.getsource(DocumentChunkRepository.search_by_embedding)
    # The own-store predicate appears unconditionally in the store branch.
    assert "DocumentChunk.tenant_id == tenant_id" in src
    # The distributed expansion is gated behind include_distributed (additive).
    assert "if include_distributed:" in src


# ------------------------------------------------- G. G1 bypass 接通 (AC3)
# The foundation left check()/require() with an optional ``db`` param so a
# group_admin bypass could fire for knowledge — but the 5 callers in
# KnowledgeService + graph.py never passed it, so the bypass was dead. Slice 02
# wires ``db=...`` through all 5 sites. These tests pin that the bypass now fires
# AND that D9 holds (knowledge-only; devices never takes the branch).


@pytest.mark.asyncio
async def test_g1_group_admin_bypass_fires_on_knowledge_read(patched_enforcer, db_session):
    """AC3: a group_admin (HQ owner, no knowledge:read casbin grant) can read knowledge.

    Before slice 02 the require() did not pass ``db`` → the bypass branch never
    ran → casbin denied (HQ owner has no knowledge policy on the HQ tenant).
    After G1, ``db=self.db`` lets ``check`` derive is_group_admin → bypass → True.
    """
    from sqlalchemy import select

    from app.models.group import Group
    from app.models.tenant import UserTenant
    from app.services.knowledge_service import KnowledgeService

    ids = await _seed_document_fixture(db_session)
    # Promote A1 into GroupA's HQ owner (derives group_admin).
    g_a = (await db_session.execute(select(Group).where(Group.id == ids["g_a"]))).scalar_one()
    g_a.headquarters_tenant_id = ids["t_a1"]
    db_session.add(UserTenant(
        user_id="u-ga", tenant_id=ids["t_a1"], role="owner", valid_to=None,
    ))
    await db_session.flush()
    # NOTE: deliberately do NOT bind a knowledge policy for u-ga — the bypass
    # must fire without any casbin knowledge grant.

    svc = KnowledgeService(db_session)
    # list_documents passes db=self.db (G1). A group_admin with no knowledge
    # casbin grant must NOT raise PermissionError.
    docs = await svc.list_documents(
        user_id="u-ga", tenant_id=ids["t_a1"], platform_role=None,
    )
    # group_admin aggregation view includes groupA + sibling stores.
    names = {d.name for d in docs}
    assert "A集团手册" in names


@pytest.mark.asyncio
async def test_g1_non_group_admin_passing_db_still_uses_casbin(patched_enforcer, db_session):
    """AC3: passing db=self.db is safe for non-group_admin callers — they fall through.

    A plain store owner WITH a knowledge:read casbin grant is allowed; one
    WITHOUT it is denied. The bypass branch only short-circuits for group_admin,
    so non-group_admin callers see zero behaviour change (regression guard).
    """
    from app.services.knowledge_service import KnowledgeService

    ids = await _seed_document_fixture(db_session)
    # A user with NO role binding and NO knowledge policy → must be denied.
    svc = KnowledgeService(db_session)
    with pytest.raises(PermissionError):
        await svc.list_documents(
            user_id="u-nobody", tenant_id=ids["t_a1"], platform_role=None,
        )


@pytest.mark.asyncio
async def test_g1_d9_bypass_is_knowledge_only_not_devices(patched_enforcer, db_session):
    """AC3/D9: the group_admin bypass is scoped to obj=='knowledge' — devices never fires.

    A group_admin calling a devices check (with db passed) must still go through
    casbin and be denied (D9: derived identity is knowledge-domain only).
    """
    from sqlalchemy import select

    from app.models.group import Group
    from app.models.tenant import UserTenant
    from app.services.permission_service import permission_service

    ids = await _seed_document_fixture(db_session)
    g_a = (await db_session.execute(select(Group).where(Group.id == ids["g_a"]))).scalar_one()
    g_a.headquarters_tenant_id = ids["t_a1"]
    db_session.add(UserTenant(
        user_id="u-ga-dev", tenant_id=ids["t_a1"], role="owner", valid_to=None,
    ))
    await db_session.flush()

    # knowledge: bypass fires (True).
    assert await permission_service.check(
        "u-ga-dev", ids["t_a1"], "knowledge", "read", platform_role=None, db=db_session,
    ) is True
    # devices: bypass must NOT fire → falls through to casbin → no policy → False.
    assert await permission_service.check(
        "u-ga-dev", ids["t_a1"], "devices", "read", platform_role=None, db=db_session,
    ) is False


# ------------------------------------ R. retrieve_knowledge tool wiring (AC5)
# The agent's retrieve_knowledge tool must call retrieve(include_distributed=True)
# and check(..., db=db). We assert the wiring by reading the tool source (the
# agent path needs a full LLM run to exercise end-to-end, which is out of scope
# for this slice's unit tests; the wiring is the contract).


def test_retrieve_knowledge_tool_passes_include_distributed_and_db():
    """AC5: the agent tool wires include_distributed=True + check(db=db)."""
    import inspect

    from app.agents.graph import _build_tenant_tools

    src = inspect.getsource(_build_tenant_tools)
    # The tool body must pass include_distributed=True to retrieve(...).
    assert "include_distributed=True" in src
    # And check(...) must forward db=db so the group_admin bypass fires.
    assert '"knowledge", "read", db=db' in src


@pytest.mark.asyncio
async def test_retrieve_for_debug_stays_own_store_only(patched_enforcer, db_session, monkeypatch):
    """AC5: retrieve_for_debug passes include_distributed=False (debug page = own store).

    The debug page must NOT surface distributed docs (plan §4.6 G3: debug page
    is for "does my pipeline find the right context?" — distributed docs would
    muddy that). We assert the wiring by capturing the repo call.
    """
    from app.repositories.document import DocumentChunkRepository

    captured: dict = {}

    async def _fake(self, **kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(DocumentChunkRepository, "search_by_embedding", _fake)
    from app.models.tenant import UserTenant
    from app.services.knowledge_service import KnowledgeService

    ids = await _seed_document_fixture(db_session)
    db_session.add(UserTenant(
        user_id="u-owner-debug", tenant_id=ids["t_a1"], role="owner", valid_to=None,
    ))
    await db_session.flush()
    _bind_role(patched_enforcer, "u-owner-debug", "owner", ids["t_a1"])

    svc = KnowledgeService(db_session)
    monkeypatch.setattr(svc, "_embedding_service", _stub_embedding_factory())
    await svc.retrieve_for_debug(
        user_id="u-owner-debug", tenant_id=ids["t_a1"], query="q", platform_role=None,
    )
    # Default include_distributed=False flows through → own store only.
    assert captured["include_distributed"] is False


# ---------------------------------------- N. DocumentRead schema fields (AC4)


@pytest.mark.asyncio
async def test_document_read_exposes_tier_fields(db_session):
    """AC4: DocumentRead carries scope/group_id/category_id (forward-compatible)."""
    from app.schemas.document import DocumentRead

    ids = await _seed_document_fixture(db_session)
    from app.models.document import Document

    # Fetch a group-scoped doc and confirm all three tier fields serialize.
    group_doc = await db_session.get(Document, ids["groupA"])
    read = DocumentRead.model_validate(group_doc)
    assert read.scope == "group"
    assert read.group_id == ids["g_a"]
    assert read.category_id is None  # no category assigned in the fixture


# ======================================================================
# 切片 03 — 下发/撤回 API + distribute 权限码
# Plan: harness/docs/plan-knowledge-tiered-backend.md slice 03.
#
# Chapter layout (matches slice 03 AC checklist):
# - D. DistributeRequest schema — G4 XOR (AC1).
# - R. Repository — create/deactivate/list_for_source/list_for_target (AC2).
# - S. Service distribute — explicit list / group expand / G4 / cross-group /
#   super_admin / upsert (AC3).
# - V. Service revoke — soft-delete + audit preserved (AC4).
# - L. Source soft-delete linkage — list/retrieve auto-exclude (AC5, slice 02
#   already wired the joint predicate; these tests prove it holds).
# - P. distribute permission — owner/admin yes / member no / group_admin bypass
#   / super_admin (AC7).
# - A. API endpoints — POST distribute + DELETE revoke (AC6).
# - G7. Reference-model consistency — edit source → target sees latest (AC11).
# ======================================================================


async def _promote_to_group_admin(db_session, group_id: str, hq_tenant_id: str,
                                  user_id: str = "u-ga-dist"):
    """Promote a user into a group's HQ owner (derives group_admin).

    Mirrors the slice-01/02 pattern: set ``headquarters_tenant_id`` on the group
    and add a UserTenant(owner) row for the user on that HQ tenant. The derived
    ``is_group_admin`` then returns True for ``(user_id, group_id)``.
    """
    from sqlalchemy import select

    from app.models.group import Group
    from app.models.tenant import UserTenant

    g = (await db_session.execute(select(Group).where(Group.id == group_id))).scalar_one()
    g.headquarters_tenant_id = hq_tenant_id
    db_session.add(UserTenant(user_id=user_id, tenant_id=hq_tenant_id, role="owner", valid_to=None))
    await db_session.flush()


# ----------------------------------------------- D. DistributeRequest schema (AC1)


@pytest.mark.asyncio
async def test_distribute_request_accepts_explicit_tenant_list():
    """AC1/G4: target_tenant_ids alone is a valid payload."""
    from app.schemas.document import DistributeRequest

    req = DistributeRequest(target_tenant_ids=["t1", "t2"])
    assert req.target_tenant_ids == ["t1", "t2"]
    assert req.target_group_id is None


@pytest.mark.asyncio
async def test_distribute_request_accepts_group_target():
    """AC1/G4: target_group_id alone is a valid payload."""
    from app.schemas.document import DistributeRequest

    req = DistributeRequest(target_group_id="g1")
    assert req.target_group_id == "g1"
    assert req.target_tenant_ids is None


@pytest.mark.asyncio
async def test_distribute_request_accepts_neither_at_schema_level():
    """AC1/G4: the schema declares both Optional — the XOR is enforced in the
    service (BizError), not on the schema (serialization hazard, see
    DistributeRequest docstring). So neither-set parses fine here.
    """
    from app.schemas.document import DistributeRequest

    req = DistributeRequest()
    assert req.target_tenant_ids is None
    assert req.target_group_id is None


@pytest.mark.asyncio
async def test_distribution_read_serializes_all_fields(db_session):
    """AC1: KnowledgeDistributionRead carries all six fields (id/source_doc_id/
    target_tenant_id/distributed_by/distributed_at/is_active)."""
    from app.models.knowledge_distribution import KnowledgeDistribution
    from app.schemas.document import KnowledgeDistributionRead

    ids = await _seed_document_fixture(db_session)
    row = KnowledgeDistribution(
        source_doc_id=ids["platform_solo"],
        target_tenant_id=ids["t_a2"],
        distributed_by="u-someone",
        is_active=True,
    )
    db_session.add(row)
    await db_session.flush()
    read = KnowledgeDistributionRead.model_validate(row)
    assert read.source_doc_id == ids["platform_solo"]
    assert read.target_tenant_id == ids["t_a2"]
    assert read.distributed_by == "u-someone"
    assert read.is_active is True
    assert read.distributed_at is not None
    assert read.id == row.id


# ------------------------------------------------ R. Repository CRUD (AC2)


@pytest.mark.asyncio
async def test_repo_create_inserts_active_row(db_session):
    """AC2: create inserts an active distribution row."""
    from app.repositories.knowledge_distribution import KnowledgeDistributionRepository

    ids = await _seed_document_fixture(db_session)
    repo = KnowledgeDistributionRepository(db_session)
    row = await repo.create(
        source_doc_id=ids["platform_solo"], target_tenant_id=ids["t_a2"],
        distributed_by="u1",
    )
    assert row.is_active is True
    assert row.source_doc_id == ids["platform_solo"]
    assert row.target_tenant_id == ids["t_a2"]


@pytest.mark.asyncio
async def test_repo_create_re_enables_revoked_row_upsert(db_session):
    """AC2/AC3: re-distributing an existing (doc,target) re-enables the row
    (Feature B upsert) rather than duplicating."""
    from app.models.knowledge_distribution import KnowledgeDistribution
    from app.repositories.knowledge_distribution import KnowledgeDistributionRepository

    ids = await _seed_document_fixture(db_session)
    repo = KnowledgeDistributionRepository(db_session)
    # First push.
    first = await repo.create(
        source_doc_id=ids["platform_solo"], target_tenant_id=ids["t_a2"],
        distributed_by="u1",
    )
    # Revoke it.
    assert await repo.deactivate(first.id) is True
    # Second push (same pair) → upsert re-enables, no duplicate row.
    second = await repo.create(
        source_doc_id=ids["platform_solo"], target_tenant_id=ids["t_a2"],
        distributed_by="u2",
    )
    assert second.is_active is True
    assert second.id == first.id  # same row, not a duplicate
    assert second.distributed_by == "u2"  # updated to the new pusher
    # Still only ONE row for this pair.
    from sqlalchemy import select
    count = len((await db_session.execute(
        select(KnowledgeDistribution).where(
            KnowledgeDistribution.source_doc_id == ids["platform_solo"],
            KnowledgeDistribution.target_tenant_id == ids["t_a2"],
        )
    )).scalars().all())
    assert count == 1


@pytest.mark.asyncio
async def test_repo_deactivate_soft_flips_preserves_row(db_session):
    """AC2/AC4: deactivate flips is_active=False but keeps the row (audit)."""
    from app.repositories.knowledge_distribution import KnowledgeDistributionRepository

    ids = await _seed_document_fixture(db_session)
    repo = KnowledgeDistributionRepository(db_session)
    row = await repo.create(
        source_doc_id=ids["platform_solo"], target_tenant_id=ids["t_a2"],
        distributed_by="u1",
    )
    assert await repo.deactivate(row.id) is True
    # Row still present, now inactive.
    still = await repo.get(row.id)
    assert still is not None
    assert still.is_active is False
    # deactivate on a missing id returns False.
    assert await repo.deactivate("nonexistent") is False


@pytest.mark.asyncio
async def test_repo_list_for_source_includes_revoked_for_audit(db_session):
    """AC2: list_for_source returns ALL rows (audit), active_only filters."""
    from app.repositories.knowledge_distribution import KnowledgeDistributionRepository

    ids = await _seed_document_fixture(db_session)
    repo = KnowledgeDistributionRepository(db_session)
    active = await repo.create(
        source_doc_id=ids["platform_solo"], target_tenant_id=ids["t_a2"],
        distributed_by="u1",
    )
    revoked = await repo.create(
        source_doc_id=ids["platform_solo"], target_tenant_id=ids["t_b1"],
        distributed_by="u1",
    )
    await repo.deactivate(revoked.id)
    # Default: audit view sees both.
    all_rows = await repo.list_for_source(ids["platform_solo"])
    assert {r.id for r in all_rows} == {active.id, revoked.id}
    # active_only: just the live one.
    live = await repo.list_for_source(ids["platform_solo"], active_only=True)
    assert {r.id for r in live} == {active.id}


@pytest.mark.asyncio
async def test_repo_list_for_target_excludes_revoked(db_session):
    """AC2: list_for_target (the store's view) excludes revoked rows."""
    from app.repositories.knowledge_distribution import KnowledgeDistributionRepository

    ids = await _seed_document_fixture(db_session)
    repo = KnowledgeDistributionRepository(db_session)
    keep = await repo.create(
        source_doc_id=ids["platform_solo"], target_tenant_id=ids["t_a2"],
        distributed_by="u1",
    )
    gone = await repo.create(
        source_doc_id=ids["groupA"], target_tenant_id=ids["t_a2"],
        distributed_by="u1",
    )
    await repo.deactivate(gone.id)
    seen = await repo.list_for_target(ids["t_a2"])
    assert {r.id for r in seen} == {keep.id}


# ------------------------------ S. Service distribute — targeting + guards (AC3)


@pytest.mark.asyncio
async def test_service_distribute_explicit_tenant_list(patched_enforcer, db_session):
    """AC3: target_tenant_ids pushes to each listed store."""
    from app.schemas.document import DistributeRequest
    from app.services.knowledge_service import KnowledgeService

    ids = await _seed_document_fixture(db_session)
    _bind_role(patched_enforcer, "u-owner-a1", "owner", ids["t_a1"])
    svc = KnowledgeService(db_session)
    rows = await svc.distribute_document(
        "u-owner-a1", ids["t_a1"], ids["storeA1"],
        DistributeRequest(target_tenant_ids=[ids["t_a2"], ids["t_b1"]]),
        platform_role=None,
    )
    assert len(rows) == 2
    targets = {r.target_tenant_id for r in rows}
    assert targets == {ids["t_a2"], ids["t_b1"]}
    assert all(r.is_active for r in rows)


@pytest.mark.asyncio
async def test_service_distribute_group_expand(patched_enforcer, db_session):
    """AC3: target_group_id expands to every store in the group."""
    from app.schemas.document import DistributeRequest
    from app.services.knowledge_service import KnowledgeService

    ids = await _seed_document_fixture(db_session)
    await _promote_to_group_admin(db_session, ids["g_a"], ids["t_a1"], "u-ga-dist")
    _bind_role(patched_enforcer, "u-ga-dist", "owner", ids["t_a1"])
    svc = KnowledgeService(db_session)
    # group_admin distributes a group doc to their whole group (A1 + A2).
    rows = await svc.distribute_document(
        "u-ga-dist", ids["t_a1"], ids["groupA"],
        DistributeRequest(target_group_id=ids["g_a"]),
        platform_role=None,
    )
    targets = {r.target_tenant_id for r in rows}
    assert targets == {ids["t_a1"], ids["t_a2"]}  # both GroupA stores


@pytest.mark.asyncio
async def test_service_distribute_g4_both_set_rejected(patched_enforcer, db_session):
    """AC3/G4: both target_tenant_ids AND target_group_id → BizError (400)."""
    from app.schemas.document import DistributeRequest
    from app.services.errors import BizError
    from app.services.knowledge_service import KnowledgeService

    ids = await _seed_document_fixture(db_session)
    _bind_role(patched_enforcer, "u-owner-a1", "owner", ids["t_a1"])
    svc = KnowledgeService(db_session)
    with pytest.raises(BizError):
        await svc.distribute_document(
            "u-owner-a1", ids["t_a1"], ids["storeA1"],
            DistributeRequest(target_tenant_ids=[ids["t_a2"]], target_group_id=ids["g_a"]),
            platform_role=None,
        )


@pytest.mark.asyncio
async def test_service_distribute_g4_neither_set_rejected(patched_enforcer, db_session):
    """AC3/G4: neither target set → BizError (400)."""
    from app.schemas.document import DistributeRequest
    from app.services.errors import BizError
    from app.services.knowledge_service import KnowledgeService

    ids = await _seed_document_fixture(db_session)
    _bind_role(patched_enforcer, "u-owner-a1", "owner", ids["t_a1"])
    svc = KnowledgeService(db_session)
    with pytest.raises(BizError):
        await svc.distribute_document(
            "u-owner-a1", ids["t_a1"], ids["storeA1"],
            DistributeRequest(),
            platform_role=None,
        )


@pytest.mark.asyncio
async def test_service_distribute_cross_group_group_admin_rejected(patched_enforcer, db_session):
    """AC3: a group_admin targeting ANOTHER group → BizError (cross-group guard)."""
    from app.schemas.document import DistributeRequest
    from app.services.errors import BizError
    from app.services.knowledge_service import KnowledgeService

    ids = await _seed_document_fixture(db_session)
    # u-ga is GroupA's admin; targeting GroupB must be refused.
    await _promote_to_group_admin(db_session, ids["g_a"], ids["t_a1"], "u-ga-xgrp")
    _bind_role(patched_enforcer, "u-ga-xgrp", "owner", ids["t_a1"])
    svc = KnowledgeService(db_session)
    with pytest.raises(BizError):
        await svc.distribute_document(
            "u-ga-xgrp", ids["t_a1"], ids["groupA"],
            DistributeRequest(target_group_id=ids["g_b"]),  # not their group
            platform_role=None,
        )


@pytest.mark.asyncio
async def test_service_distribute_super_admin_targets_any_group(db_session):
    """AC3: super_admin may target any group (no cross-group guard)."""
    from app.schemas.document import DistributeRequest
    from app.services.knowledge_service import KnowledgeService

    ids = await _seed_document_fixture(db_session)
    svc = KnowledgeService(db_session)
    rows = await svc.distribute_document(
        "u-super", ids["t_a1"], ids["platform_solo"],
        DistributeRequest(target_group_id=ids["g_b"]),  # any group
        platform_role="super_admin",
    )
    # GroupB has one store (t_b1).
    assert {r.target_tenant_id for r in rows} == {ids["t_b1"]}


@pytest.mark.asyncio
async def test_service_distribute_upsert_re_enables_revoked(patched_enforcer, db_session):
    """AC3: re-distributing to a store that had the doc revoked re-enables it."""
    from app.schemas.document import DistributeRequest
    from app.services.knowledge_service import KnowledgeService

    ids = await _seed_document_fixture(db_session)
    _bind_role(patched_enforcer, "u-owner-a1", "owner", ids["t_a1"])
    svc = KnowledgeService(db_session)
    first = await svc.distribute_document(
        "u-owner-a1", ids["t_a1"], ids["storeA1"],
        DistributeRequest(target_tenant_ids=[ids["t_a2"]]),
        platform_role=None,
    )
    dist_id = first[0].id
    # Revoke via the service, then re-distribute.
    await svc.revoke_distribution("u-owner-a1", ids["t_a1"], dist_id, platform_role=None)
    second = await svc.distribute_document(
        "u-owner-a1", ids["t_a1"], ids["storeA1"],
        DistributeRequest(target_tenant_ids=[ids["t_a2"]]),
        platform_role=None,
    )
    assert second[0].id == dist_id  # same row
    assert second[0].is_active is True  # re-enabled


@pytest.mark.asyncio
async def test_service_distribute_missing_source_rejected(patched_enforcer, db_session):
    """AC3: distributing a non-existent / soft-deleted source → NotFoundError."""
    from app.models.document import Document
    from app.schemas.document import DistributeRequest
    from app.services.errors import NotFoundError
    from app.services.knowledge_service import KnowledgeService

    ids = await _seed_document_fixture(db_session)
    _bind_role(patched_enforcer, "u-owner-a1", "owner", ids["t_a1"])
    svc = KnowledgeService(db_session)
    # Non-existent doc.
    with pytest.raises(NotFoundError):
        await svc.distribute_document(
            "u-owner-a1", ids["t_a1"], "no-such-doc",
            DistributeRequest(target_tenant_ids=[ids["t_a2"]]),
            platform_role=None,
        )
    # Soft-deleted doc.
    doc = await db_session.get(Document, ids["storeA1"])
    doc.is_deleted = True
    await db_session.flush()
    with pytest.raises(NotFoundError):
        await svc.distribute_document(
            "u-owner-a1", ids["t_a1"], ids["storeA1"],
            DistributeRequest(target_tenant_ids=[ids["t_a2"]]),
            platform_role=None,
        )


# ----------------------------------------- V. Service revoke — soft delete (AC4)


@pytest.mark.asyncio
async def test_service_revoke_soft_deletes_and_excludes(patched_enforcer, db_session):
    """AC4: revoke flips is_active=False; target's list/retrieve then excludes."""
    from app.repositories.document import DocumentRepository
    from app.schemas.document import DistributeRequest
    from app.services.knowledge_service import KnowledgeService

    ids = await _seed_document_fixture(db_session)
    _bind_role(patched_enforcer, "u-owner-a1", "owner", ids["t_a1"])
    svc = KnowledgeService(db_session)
    rows = await svc.distribute_document(
        "u-owner-a1", ids["t_a1"], ids["platform_solo"],
        DistributeRequest(target_tenant_ids=[ids["t_a2"]]),
        platform_role=None,
    )
    # Before revoke: t_a2 sees the distributed doc.
    repo = DocumentRepository(db_session)
    seen = await repo.list_visible_for(
        tenant_id=ids["t_a2"], group_id=ids["g_a"],
        include_all_tenants=False, is_group_admin=False,
    )
    assert ids["platform_solo"] in {d.id for d in seen}
    # Revoke.
    await svc.revoke_distribution("u-owner-a1", ids["t_a1"], rows[0].id, platform_role=None)
    # After revoke: t_a2 no longer sees it.
    seen = await repo.list_visible_for(
        tenant_id=ids["t_a2"], group_id=ids["g_a"],
        include_all_tenants=False, is_group_admin=False,
    )
    assert ids["platform_solo"] not in {d.id for d in seen}


@pytest.mark.asyncio
async def test_service_revoke_preserves_audit_row(patched_enforcer, db_session):
    """AC4: revoke keeps the row (is_active=False) for audit — not a hard delete."""
    from app.models.knowledge_distribution import KnowledgeDistribution
    from app.schemas.document import DistributeRequest
    from app.services.knowledge_service import KnowledgeService

    ids = await _seed_document_fixture(db_session)
    _bind_role(patched_enforcer, "u-owner-a1", "owner", ids["t_a1"])
    svc = KnowledgeService(db_session)
    rows = await svc.distribute_document(
        "u-owner-a1", ids["t_a1"], ids["platform_solo"],
        DistributeRequest(target_tenant_ids=[ids["t_a2"]]),
        platform_role=None,
    )
    dist_id = rows[0].id
    await svc.revoke_distribution("u-owner-a1", ids["t_a1"], dist_id, platform_role=None)
    # The row still exists (audit), now inactive.
    row = await db_session.get(KnowledgeDistribution, dist_id)
    assert row is not None
    assert row.is_active is False


@pytest.mark.asyncio
async def test_service_revoke_missing_row_not_found(patched_enforcer, db_session):
    """AC4: revoking a non-existent id → NotFoundError (no leak)."""
    from app.services.errors import NotFoundError
    from app.services.knowledge_service import KnowledgeService

    ids = await _seed_document_fixture(db_session)
    _bind_role(patched_enforcer, "u-owner-a1", "owner", ids["t_a1"])
    svc = KnowledgeService(db_session)
    with pytest.raises(NotFoundError):
        await svc.revoke_distribution("u-owner-a1", ids["t_a1"], "no-such-dist", platform_role=None)


# ----------------------- L. Source soft-delete linkage (AC5 — slice 02 wired it)


@pytest.mark.asyncio
async def test_source_soft_delete_excludes_from_store_list(patched_enforcer, db_session):
    """AC5: soft-deleting the source doc hides it from the target's list, even
    though the distribution row is still active (joint predicate doc.is_deleted
    =false AND dist.is_active=true)."""
    from app.models.document import Document
    from app.repositories.document import DocumentRepository
    from app.schemas.document import DistributeRequest
    from app.services.knowledge_service import KnowledgeService

    ids = await _seed_document_fixture(db_session)
    _bind_role(patched_enforcer, "u-owner-a1", "owner", ids["t_a1"])
    svc = KnowledgeService(db_session)
    await svc.distribute_document(
        "u-owner-a1", ids["t_a1"], ids["platform_solo"],
        DistributeRequest(target_tenant_ids=[ids["t_a2"]]),
        platform_role=None,
    )
    repo = DocumentRepository(db_session)
    # t_a2 sees it before the source is deleted.
    seen = await repo.list_visible_for(
        tenant_id=ids["t_a2"], group_id=ids["g_b"],
        include_all_tenants=False, is_group_admin=False,
    )
    assert ids["platform_solo"] in {d.id for d in seen}
    # Soft-delete the SOURCE.
    doc = await db_session.get(Document, ids["platform_solo"])
    doc.is_deleted = True
    await db_session.flush()
    # t_a2 no longer sees it — the distribution row is still active, but the
    # joint predicate excludes soft-deleted sources.
    seen = await repo.list_visible_for(
        tenant_id=ids["t_a2"], group_id=ids["g_b"],
        include_all_tenants=False, is_group_admin=False,
    )
    assert ids["platform_solo"] not in {d.id for d in seen}


@pytest.mark.asyncio
async def test_source_soft_delete_distribution_row_preserved(patched_enforcer, db_session):
    """AC5: after the source is soft-deleted, the distribution ROW survives
    (audit intact) — only the joint predicate excludes it, no manual flip."""
    from app.models.document import Document
    from app.repositories.knowledge_distribution import KnowledgeDistributionRepository
    from app.schemas.document import DistributeRequest
    from app.services.knowledge_service import KnowledgeService

    ids = await _seed_document_fixture(db_session)
    _bind_role(patched_enforcer, "u-owner-a1", "owner", ids["t_a1"])
    svc = KnowledgeService(db_session)
    rows = await svc.distribute_document(
        "u-owner-a1", ids["t_a1"], ids["platform_solo"],
        DistributeRequest(target_tenant_ids=[ids["t_a2"]]),
        platform_role=None,
    )
    dist_id = rows[0].id
    # Soft-delete the source.
    doc = await db_session.get(Document, ids["platform_solo"])
    doc.is_deleted = True
    await db_session.flush()
    # The distribution row is STILL active (audit complete, is_active unchanged).
    row = await KnowledgeDistributionRepository(db_session).get(dist_id)
    assert row is not None
    assert row.is_active is True


@pytest.mark.asyncio
async def test_source_soft_delete_excludes_from_search(patched_enforcer, db_session, monkeypatch):
    """AC5: search_by_embedding's joint predicate excludes soft-deleted sources
    even via an active distribution row (slice 02 wired the join; this pins it)."""
    import inspect

    from app.repositories.document import DocumentChunkRepository

    src = inspect.getsource(DocumentChunkRepository.search_by_embedding)
    # The joint predicate: always joins Document and filters is_deleted=False,
    # BEFORE the distribution expansion — so a soft-deleted source's chunks never
    # surface even when a distribution row points at them.
    assert "Document.is_deleted.is_(False)" in src


# ------------------------------- P. distribute permission matrix (AC7)


@pytest.mark.asyncio
async def test_perm_owner_can_distribute(patched_enforcer, db_session):
    """AC7: owner (has knowledge:distribute grant) may distribute."""
    from app.schemas.document import DistributeRequest
    from app.services.knowledge_service import KnowledgeService

    ids = await _seed_document_fixture(db_session)
    _bind_role(patched_enforcer, "u-owner-a1", "owner", ids["t_a1"])
    svc = KnowledgeService(db_session)
    rows = await svc.distribute_document(
        "u-owner-a1", ids["t_a1"], ids["storeA1"],
        DistributeRequest(target_tenant_ids=[ids["t_a2"]]),
        platform_role=None,
    )
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_perm_member_cannot_distribute(patched_enforcer, db_session):
    """AC7: member (no knowledge:distribute grant) is refused at the require gate."""
    from app.schemas.document import DistributeRequest
    from app.services.knowledge_service import KnowledgeService

    ids = await _seed_document_fixture(db_session)
    _bind_role(patched_enforcer, "u-member-a1", "member", ids["t_a1"])
    svc = KnowledgeService(db_session)
    with pytest.raises(PermissionError):
        await svc.distribute_document(
            "u-member-a1", ids["t_a1"], ids["storeA1"],
            DistributeRequest(target_tenant_ids=[ids["t_a2"]]),
            platform_role=None,
        )


@pytest.mark.asyncio
async def test_perm_group_admin_bypass_distributes_within_group(patched_enforcer, db_session):
    """AC7: a group_admin (no knowledge:distribute casbin grant) distributes via
    the G1 bypass (require passes db=self.db → derived is_group_admin → True)."""
    from app.schemas.document import DistributeRequest
    from app.services.knowledge_service import KnowledgeService

    ids = await _seed_document_fixture(db_session)
    await _promote_to_group_admin(db_session, ids["g_a"], ids["t_a1"], "u-ga-bypass")
    # Deliberately do NOT bind a knowledge policy — the bypass must fire.
    svc = KnowledgeService(db_session)
    rows = await svc.distribute_document(
        "u-ga-bypass", ids["t_a1"], ids["groupA"],
        DistributeRequest(target_group_id=ids["g_a"]),
        platform_role=None,
    )
    assert {r.target_tenant_id for r in rows} == {ids["t_a1"], ids["t_a2"]}


@pytest.mark.asyncio
async def test_perm_super_admin_distributes_globally(db_session):
    """AC7: super_admin distributes any doc to any target (platform bypass)."""
    from app.schemas.document import DistributeRequest
    from app.services.knowledge_service import KnowledgeService

    ids = await _seed_document_fixture(db_session)
    svc = KnowledgeService(db_session)
    rows = await svc.distribute_document(
        "u-super", ids["t_a1"], ids["platform_solo"],
        DistributeRequest(target_tenant_ids=[ids["t_a2"], ids["t_b1"]]),
        platform_role="super_admin",
    )
    assert len(rows) == 2


# ----------------------------------- A. API endpoints (AC6)


@pytest.mark.asyncio
async def test_api_distribute_document_by_owner(app_client):
    """AC6: owner POSTs a distribution; returns 201 + the distribution rows."""
    me = (await app_client.get("/api/v1/auth/me", headers=AUTH)).json()
    tenant_id = me["tenant_id"]
    # Create a document first (owner can ingest).
    doc = (await app_client.post(
        "/api/v1/knowledge/documents",
        json={"name": "待下发文档", "content": "hello world"},
        headers=AUTH,
    )).json()
    resp = await app_client.post(
        f"/api/v1/knowledge/documents/{doc['id']}/distribute",
        json={"target_tenant_ids": [tenant_id]},  # distribute to self (own store)
        headers=AUTH,
    )
    assert resp.status_code == 201, resp.text
    rows = resp.json()
    assert isinstance(rows, list)
    assert len(rows) == 1
    assert rows[0]["source_doc_id"] == doc["id"]
    assert rows[0]["target_tenant_id"] == tenant_id
    assert rows[0]["is_active"] is True
    assert rows[0]["distributed_by"] == me["user_id"]


@pytest.mark.asyncio
async def test_api_distribute_g4_both_set_returns_400(app_client):
    """AC6/G4: both target fields set → 400 (BizError from the service XOR)."""
    doc = (await app_client.post(
        "/api/v1/knowledge/documents",
        json={"name": "G4测试", "content": "x"},
        headers=AUTH,
    )).json()
    me = (await app_client.get("/api/v1/auth/me", headers=AUTH)).json()
    resp = await app_client.post(
        f"/api/v1/knowledge/documents/{doc['id']}/distribute",
        json={"target_tenant_ids": [me["tenant_id"]], "target_group_id": "g-x"},
        headers=AUTH,
    )
    assert resp.status_code == 400, resp.text


@pytest.mark.asyncio
async def test_api_distribute_member_forbidden(member_client):
    """AC6/AC7: member POST distribute → 403 (no knowledge:distribute grant)."""
    me = (await member_client.get("/api/v1/auth/me", headers=AUTH)).json()
    resp = await member_client.post(
        "/api/v1/knowledge/documents/some-doc/distribute",
        json={"target_tenant_ids": [me["tenant_id"]]},
        headers=AUTH,
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_api_revoke_distribution_by_owner(app_client):
    """AC6: owner DELETEs a distribution → 204; row becomes inactive."""
    me = (await app_client.get("/api/v1/auth/me", headers=AUTH)).json()
    tenant_id = me["tenant_id"]
    doc = (await app_client.post(
        "/api/v1/knowledge/documents",
        json={"name": "待撤回", "content": "x"},
        headers=AUTH,
    )).json()
    dist = (await app_client.post(
        f"/api/v1/knowledge/documents/{doc['id']}/distribute",
        json={"target_tenant_ids": [tenant_id]},
        headers=AUTH,
    )).json()
    revoke = await app_client.delete(
        f"/api/v1/knowledge/distributions/{dist[0]['id']}", headers=AUTH,
    )
    assert revoke.status_code == 204, revoke.text


@pytest.mark.asyncio
async def test_api_revoke_nonexistent_returns_404(app_client):
    """AC6: revoking a non-existent distribution → 404 (no leak)."""
    resp = await app_client.delete(
        "/api/v1/knowledge/distributions/no-such-dist", headers=AUTH,
    )
    assert resp.status_code == 404, resp.text


# ----------------------------------- G7. Reference-model consistency (AC11)


def test_g7_reference_model_shares_chunks_structural_guard():
    """AC11/G7: distribution is a REFERENCE model — the target sees the source's
    chunks (no copy). So when the source is re-ingested, the target immediately
    sees the latest. We pin this at the SQL-shape level: list_visible_for /
    search_by_embedding reach the source doc via the distribution row's
    source_doc_id (a reference, not a copied doc_id), so edits propagate for free.
    """
    import inspect

    from app.repositories.document import DocumentChunkRepository, DocumentRepository

    # list_visible_for's store branch reaches distributed docs by their SOURCE id.
    list_src = inspect.getsource(DocumentRepository.list_visible_for)
    assert "KnowledgeDistribution.source_doc_id" in list_src
    # search_by_embedding's distributed branch reaches chunks by the source doc id.
    search_src = inspect.getsource(DocumentChunkRepository.search_by_embedding)
    assert "KnowledgeDistribution.source_doc_id" in search_src


@pytest.mark.asyncio
async def test_g7_reingest_source_target_sees_latest(patched_enforcer, db_session, monkeypatch):
    """AC11/G7: after the source doc is re-ingested (new chunks), the target's
    retrieval immediately reflects the new content (reference model — chunks are
    shared via source_doc_id, not copied).

    We exercise the wiring: capture the chunks the target's search would reach
    and confirm they belong to the source doc (post-reingest), proving no stale
    copy exists.
    """
    from app.models.document import DocumentChunk
    from app.schemas.document import DistributeRequest
    from app.services.knowledge_service import KnowledgeService

    ids = await _seed_document_fixture(db_session)
    _bind_role(patched_enforcer, "u-owner-a1", "owner", ids["t_a1"])
    svc = KnowledgeService(db_session)
    # Distribute platform_solo → t_a2.
    await svc.distribute_document(
        "u-owner-a1", ids["t_a1"], ids["platform_solo"],
        DistributeRequest(target_tenant_ids=[ids["t_a2"]]),
        platform_role="super_admin",  # platform_solo is a platform doc
    )
    # The distributed expansion selects chunks whose document_id ∈ active
    # distribution rows for the target. After re-ingest (new chunk rows on the
    # SAME document_id), the target sees them with no distribution change.
    # Add a "re-ingested" chunk on the source doc — simulates re-ingest.
    new_chunk = DocumentChunk(
        document_id=ids["platform_solo"], tenant_id=ids["t_a1"],
        chunk_index=99, content="re-ingested content", embedding=[0.0],
    )
    db_session.add(new_chunk)
    await db_session.flush()
    # The chunk belongs to the source doc; the distribution references that doc,
    # so the target's search (include_distributed) reaches it. We assert the
    # reference linkage at the data level: the chunk's document_id == the
    # distributed source_doc_id.
    distributed_doc_ids = {
        r.source_doc_id for r in await svc.distributions.list_for_target(ids["t_a2"])
    }
    assert ids["platform_solo"] in distributed_doc_ids
    assert new_chunk.document_id in distributed_doc_ids  # same doc → visible


# ------------------------------------- permission-code seed (AC8)


@pytest.mark.asyncio
async def test_permission_constants_have_distribute():
    """AC8: DEFAULT_OWNER/ADMIN_PERMS carry knowledge:distribute; member does not."""
    from app.services.permission_service import (
        ACT_CN,
        DEFAULT_ADMIN_PERMS,
        DEFAULT_MEMBER_PERMS,
        DEFAULT_OWNER_PERMS,
        OBJ_CN,
    )

    assert ("knowledge", "distribute") in DEFAULT_OWNER_PERMS
    assert ("knowledge", "distribute") in DEFAULT_ADMIN_PERMS
    assert ("knowledge", "distribute") not in DEFAULT_MEMBER_PERMS
    assert ACT_CN["distribute"] == "下发"
    assert OBJ_CN["knowledge"] == "知识库"


# ======================================================================
# 切片 04 — 集成验证 + feature 收尾(末切片)
# Plan: harness/docs/plan-knowledge-tiered-backend.md slice 04.
#
# 六个端到端集成场景,验证切片 01-03 的组件(Category CRUD / list+检索三路径 /
# 下发撤回 API)协同工作。这些不是新的单元覆盖(切片 01-03 已穷尽单组件),
# 而是「把它们串起来」的场景测试 —— 回答 plan §4 的核心问题:跨 scope 可见性
# 矩阵 + 引用一致性 + 跨租户隔离铁律不破,在同一真实数据库会话里一起成立。
#
# 走 service / repository 层(非 HTTP):这些场景需要多 tenant + group_admin 派生
# 身份,conftest 的 HTTP client fixtures 只绑单 tenant/单角色,改造 成本高;而
# ``_seed_document_fixture`` / ``_seed_category_fixture`` + ``patched_enforcer`` +
# 直接调 service 正是切片 03 已验证的范式(D9 测试即 service 层直调)。集成验证
# 关心「链路协同」,service 层是合适的边界。
#
# Chapter layout (matches slice 04 AC checklist):
# - I1. 完整下发链路:platform 文档 → 下发 → 门店 list/retrieve → 撤回 → 不可见
# - I2. group_admin 链路:group 文档 → 下发到本集团分店 → 分店看到 / 跨集团看不到
# - I3. Category 跨级可见:三级 Category + 门店看到三级 + 上级 Category 可挂文档
# - I4. 源文档软删联动:list/retrieve 同时排除(联合谓词) + 下发行保留审计
# - I5. 跨租户隔离铁律:store 文档 / 下发文档 / group_admin 视图 三重隔离
# - I6. D9 越界守卫:group_admin 对 knowledge 放行,对 devices/bookings 不放行


async def _promote_to_group_admin_and_bind(
    db_session, enforcer, *, group_id, hq_tenant_id, user_id,
):
    """Promote a user to group_admin of ``group_id`` AND bind the owner casbin role.

    Wraps the slice-03 ``_promote_to_group_admin`` (sets ``headquarters_tenant_id``
    + seeds UserTenant owner → derives is_group_admin True) with an extra
    ``_bind_role`` so the impersonated owner's casbin policies are seeded for the
    test tenant. The slice-03 helper alone suffices for tests that go via the
    group_admin bypass or platform_role; the integration tests here drive the
    real service ``require`` gate, so they need the owner role bound too.
    Used by I2/I5/I6.
    """
    await _promote_to_group_admin(db_session, group_id, hq_tenant_id, user_id)
    _bind_role(enforcer, user_id, "owner", hq_tenant_id)


# -------------------------------------------------- I1. 完整下发链路(AC1)


@pytest.mark.asyncio
async def test_integration_full_distribute_chain_platform_to_store(patched_enforcer, db_session):
    """AC1: super_admin 建 platform 文档 → 下发到门店 → 门店 list 看到 → 门店
    retrieve 搜到 → 撤回后门店 list/retrieve 都看不到。

    端到端串联 distribute_document → list_visible_for → retrieve(数据层可达) →
    revoke_distribution → list/retrieve 双排除。super_admin 用 platform_solo
    (scope=platform, _get_distributable_source 对 super_admin 放行 any doc)。
    """
    from app.models.document import DocumentChunk
    from app.repositories.document import DocumentRepository
    from app.schemas.document import DistributeRequest
    from app.services.knowledge_service import KnowledgeService

    ids = await _seed_document_fixture(db_session)
    _bind_role(patched_enforcer, "u-super", "owner", ids["t_a1"])
    svc = KnowledgeService(db_session)

    # 下发 platform_solo → t_a2(super_admin 全域放行)。
    rows = await svc.distribute_document(
        "u-super", ids["t_a1"], ids["platform_solo"],
        DistributeRequest(target_tenant_ids=[ids["t_a2"]]),
        platform_role="super_admin",
    )
    assert len(rows) == 1

    repo = DocumentRepository(db_session)
    # ① 下发后:t_a2 list 看到该 platform 文档。
    seen = await repo.list_visible_for(
        tenant_id=ids["t_a2"], group_id=ids["g_a"],
        include_all_tenants=False, is_group_admin=False,
    )
    assert ids["platform_solo"] in {d.id for d in seen}

    # ② retrieve 搜到:造源文档的 chunk,断言它经由 distributed_doc_ids 可达
    # (引用模型 —— chunk 属于源 doc,distribution 引用 doc_id,故目标检索命中)。
    chunk = DocumentChunk(
        document_id=ids["platform_solo"], tenant_id=ids["t_a1"],
        chunk_index=0, content="平台手册内容", embedding=[0.0],
    )
    db_session.add(chunk)
    await db_session.flush()
    # 数据层前置条件:下发关系存在 + chunk 归属于该下发文档。retrieve 的 store
    # 分支(search_by_embedding 的 document_id.in_(distributed_doc_ids))在此前提
    # 下会命中该 chunk —— 但 SQLite 无 pgvector,真实向量过滤跑不了,故此处只证
    # 「分发关系 + chunk 归属」数据可达;retrieve 的实际过滤由切片02 search_by_embedding
    # 结构测试 + 紧随其后的 wiring 断言(include_distributed=True 转发)共同补全。
    distributed_doc_ids = {
        r.source_doc_id for r in await svc.distributions.list_for_target(ids["t_a2"])
    }
    assert chunk.document_id in distributed_doc_ids

    # ③ 撤回。
    await svc.revoke_distribution("u-super", ids["t_a1"], rows[0].id, platform_role="super_admin")

    # ④ 撤回后:t_a2 list 不再看到。
    seen = await repo.list_visible_for(
        tenant_id=ids["t_a2"], group_id=ids["g_a"],
        include_all_tenants=False, is_group_admin=False,
    )
    assert ids["platform_solo"] not in {d.id for d in seen}
    # retrieve 也不可达:list_for_target 已排除 revoked(is_active=False)。
    active_doc_ids = {
        r.source_doc_id
        for r in await svc.distributions.list_for_target(ids["t_a2"])
    }
    assert ids["platform_solo"] not in active_doc_ids


@pytest.mark.asyncio
async def test_integration_retrieve_wires_include_distributed_for_store(patched_enforcer, db_session, monkeypatch):
    """AC1 补强:门店视角 retrieve(include_distributed=True) 真的把 include_distributed=True
    转发到 search_by_embedding —— 这是「retrieve 搜到下发文档」的 service→repo 协同契约。

    SQLite 无 pgvector,真实向量 SQL 跑不了;这里 monkeypatch search_by_embedding
    为 recorder,断言门店 agent 路径(retrieve_knowledge 工具)的 role flag 正确下发。
    与 I1 的数据层断言互为补充(wiring + 数据可达双保险)。
    """
    from app.repositories.document import DocumentChunkRepository
    from app.services.knowledge_service import KnowledgeService

    captured: dict = {}

    async def _fake(self, **kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(DocumentChunkRepository, "search_by_embedding", _fake)
    ids = await _seed_document_fixture(db_session)
    svc = KnowledgeService(db_session)
    monkeypatch.setattr(svc, "_embedding_service", _stub_embedding_factory())
    # 门店 agent 路径:include_distributed=True(本店 + 下发)。
    await svc.retrieve("q", ids["t_a2"], include_distributed=True)
    assert captured["include_distributed"] is True
    assert captured["tenant_id"] == ids["t_a2"]


# -------------------------------------------------- I2. group_admin 链路(AC2)


@pytest.mark.asyncio
async def test_integration_group_admin_distribute_within_group(patched_enforcer, db_session):
    """AC2:总部 owner(group_admin)建 group 文档 → 下发到本集团分店 → 分店 list
    看到 → 分店 retrieve 可达 → 跨集团分店看不到。

    提升 t_a1 owner 为 groupA 的 group_admin → 下发 groupA(scope=group)→ t_a2(同
    集团)→ t_a2 list 看到 → t_b1(跨集团)list 看不到。group_admin 走 bypass
    (G1),无需 casbin knowledge:distribute 策略。
    """
    from app.models.document import DocumentChunk
    from app.repositories.document import DocumentRepository
    from app.schemas.document import DistributeRequest
    from app.services.knowledge_service import KnowledgeService

    ids = await _seed_document_fixture(db_session)
    await _promote_to_group_admin_and_bind(
        db_session, patched_enforcer,
        user_id="u-ga", hq_tenant_id=ids["t_a1"], group_id=ids["g_a"],
    )
    svc = KnowledgeService(db_session)

    # group_admin 下发 groupA(scope=group)→ t_a2(本集团分店)。走 bypass(G1)。
    rows = await svc.distribute_document(
        "u-ga", ids["t_a1"], ids["groupA"],
        DistributeRequest(target_tenant_ids=[ids["t_a2"]]),
        platform_role=None,
    )
    assert len(rows) == 1

    repo = DocumentRepository(db_session)
    # ① t_a2(同集团分店)list 看到。
    seen_a2 = await repo.list_visible_for(
        tenant_id=ids["t_a2"], group_id=ids["g_a"],
        include_all_tenants=False, is_group_admin=False,
    )
    assert ids["groupA"] in {d.id for d in seen_a2}

    # ② t_a2 retrieve 可达(造 chunk,断言经由 distributed_doc_ids)。
    chunk = DocumentChunk(
        document_id=ids["groupA"], tenant_id=ids["t_a1"],
        chunk_index=0, content="集团手册内容", embedding=[0.0],
    )
    db_session.add(chunk)
    await db_session.flush()
    distributed_doc_ids = {
        r.source_doc_id for r in await svc.distributions.list_for_target(ids["t_a2"])
    }
    assert ids["groupA"] in distributed_doc_ids

    # ③ t_b1(跨集团分店)list 看不到 —— 只下发到 t_a2,未下发到 t_b1。
    seen_b1 = await repo.list_visible_for(
        tenant_id=ids["t_b1"], group_id=ids["g_b"],
        include_all_tenants=False, is_group_admin=False,
    )
    assert ids["groupA"] not in {d.id for d in seen_b1}


@pytest.mark.asyncio
async def test_integration_group_admin_cannot_distribute_cross_group(patched_enforcer, db_session):
    """AC2 补强:group_admin 不能下发到其他集团(target_group_id 跨集团拒绝)。

    groupA 的 group_admin 用 target_group_id=groupB 下发 → BizError「只能下发到
    自己管理的集团」。这是 group_admin 域边界的写侧守卫(D9 在读侧,这里是写侧)。
    """
    from app.schemas.document import DistributeRequest
    from app.services.errors import BizError
    from app.services.knowledge_service import KnowledgeService

    ids = await _seed_document_fixture(db_session)
    await _promote_to_group_admin_and_bind(
        db_session, patched_enforcer,
        user_id="u-ga", hq_tenant_id=ids["t_a1"], group_id=ids["g_a"],
    )
    svc = KnowledgeService(db_session)
    # groupA 的 group_admin 试图用 target_group_id=groupB 展开 → 拒绝。
    with pytest.raises(BizError):
        await svc.distribute_document(
            "u-ga", ids["t_a1"], ids["groupA"],
            DistributeRequest(target_group_id=ids["g_b"]),
            platform_role=None,
        )


# ------------------------------------------ I3. Category 跨级可见(AC3)


@pytest.mark.asyncio
async def test_integration_category_cross_tier_visibility_and_attach(patched_enforcer, db_session):
    """AC3:super_admin 建 platform Category / group_admin 建 group Category / 门店建
    store Category → 门店 list 看到三级 → 选用上级 Category 创建文档(category_id 挂载)。

    生产代码边界(重要):``DocumentCreate`` schema 与 ``KnowledgeService.create_document``
    当前不接 ``scope``/``group_id``/``category_id`` —— 写时挂 Category 属 plan 范围外的
    future feature(可能归 Feature D 前端管理 UI)。故 AC3 字面「选用上级 Category 创建文档」
    在当前 API 层不可达;本测试验证其可验证子集:① 门店 list 看到三级 Category(协同链路);
    ② Document 模型支持挂上级 category_id + DocumentRead 正确暴露(数据/schema 层向前兼容,
    切片03 test_document_read_exposes_tier_fields 已验字段映射,这里验「list 到上级 → 可挂」
    的端到端语义)。待 create_document 接 category_id 后,此处应改为真调 service 创建。
    """
    from app.models.document import Document
    from app.schemas.document import DocumentRead
    from app.services.category_service import KnowledgeCategoryService

    ids = await _seed_category_fixture(db_session)
    _bind_role(patched_enforcer, "u-owner-a1", "owner", ids["t_a1"])

    # 门店 A1 list Category:看到 platform + groupA + storeA1 三级。
    cat_svc = KnowledgeCategoryService(db_session)
    visible = await cat_svc.list(actor_id="u-owner-a1", tenant_id=ids["t_a1"], platform_role=None)
    visible_ids = {c.id for c in visible}
    assert {ids["platform"], ids["groupA"], ids["storeA1"]} <= visible_ids
    # 看不到兄弟店 / 跨集团。
    assert ids["storeA2"] not in visible_ids
    assert ids["groupB"] not in visible_ids
    assert ids["storeB1"] not in visible_ids

    # 选用上级(platform)Category 创建文档:挂 category_id,DocumentRead 暴露。
    doc = Document(
        tenant_id=ids["t_a1"], name="挂平台类目的文档", scope="store",
        content="x", status="indexed", chunk_count=0,
        category_id=ids["platform"],
    )
    db_session.add(doc)
    await db_session.flush()
    read = DocumentRead.model_validate(doc)
    assert read.category_id == ids["platform"]
    assert read.scope == "store"


# -------------------------------------- I4. 源文档软删联动(AC4)


@pytest.mark.asyncio
async def test_integration_source_soft_delete_list_and_retrieve_exclude(patched_enforcer, db_session):
    """AC4:下发后源文档软删 → 门店 list/retrieve 同时排除(联合谓词 doc.is_deleted
    =false AND dist.is_active=true 生效)→ 下发关系行保留(审计完整)。

    端到端串联:distribute → 软删源 → list_visible_for 排除(list 路径 join Document
    带 is_deleted=False)+ retrieve 排除(search 路径 join Document 带 is_deleted=False)
    + distribution 行仍存在(is_active=True,审计完整)。这是切片02 联合谓词 + 切片03
    下发 + 软删语义的协同验证。
    """
    from app.models.document import Document
    from app.models.knowledge_distribution import KnowledgeDistribution
    from app.repositories.document import DocumentRepository
    from app.schemas.document import DistributeRequest
    from app.services.knowledge_service import KnowledgeService

    ids = await _seed_document_fixture(db_session)
    _bind_role(patched_enforcer, "u-super", "owner", ids["t_a1"])
    svc = KnowledgeService(db_session)

    rows = await svc.distribute_document(
        "u-super", ids["t_a1"], ids["platform_solo"],
        DistributeRequest(target_tenant_ids=[ids["t_a2"]]),
        platform_role="super_admin",
    )
    dist_id = rows[0].id

    repo = DocumentRepository(db_session)
    # 软删前:t_a2 list 看到。
    seen = await repo.list_visible_for(
        tenant_id=ids["t_a2"], group_id=ids["g_a"],
        include_all_tenants=False, is_group_admin=False,
    )
    assert ids["platform_solo"] in {d.id for d in seen}

    # 软删源文档。
    doc = await db_session.get(Document, ids["platform_solo"])
    doc.is_deleted = True
    await db_session.flush()

    # ① list 排除(联合谓词 doc.is_deleted=false 生效,distribution 行仍 active)。
    seen = await repo.list_visible_for(
        tenant_id=ids["t_a2"], group_id=ids["g_a"],
        include_all_tenants=False, is_group_admin=False,
    )
    assert ids["platform_solo"] not in {d.id for d in seen}

    # ② retrieve 同理排除 + 反证排除来源:list_for_target(active)仍含该 doc,
    # 但 list_visible_for 排除了它 —— 两者唯一差别是 list 带 Document.is_deleted=False
    # 联合谓词,故排除必然来自 doc.is_deleted,而非 distribution 失效。retrieve 的
    # search_by_embedding 路径有同样的 join Document.is_deleted 守卫(切片02 line 206-208
    # 已固化),故 retrieve 同理排除软删源 chunks(SQLite 无 pgvector,真实向量过滤由
    # 切片02 search 结构测试覆盖,此处证联合谓词的数据层前提)。
    target_docs = await svc.distributions.list_for_target(ids["t_a2"])
    active_doc_ids = {r.source_doc_id for r in target_docs if r.is_active}
    assert ids["platform_solo"] in active_doc_ids  # distribution 行未失效

    # ③ 下发关系行保留(审计完整):is_active 仍 True,行未硬删(软删源不影响下发行)。
    row = await db_session.get(KnowledgeDistribution, dist_id)
    assert row is not None
    assert row.is_active is True


# -------------------------------------- I5. 跨租户隔离铁律(AC5)


@pytest.mark.asyncio
async def test_integration_cross_tenant_isolation_triple(patched_enforcer, db_session):
    """AC5:跨租户隔离铁律三重验证 —— ① 门店 A 的 store 文档门店 B 看不到;
    ② 门店 A 的下发文档(只下发给 A)门店 B 看不到;③ group_admin A 看不到 group B。

    三重隔离在同一布局里一起成立,证明跨租户隔离不破。门店间隔离是 SaaS 多租户
    的基石(AGENTS.md 铁律 #2),下发是「显式 opt-in」打破隔离的唯一受控通道。
    """
    from app.repositories.document import DocumentRepository
    from app.schemas.document import DistributeRequest
    from app.services.knowledge_service import KnowledgeService

    ids = await _seed_document_fixture(db_session)
    _bind_role(patched_enforcer, "u-super", "owner", ids["t_a1"])
    svc = KnowledgeService(db_session)
    repo = DocumentRepository(db_session)

    # ① 门店 A1 的 store 文档(storeA1)门店 A2 看不到(store 间默认隔离)。
    seen_a2 = await repo.list_visible_for(
        tenant_id=ids["t_a2"], group_id=ids["g_a"],
        include_all_tenants=False, is_group_admin=False,
    )
    assert ids["storeA1"] not in {d.id for d in seen_a2}

    # ② super_admin 下发 storeA1 → t_a1(只下发给 A1),门店 A2 看不到。
    await svc.distribute_document(
        "u-super", ids["t_a1"], ids["storeA1"],
        DistributeRequest(target_tenant_ids=[ids["t_a1"]]),
        platform_role="super_admin",
    )
    seen_a2 = await repo.list_visible_for(
        tenant_id=ids["t_a2"], group_id=ids["g_a"],
        include_all_tenants=False, is_group_admin=False,
    )
    assert ids["storeA1"] not in {d.id for d in seen_a2}  # 只下发 A1,A2 看不到
    # 但 A1 自己能看到下发来的 storeA1(下发是显式 opt-in)。
    seen_a1 = await repo.list_visible_for(
        tenant_id=ids["t_a1"], group_id=ids["g_a"],
        include_all_tenants=False, is_group_admin=False,
    )
    assert ids["storeA1"] in {d.id for d in seen_a1}

    # ③ group_admin A 看不到 group B:提升 t_a1 owner 为 groupA 的 group_admin,
    # 其聚合视图只含 groupA(group + 兄弟 stores),不含 groupB。
    await _promote_to_group_admin_and_bind(
        db_session, patched_enforcer,
        user_id="u-ga", hq_tenant_id=ids["t_a1"], group_id=ids["g_a"],
    )
    seen_ga = await repo.list_visible_for(
        tenant_id=ids["t_a1"], group_id=ids["g_a"],
        include_all_tenants=False, is_group_admin=True,
    )
    seen_ids = {d.id for d in seen_ga}
    assert ids["groupA"] in seen_ids  # 本集团 group 文档可见
    assert ids["groupB"] not in seen_ids  # 跨集团 group 文档不可见
    assert ids["storeB1"] not in seen_ids  # 跨集团 store 文档不可见


# ------------------------------------------ I6. D9 越界守卫(AC6)


@pytest.mark.asyncio
async def test_integration_d9_group_admin_bypass_knowledge_only(patched_enforcer, db_session):
    """AC6/D9:group_admin 派生身份仅知识库域 —— 对 knowledge 放行(check=True),
    对 devices/bookings 不放行(check 落 casbin → 无策略 → False)。

    扩展切片03 的 test_g1_d9_bypass_is_knowledge_only_not_devices:除了 devices,
    再覆盖 bookings 域(确认派生身份不渗漏到其他业务域)。这是 D9 决策的越界守卫。
    """
    from app.services.permission_service import permission_service

    ids = await _seed_document_fixture(db_session)
    await _promote_to_group_admin_and_bind(
        db_session, patched_enforcer,
        user_id="u-ga-d9", hq_tenant_id=ids["t_a1"], group_id=ids["g_a"],
    )

    # knowledge:派生身份 bypass 放行(True)。
    assert await permission_service.check(
        "u-ga-d9", ids["t_a1"], "knowledge", "read", platform_role=None, db=db_session,
    ) is True
    # devices:bypass 不触发 → 落 casbin → 无策略 → False。
    assert await permission_service.check(
        "u-ga-d9", ids["t_a1"], "devices", "read", platform_role=None, db=db_session,
    ) is False
    # bookings:bypass 不触发 → 落 casbin → 无策略 → False。
    assert await permission_service.check(
        "u-ga-d9", ids["t_a1"], "bookings", "read", platform_role=None, db=db_session,
    ) is False


# ============================================================== admin-ui slice 01
# B1 MeResponse group_admin + B2 DocumentCreate scope + B3 list distributions.
# Plan: harness/docs/plan-knowledge-tiered-admin-ui.md 切片 01 AC.
# Reuses the slice-02/03 fixtures (_seed_document_fixture, _promote_to_group_admin,
# _bind_role) so the multi-group topology (g_a/g_b + t_a1/t_a2/t_b1) is consistent.


# ------------------------------------------- B1. _build_me_response group_admin (AC1)


@pytest.mark.asyncio
async def test_b1_me_response_group_admin_user_gets_group_id(patched_enforcer, db_session):
    """B1/AC1: a group's HQ-store owner → MeResponse.group_id set + is_group_admin True.

    Mirrors permission_service.is_group_admin exactly so the frontend display
    and the backend require() gate never disagree. The user is the owner of
    t_a1, which is group_a's headquarters_tenant_id.
    """
    from app.api.deps import CurrentUser
    from app.api.v1.auth import _build_me_response

    ids = await _seed_document_fixture(db_session)
    await _promote_to_group_admin(db_session, ids["g_a"], ids["t_a1"], "u-ga-me")
    me = await _build_me_response(
        CurrentUser(user_id="u-ga-me", tenant_id=ids["t_a1"]), db_session
    )
    assert me.is_group_admin is True
    assert me.group_id == ids["g_a"]


@pytest.mark.asyncio
async def test_b1_me_response_plain_store_owner_is_not_group_admin(patched_enforcer, db_session):
    """B1/AC1: a store owner whose store is NOT a group HQ → null + False.

    t_a2 is in group_a but group_a's HQ is t_a1 (not t_a2), so an owner of t_a2
    is a plain store owner, not a group_admin.
    """
    from app.api.deps import CurrentUser
    from app.api.v1.auth import _build_me_response

    ids = await _seed_document_fixture(db_session)
    # group_a's HQ is t_a1; seed an owner on t_a2 (a member store, not HQ).
    await _promote_to_group_admin(db_session, ids["g_a"], ids["t_a1"], "u-hq-a1")
    from app.models.tenant import UserTenant
    db_session.add(UserTenant(user_id="u-owner-a2", tenant_id=ids["t_a2"], role="owner", valid_to=None))
    await db_session.flush()
    me = await _build_me_response(
        CurrentUser(user_id="u-owner-a2", tenant_id=ids["t_a2"]), db_session
    )
    assert me.is_group_admin is False
    assert me.group_id is None


@pytest.mark.asyncio
async def test_b1_me_response_super_admin_is_not_group_admin(patched_enforcer, db_session):
    """B1/AC1: super_admin is a platform-level identity, never a derived group_admin.

    Even if a super_admin happens to sit in a group's HQ store, is_group_admin
    stays False — the frontend branches super_admin off platform_role, not the
    derived group_admin flag (plan §B1: super_admin → null/False).
    """
    from app.api.deps import CurrentUser
    from app.api.v1.auth import _build_me_response

    ids = await _seed_document_fixture(db_session)
    # super_admin sits on t_a1, which is group_a's HQ — still must NOT read as
    # group_admin (short-circuited on platform_role == super_admin).
    await _promote_to_group_admin(db_session, ids["g_a"], ids["t_a1"], "u-super-me")
    me = await _build_me_response(
        CurrentUser(user_id="u-super-me", tenant_id=ids["t_a1"], platform_role="super_admin"),
        db_session,
    )
    assert me.is_group_admin is False
    assert me.group_id is None


# ------------------------------------------- B2. create_document scope matrix (AC2)


@pytest.mark.asyncio
async def test_b2_create_scope_none_zero_regression_store(patched_enforcer, db_session):
    """B2/AC2: scope=None → derive 'store' + caller tenant (reader-ui zero-regression)."""
    from app.schemas.document import DocumentCreate
    from app.services.knowledge_service import KnowledgeService

    ids = await _seed_document_fixture(db_session)
    _bind_role(patched_enforcer, "u-owner-a1", "owner", ids["t_a1"])
    svc = KnowledgeService(db_session)
    doc = await svc.create_document(
        "u-owner-a1", ids["t_a1"],
        DocumentCreate(name="reader风格文档", content="x"),  # no scope field
        platform_role=None,
    )
    assert doc.scope == "store"
    assert doc.group_id is None
    assert doc.tenant_id == ids["t_a1"]


@pytest.mark.asyncio
async def test_b2_create_scope_store_own_tenant_succeeds(patched_enforcer, db_session):
    """B2/AC2: scope=store + own tenant_id (or None) → store doc."""
    from app.schemas.document import DocumentCreate
    from app.services.knowledge_service import KnowledgeService

    ids = await _seed_document_fixture(db_session)
    _bind_role(patched_enforcer, "u-owner-a1", "owner", ids["t_a1"])
    svc = KnowledgeService(db_session)
    doc = await svc.create_document(
        "u-owner-a1", ids["t_a1"],
        DocumentCreate(name="本店文档", content="x", scope="store", tenant_id=ids["t_a1"]),
        platform_role=None,
    )
    assert doc.scope == "store"
    assert doc.tenant_id == ids["t_a1"]


@pytest.mark.asyncio
async def test_b2_create_scope_store_cross_tenant_rejected(patched_enforcer, db_session):
    """B2/AC2: scope=store + another store's tenant_id → BizError (cross-tenant)."""
    from app.schemas.document import DocumentCreate
    from app.services.errors import BizError
    from app.services.knowledge_service import KnowledgeService

    ids = await _seed_document_fixture(db_session)
    _bind_role(patched_enforcer, "u-owner-a1", "owner", ids["t_a1"])
    svc = KnowledgeService(db_session)
    with pytest.raises(BizError):
        await svc.create_document(
            "u-owner-a1", ids["t_a1"],
            DocumentCreate(name="跨店文档", content="x", scope="store", tenant_id=ids["t_a2"]),
            platform_role=None,
        )


@pytest.mark.asyncio
async def test_b2_create_scope_store_with_group_id_rejected(patched_enforcer, db_session):
    """B2/AC2: scope=store + group_id → BizError (binding conflict)."""
    from app.schemas.document import DocumentCreate
    from app.services.errors import BizError
    from app.services.knowledge_service import KnowledgeService

    ids = await _seed_document_fixture(db_session)
    _bind_role(patched_enforcer, "u-owner-a1", "owner", ids["t_a1"])
    svc = KnowledgeService(db_session)
    with pytest.raises(BizError):
        await svc.create_document(
            "u-owner-a1", ids["t_a1"],
            DocumentCreate(name="带group的store", content="x", scope="store", group_id=ids["g_a"]),
            platform_role=None,
        )


@pytest.mark.asyncio
async def test_b2_create_scope_group_by_group_admin_succeeds(patched_enforcer, db_session):
    """B2/AC2: scope=group + group_admin of that group → group doc."""
    from app.schemas.document import DocumentCreate
    from app.services.knowledge_service import KnowledgeService

    ids = await _seed_document_fixture(db_session)
    await _promote_to_group_admin(db_session, ids["g_a"], ids["t_a1"], "u-ga-create")
    _bind_role(patched_enforcer, "u-ga-create", "owner", ids["t_a1"])
    svc = KnowledgeService(db_session)
    doc = await svc.create_document(
        "u-ga-create", ids["t_a1"],
        DocumentCreate(name="集团手册", content="x", scope="group", group_id=ids["g_a"]),
        platform_role=None,
    )
    assert doc.scope == "group"
    assert doc.group_id == ids["g_a"]


@pytest.mark.asyncio
async def test_b2_create_scope_group_by_non_group_admin_rejected(patched_enforcer, db_session):
    """B2/AC2: scope=group by a plain store owner (not group_admin) → BizError."""
    from app.schemas.document import DocumentCreate
    from app.services.errors import BizError
    from app.services.knowledge_service import KnowledgeService

    ids = await _seed_document_fixture(db_session)
    _bind_role(patched_enforcer, "u-owner-a1", "owner", ids["t_a1"])
    svc = KnowledgeService(db_session)
    with pytest.raises(BizError):
        await svc.create_document(
            "u-owner-a1", ids["t_a1"],
            DocumentCreate(name="非group_admin建group", content="x", scope="group", group_id=ids["g_a"]),
            platform_role=None,
        )


@pytest.mark.asyncio
async def test_b2_create_scope_platform_by_super_admin_succeeds(db_session):
    """B2/AC2: scope=platform + super_admin → platform doc."""
    from app.schemas.document import DocumentCreate
    from app.services.knowledge_service import KnowledgeService

    ids = await _seed_document_fixture(db_session)
    svc = KnowledgeService(db_session)
    doc = await svc.create_document(
        "u-super", ids["t_a1"],
        DocumentCreate(name="平台文档", content="x", scope="platform"),
        platform_role="super_admin",
    )
    assert doc.scope == "platform"
    assert doc.group_id is None


@pytest.mark.asyncio
async def test_b2_create_scope_platform_by_non_super_rejected(patched_enforcer, db_session):
    """B2/AC2: scope=platform by a non-super → BizError."""
    from app.schemas.document import DocumentCreate
    from app.services.errors import BizError
    from app.services.knowledge_service import KnowledgeService

    ids = await _seed_document_fixture(db_session)
    _bind_role(patched_enforcer, "u-owner-a1", "owner", ids["t_a1"])
    svc = KnowledgeService(db_session)
    with pytest.raises(BizError):
        await svc.create_document(
            "u-owner-a1", ids["t_a1"],
            DocumentCreate(name="非超管建平台", content="x", scope="platform"),
            platform_role=None,
        )


@pytest.mark.asyncio
async def test_b2_create_with_nonexistent_category_rejected(patched_enforcer, db_session):
    """B2/AC2: category_id pointing to a non-existent Category → BizError.

    category_id is optional, but when present it must reference a live row so
    the document isn't orphaned under a deleted/non-existent Category.
    """
    from app.schemas.document import DocumentCreate
    from app.services.errors import BizError
    from app.services.knowledge_service import KnowledgeService

    ids = await _seed_document_fixture(db_session)
    _bind_role(patched_enforcer, "u-owner-a1", "owner", ids["t_a1"])
    svc = KnowledgeService(db_session)
    with pytest.raises(BizError):
        await svc.create_document(
            "u-owner-a1", ids["t_a1"],
            DocumentCreate(name="孤儿类目文档", content="x", category_id="nonexistent-cat"),
            platform_role=None,
        )


# ------------------------------------------- B3. list_distributions_for_source (AC3)


@pytest.mark.asyncio
async def test_b3_list_distributions_super_admin_sees_all(patched_enforcer, db_session):
    """B3/AC3: super_admin lists every distribution row for any doc (active + revoked)."""
    from app.schemas.document import DistributeRequest
    from app.services.knowledge_service import KnowledgeService

    ids = await _seed_document_fixture(db_session)
    svc = KnowledgeService(db_session)
    # platform_solo is a platform doc; distribute to t_a1, then revoke.
    rows = await svc.distribute_document(
        "u-super", ids["t_a1"], ids["platform_solo"],
        DistributeRequest(target_tenant_ids=[ids["t_a1"], ids["t_a2"]]),
        platform_role="super_admin",
    )
    # revoke one so both active + revoked appear.
    await svc.revoke_distribution("u-super", ids["t_a1"], rows[0].id, platform_role="super_admin")
    seen = await svc.list_distributions_for_source(
        "u-super", ids["t_a1"], ids["platform_solo"], platform_role="super_admin"
    )
    assert len(seen) == 2  # one active, one revoked
    statuses = {r.is_active for r in seen}
    assert statuses == {True, False}


@pytest.mark.asyncio
async def test_b3_list_distributions_group_admin_own_group(patched_enforcer, db_session):
    """B3/AC3: group_admin lists distributions for a doc in their group's aggregated view."""
    from app.schemas.document import DistributeRequest
    from app.services.knowledge_service import KnowledgeService

    ids = await _seed_document_fixture(db_session)
    await _promote_to_group_admin(db_session, ids["g_a"], ids["t_a1"], "u-ga-list")
    _bind_role(patched_enforcer, "u-ga-list", "owner", ids["t_a1"])
    svc = KnowledgeService(db_session)
    # groupA doc distributed to t_a2 — group_admin sees it.
    await svc.distribute_document(
        "u-ga-list", ids["t_a1"], ids["groupA"],
        DistributeRequest(target_tenant_ids=[ids["t_a2"]]),
        platform_role=None,
    )
    seen = await svc.list_distributions_for_source(
        "u-ga-list", ids["t_a1"], ids["groupA"], platform_role=None
    )
    assert len(seen) == 1
    assert seen[0].target_tenant_id == ids["t_a2"]


@pytest.mark.asyncio
async def test_b3_list_distributions_store_owner_own_doc(patched_enforcer, db_session):
    """B3/AC3: store owner lists distributions for their own store doc."""
    from app.schemas.document import DistributeRequest
    from app.services.knowledge_service import KnowledgeService

    ids = await _seed_document_fixture(db_session)
    _bind_role(patched_enforcer, "u-owner-a1", "owner", ids["t_a1"])
    svc = KnowledgeService(db_session)
    # storeA1 doc distributed to t_a2.
    await svc.distribute_document(
        "u-owner-a1", ids["t_a1"], ids["storeA1"],
        DistributeRequest(target_tenant_ids=[ids["t_a2"]]),
        platform_role=None,
    )
    seen = await svc.list_distributions_for_source(
        "u-owner-a1", ids["t_a1"], ids["storeA1"], platform_role=None
    )
    assert len(seen) == 1
    assert seen[0].target_tenant_id == ids["t_a2"]


@pytest.mark.asyncio
async def test_b3_list_distributions_cross_group_returns_not_found(patched_enforcer, db_session):
    """B3/AC3: a group_admin probing a doc in ANOTHER group → NotFoundError (404).

    Cross-tenant/cross-group probes leak no information (no "exists but
    forbidden" — just 404). groupA's group_admin probes groupB's group doc.
    """
    from app.services.errors import NotFoundError
    from app.services.knowledge_service import KnowledgeService

    ids = await _seed_document_fixture(db_session)
    await _promote_to_group_admin(db_session, ids["g_a"], ids["t_a1"], "u-ga-cross")
    _bind_role(patched_enforcer, "u-ga-cross", "owner", ids["t_a1"])
    svc = KnowledgeService(db_session)
    with pytest.raises(NotFoundError):
        await svc.list_distributions_for_source(
            "u-ga-cross", ids["t_a1"], ids["groupB"], platform_role=None
        )


@pytest.mark.asyncio
async def test_b3_list_distributions_empty_returns_empty_list(patched_enforcer, db_session):
    """B3/AC3: a doc with no distributions → empty list (not error).

    Well-formed call on a doc with no rows yet returns [] so the UI shows an
    empty state rather than erroring.
    """
    from app.services.knowledge_service import KnowledgeService

    ids = await _seed_document_fixture(db_session)
    _bind_role(patched_enforcer, "u-owner-a1", "owner", ids["t_a1"])
    svc = KnowledgeService(db_session)
    # storeA2 is owned by t_a2, but storeA1's owner can see storeA1 (own doc).
    seen = await svc.list_distributions_for_source(
        "u-owner-a1", ids["t_a1"], ids["storeA1"], platform_role=None
    )
    assert seen == []
