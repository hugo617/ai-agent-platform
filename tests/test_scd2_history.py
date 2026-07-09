"""SCD2 history tests for user_tenants + role_permissions.

Covers the two scenarios from ``docs/auth-history-scd2-plan.md``:
  i.  "what role did this user hold at time T?" — user_tenants SCD2
  ii. "what permissions did this role have at time T?" — role_permissions SCD2

Plus the cross-cutting guarantees:
  - assign_role closes the old row + opens a new one (history preserved)
  - remove_member keeps the history row (no physical delete)
  - the partial unique index blocks two active rows for the same (user, tenant)
  - grant/revoke resync casbin so the change takes effect immediately
"""

import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core import casbin_enforcer as casbin_mod
from app.models.rbac import Role
from app.models.tenant import Tenant, User, UserTenant
from app.repositories.rbac import RolePermissionRepository
from app.repositories.tenant import UserTenantRepository
from app.services.permission_service import permission_service
from app.services.rbac_service import RbacService

AUTH = {"Authorization": "Bearer fake"}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def file_enforcer():
    """A fresh file-backed casbin enforcer, for db_session-only tests.

    db_session tests bypass app_client (which patches get_enforcer), so without
    this fixture seed_tenant_defaults → add_policy would build the real
    SQLAlchemy casbin adapter against the in-memory async SQLite URL and blow up
    with MissingGreenlet. Request this fixture explicitly in DB-only tests;
    HTTP tests use app_client's own enforcer instead.
    """
    import os
    import tempfile
    from unittest.mock import patch

    import casbin
    from casbin.persist.adapters import FileAdapter

    policy_file = os.path.join(tempfile.mkdtemp(), "policy.csv")
    open(policy_file, "w").close()
    e = casbin.Enforcer("casbin_model.conf", FileAdapter(policy_file))

    with patch.object(casbin_mod, "get_enforcer", return_value=e):
        yield e


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _seed_tenant_with_roles(db, tenant_id: str, owner_user: str) -> dict[str, str]:
    """Minimal tenant + system roles + owner membership + permissions seed.

    Mirrors TenantService.create_tenant minus the casbin file adapter (tests
    inject their own enforcer). Returns role ids by code.
    """
    db.add(Tenant(id=tenant_id, name="T"))
    db.add(User(id=owner_user, email=f"{owner_user}@x.com", status="active"))
    await db.flush()
    await RbacService(db).seed_defaults(tenant_id)
    # Owner membership via the SCD2 write path (so tests that read current_role
    # see one active row, exactly like production).
    await UserTenantRepository(db).assign_role(owner_user, tenant_id, "owner")
    await permission_service.seed_tenant_defaults(tenant_id, owner_user, db=db)
    await db.commit()
    rows = (
        await db.execute(
            select(Role.code, Role.id).where(
                Role.tenant_id == tenant_id, Role.is_deleted.is_(False)
            )
        )
    ).all()
    return {code: rid for code, rid in rows}


# ---------------------------------------------------------------------------
# Scenario i — user_tenants SCD2 (member role history)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_assign_role_creates_history(db_session, file_enforcer):
    """Three role changes → three history rows, one active."""
    tenant_id = f"tnt-{uuid.uuid4().hex}"
    user_id = f"user-{uuid.uuid4().hex}"
    await _seed_tenant_with_roles(db_session, tenant_id, user_id)
    repo = UserTenantRepository(db_session)

    t0 = datetime.utcnow() - timedelta(hours=3)
    t1 = t0 + timedelta(hours=1)
    t2 = t1 + timedelta(hours=1)

    await repo.assign_role(user_id, tenant_id, "owner", at=t0)
    await repo.assign_role(user_id, tenant_id, "admin", at=t1)
    await repo.assign_role(user_id, tenant_id, "member", at=t2)
    await db_session.commit()

    all_rows = list(
        (
            await db_session.execute(
                select(UserTenant).where(
                    UserTenant.user_id == user_id, UserTenant.tenant_id == tenant_id
                )
            )
        ).scalars().all()
    )
    # Seed created the first "owner" row, then assign_role ran 3 times. The
    # initial seeded row + 3 assigns = 4 rows total (seed owner, then
    # owner→admin→member each close+open).
    assert len(all_rows) >= 3
    active = [r for r in all_rows if r.valid_to is None]
    assert len(active) == 1, "exactly one active row"
    assert active[0].role == "member"


@pytest.mark.asyncio
async def test_member_role_at_point_in_time(db_session, file_enforcer):
    """Scenario i: restore the role held at each timestamp.

    Build a clean past timeline owner(t0) → admin(t1) → member(t2) with all
    timestamps strictly in the past and in order, then assert the point-in-time
    restore returns each phase and current_role returns the latest.
    """
    tenant_id = f"tnt-{uuid.uuid4().hex}"
    user_id = f"user-{uuid.uuid4().hex}"
    await _seed_tenant_with_roles(db_session, tenant_id, user_id)
    repo = UserTenantRepository(db_session)

    base = datetime.utcnow() - timedelta(hours=3)
    t0 = base
    t1 = base + timedelta(hours=1)
    t2 = base + timedelta(hours=2)
    # Each assign closes the prior active row and opens a new one at the given
    # timestamp. We start with "admin" (different from the seeded "owner") so
    # the first assign is not absorbed by the same-role idempotency short-circuit,
    # guaranteeing a clean three-row history: admin(t0) → member(t1) → owner(t2).
    await repo.assign_role(user_id, tenant_id, "admin", at=t0)
    await repo.assign_role(user_id, tenant_id, "member", at=t1)
    await repo.assign_role(user_id, tenant_id, "owner", at=t2)
    await db_session.commit()

    # Point-in-time restore at each phase.
    assert (await repo.member_role_at(user_id, tenant_id, t0 + timedelta(minutes=1))).role == "admin"
    assert (await repo.member_role_at(user_id, tenant_id, t1 + timedelta(minutes=1))).role == "member"
    assert (await repo.member_role_at(user_id, tenant_id, t2 + timedelta(minutes=1))).role == "owner"
    # Current state: the latest row.
    assert (await repo.current_role(user_id, tenant_id)).role == "owner"


@pytest.mark.asyncio
async def test_remove_member_preserves_history(db_session, file_enforcer):
    tenant_id = f"tnt-{uuid.uuid4().hex}"
    user_id = f"user-{uuid.uuid4().hex}"
    await _seed_tenant_with_roles(db_session, tenant_id, user_id)
    repo = UserTenantRepository(db_session)

    assert await repo.current_role(user_id, tenant_id) is not None
    assert await repo.remove_member(user_id, tenant_id) is True
    await db_session.commit()

    # Current state: no active membership.
    assert await repo.current_role(user_id, tenant_id) is None
    # History: the closed row still exists.
    closed = list(
        (
            await db_session.execute(
                select(UserTenant).where(
                    UserTenant.user_id == user_id, UserTenant.tenant_id == tenant_id
                )
            )
        ).scalars().all()
    )
    assert len(closed) >= 1
    assert all(r.valid_to is not None for r in closed)


@pytest.mark.asyncio
async def test_partial_unique_blocks_two_active_memberships(db_session, file_enforcer):
    """The partial unique index forbids two active rows for one (user, tenant)."""
    tenant_id = f"tnt-{uuid.uuid4().hex}"
    user_id = f"user-{uuid.uuid4().hex}"
    await _seed_tenant_with_roles(db_session, tenant_id, user_id)

    # Seed already created one active row; inserting a second active one must fail.
    db_session.add(
        UserTenant(user_id=user_id, tenant_id=tenant_id, role="admin", valid_to=None)
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


# ---------------------------------------------------------------------------
# Scenario ii — role_permissions SCD2 (role permission-set history)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_grant_and_revoke_with_casbin_sync(db_session, file_enforcer):
    """grant → active SCD2 row + casbin policy; revoke closes the row + drops it."""
    tenant_id = f"tnt-{uuid.uuid4().hex}"
    owner = f"user-{uuid.uuid4().hex}"
    role_ids = await _seed_tenant_with_roles(db_session, tenant_id, owner)
    member_role_id = role_ids["member"]
    repo = RolePermissionRepository(db_session)

    # The member role already has its default perms from the seed. Grant an
    # extra one and confirm it lands in both SCD2 and casbin.
    pid = await permission_service._upsert_permission(
        db_session, tenant_id, "agents", "delete"
    )
    await repo.grant(member_role_id, pid, tenant_id)
    await permission_service.sync_role_permissions_to_casbin(
        db_session, member_role_id, tenant_id
    )
    await db_session.commit()

    active = await repo.current_permissions(member_role_id, tenant_id)
    assert any(p.permission_id == pid for p in active)

    e = casbin_mod.get_enforcer()
    assert e.has_policy("member", tenant_id, "agents", "delete")

    # Revoke → row closes, casbin policy disappears.
    assert await repo.revoke(member_role_id, pid, tenant_id) is True
    await permission_service.sync_role_permissions_to_casbin(
        db_session, member_role_id, tenant_id
    )
    await db_session.commit()

    active_after = await repo.current_permissions(member_role_id, tenant_id)
    assert all(p.permission_id != pid for p in active_after)
    assert not e.has_policy("member", tenant_id, "agents", "delete")


@pytest.mark.asyncio
async def test_permissions_at_point_in_time(db_session, file_enforcer):
    """Scenario ii: restore a role's permission set at a past timestamp."""
    tenant_id = f"tnt-{uuid.uuid4().hex}"
    owner = f"user-{uuid.uuid4().hex}"
    role_ids = await _seed_tenant_with_roles(db_session, tenant_id, owner)
    member_role_id = role_ids["member"]
    repo = RolePermissionRepository(db_session)

    t0 = datetime.utcnow() - timedelta(hours=2)
    t1 = t0 + timedelta(hours=1)

    pid_before = await permission_service._upsert_permission(
        db_session, tenant_id, "agents", "delete"
    )
    await repo.grant(member_role_id, pid_before, tenant_id, at=t0)
    pid_after = await permission_service._upsert_permission(
        db_session, tenant_id, "users", "delete"
    )
    await repo.grant(member_role_id, pid_after, tenant_id, at=t1)
    await db_session.commit()

    at_before = await repo.permissions_at(member_role_id, tenant_id, t0 + timedelta(minutes=1))
    at_after = await repo.permissions_at(member_role_id, tenant_id, t1 + timedelta(minutes=1))
    ids_before = {p.permission_id for p in at_before}
    ids_after = {p.permission_id for p in at_after}
    assert pid_before in ids_before and pid_after not in ids_before
    assert pid_before in ids_after and pid_after in ids_after


# ---------------------------------------------------------------------------
# HTTP — grant/revoke endpoint resyncs casbin (end-to-end)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_grant_permission_endpoint_resyncs_casbin(
    app_client, tenant_owner, db_session
):
    """Granting via the API immediately enables the permission for role holders.

    The owner is the only role holder; granting the owner role an extra
    permission must (a) land an active role_permissions row, (b) appear in the
    listing, and (c) immediately show up as a casbin policy for that role.
    """
    tenant_id = tenant_owner["tenant_id"]
    owner_user = tenant_owner["user_id"]

    # The test_env fixture seeds Tenant/User/UserTenant but NOT the system roles.
    # Seed them now (roles + permissions + role_permissions + casbin), mirroring
    # TenantService.create_tenant.
    await RbacService(db_session).seed_defaults(tenant_id)
    await permission_service.seed_tenant_defaults(tenant_id, owner_user, db=db_session)
    await db_session.commit()

    # Resolve the owner role id via the labels endpoint.
    labels = (await app_client.get("/api/v1/roles/label", headers=AUTH)).json()
    owner_role = next(r for r in labels if r["code"] == "owner")

    resp = await app_client.post(
        f"/api/v1/roles/{owner_role['id']}/permissions",
        json={"obj": "agents", "act": "delete"},
        headers=AUTH,
    )
    assert resp.status_code == 201, resp.text

    e = casbin_mod.get_enforcer()
    assert e.has_policy("owner", tenant_id, "agents", "delete")

    listed = (
        await app_client.get(
            f"/api/v1/roles/{owner_role['id']}/permissions", headers=AUTH
        )
    ).json()
    assert any(p["obj"] == "agents" and p["act"] == "delete" for p in listed)
