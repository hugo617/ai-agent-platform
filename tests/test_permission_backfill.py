"""Parameterized tests for ``backfill_perm_set_for_existing_tenants``.

Replaces the former K chapter in ``test_devices_api.py`` / ``test_bookings_api.py``
(perm-backfill-dedupe slice 02). The two chapters were byte-for-byte mirrors —
the only variation was the ``obj`` literal — so they collapse into one
parametrized suite covering the same 3 scenarios (correctness / idempotency /
scope guardrail) across both objects, plus one whitelist boundary.

Why a separate file (per plan §5):
  * backfill is a pure function-style DB op, not an HTTP endpoint, so it doesn't
    belong in either ``*_api.py`` file's per-chapter narrative;
  * parametrize makes the "obj is the only axis of variation" contract explicit
    and adds a 3rd object later by appending to ``BACKFILLABLE_OBJS`` (no new
    test function — the same parametrize just gains a case).

Expected counts are derived from ``DEFAULT_*_PERMS`` (plan §5 v2: do NOT hardcode
``5+4+2`` — compute from the data source so a future obj with a different perm
count stays correct). Each scenario stands alone (no client fixture — pure DB +
permission_service assertions) and uses a FRESH backfill-target tenant, so it
does not interact with the shared owner/seeded-casbin state in the api files.
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from sqlalchemy import select

from app.core import casbin_enforcer as casbin_mod
from app.models.rbac import Permission, Role, RolePermission
from app.models.tenant import Tenant
from app.services.permission_service import (
    BACKFILLABLE_OBJS,
    DEFAULT_ADMIN_PERMS,
    DEFAULT_MEMBER_PERMS,
    DEFAULT_MENU_PERMS,
    DEFAULT_OWNER_PERMS,
    backfill_perm_set_for_existing_tenants,
    permission_service,
)


def _expected_new_grants(obj: str) -> int:
    """How many role×permission pairs a backfill of ``obj`` should add to a
    tenant that starts with zero ``<obj>``-related grants.

    Computed from the data source (``DEFAULT_*_PERMS``) rather than hardcoded:
    for each system role, count the api perms whose obj matches, plus one menu
    perm if ``<obj>`` is in that role's ``DEFAULT_MENU_PERMS`` entry. The
    pre-seeded unrelated perms (``customers:read`` etc.) are not counted — the
    grant is a no-op on an already-active row.
    """
    api_total = sum(
        1 for o, _ in DEFAULT_OWNER_PERMS if o == obj
    ) + sum(1 for o, _ in DEFAULT_ADMIN_PERMS if o == obj) + sum(
        1 for o, _ in DEFAULT_MEMBER_PERMS if o == obj
    )
    menu_total = sum(
        1 for codes in DEFAULT_MENU_PERMS.values() if obj in codes
    )
    return api_total + menu_total


# A fixed "other obj" seeded as the pre-existing grant the K6 contract must
# prove untouched. ``customers`` is always seeded from day one by
# ``seed_tenant_defaults`` and is never a backfill target (not in
# BACKFILLABLE_OBJS), so it is a safe control obj for every backfillable obj.
# The helper below asserts ``_OTHER_OBJ != obj`` so the invariant holds by
# contract, not by value coincidence — if a future obj collides with customers
# the assert fails loudly instead of the test silently testing the wrong thing.
_OTHER_OBJ = "customers"


async def _seed_backfill_target_tenant(
    db_session, test_env=None, obj: str = "devices"
):
    """Build a tenant that pre-dates ``<obj>`` shipping (K1).

    The tenant has the three system roles (owner/admin/member) and a couple of
    unrelated permission grants to prove the K6 contract — backfill must NOT
    touch other perms. Critically, it has ZERO ``<obj>``-related rows (no
    Permission rows, no RolePermission grants, no casbin policies) when this
    helper returns.

    Parameterized (v2): the unrelated perms use ``other_obj`` (= ``customers``
    for any ``obj``), which is guaranteed != ``obj`` since customers is never a
    backfill target. The grants are mirrored in BOTH the DB (SCD2 grants) AND
    casbin so ``permission_service.check`` returns True before backfill —
    mirroring the two-step write path production ``seed_tenant_defaults`` uses.
    """
    other_obj = _OTHER_OBJ
    assert other_obj != obj, (
        f"control obj {other_obj!r} must differ from backfill target {obj!r} "
        "or the K6 untouched contract tests the wrong perm"
    )

    tenant_id = f"tnt-k-{uuid.uuid4().hex}"
    db_session.add(Tenant(id=tenant_id, name="K Backfill Target"))

    role_ids: dict[str, str] = {}
    for code in ("owner", "admin", "member"):
        rid = uuid.uuid4().hex
        db_session.add(
            Role(
                id=rid,
                tenant_id=tenant_id,
                name=code.capitalize(),
                code=code,
                is_system=True,
                data_scope="tenant",
            )
        )
        role_ids[code] = rid

    # Seed an unrelated api perm (<other_obj>:read) on all three roles + a menu
    # perm (menu:agents) on owner. These prove backfill doesn't touch existing
    # grants (K6). Mirrored in casbin below so ``check`` returns True.
    api_perm_id = uuid.uuid4().hex
    db_session.add(
        Permission(
            id=api_perm_id,
            tenant_id=tenant_id,
            name="其他-查看",
            code=f"{other_obj}:read",
            type="api",
            is_system=True,
        )
    )
    menu_perm_id = uuid.uuid4().hex
    db_session.add(
        Permission(
            id=menu_perm_id,
            tenant_id=tenant_id,
            name="菜单-智能体",
            code="menu:agents",
            type="menu",
            is_system=True,
        )
    )
    for code in ("owner", "admin", "member"):
        db_session.add(
            RolePermission(
                role_id=role_ids[code],
                permission_id=api_perm_id,
                tenant_id=tenant_id,
                valid_from=datetime.now(UTC),
                valid_to=None,
            )
        )
    db_session.add(
        RolePermission(
            role_id=role_ids["owner"],
            permission_id=menu_perm_id,
            tenant_id=tenant_id,
            valid_from=datetime.now(UTC),
            valid_to=None,
        )
    )
    await db_session.commit()

    # Casbin mirror — the SCD2 grants above are the source of truth but casbin
    # is what ``check`` actually reads. Add the same (role, obj, act) pairs so
    # the pre-backfill assertions pass (K6 is "other perms work before AND
    # after").
    if test_env is not None:
        for role in ("owner", "admin", "member"):
            test_env.enforcer.add_policy(role, tenant_id, other_obj, "read")
        test_env.enforcer.add_policy("owner", tenant_id, "menu", "agents")

    return tenant_id, role_ids


@pytest.mark.parametrize("obj", sorted(BACKFILLABLE_OBJS))
@pytest.mark.asyncio
async def test_backfill_grants_perms_correctly(db_session, test_env, obj):
    """K2 + K3 + K4: backfill grants owner the full ``<obj>`` set, member only
    read; both pick up ``menu:<obj>``. Verified through the production code path
    (permission_service.check) so a casbin-sync regression surfaces. Expected
    grant count is derived from DEFAULT_*_PERMS, not hardcoded."""
    tenant_id, _ = await _seed_backfill_target_tenant(
        db_session, test_env, obj=obj
    )
    # The enforcer patch mirrors what app_client sets up: without it, the
    # production ``get_enforcer`` would route casbin calls to the unrelated
    # global SQLite DB (MissingGreenlet). Patch for the whole test.
    with patch.object(casbin_mod, "get_enforcer", return_value=test_env.enforcer):
        # K2: run the backfill. ``db`` must be the same session the assertions
        # use so the writes are visible (test fixture shares one connection).
        stats = await backfill_perm_set_for_existing_tenants(db_session, obj)

        # Expected count is computed from the data source (see helper). The
        # seeded other-obj perms are NOT counted (pre-existing → no-op grant).
        assert stats[tenant_id] == _expected_new_grants(obj), stats

        # K3: owner gets all ``<obj>`` api perms + menu:<obj>. The role name
        # itself is a casbin subject (see conftest _make_casbin), so we check
        # the role directly — no user binding needed.
        owner_api_acts = [a for o, a in DEFAULT_OWNER_PERMS if o == obj]
        for act in owner_api_acts:
            ok = await permission_service.check("owner", tenant_id, obj, act)
            assert ok, f"owner should have {obj}:{act} after backfill"
        ok = await permission_service.check("owner", tenant_id, "menu", obj)
        assert ok, f"owner should have menu:{obj} after backfill"

        # K4: member gets ``<obj>:read`` + ``menu:<obj>`` only — NOT create.
        ok = await permission_service.check("member", tenant_id, obj, "read")
        assert ok, f"member should have {obj}:read after backfill"
        denied = await permission_service.check("member", tenant_id, obj, "create")
        assert not denied, f"member must NOT get {obj}:create (anti-overgrant)"


@pytest.mark.parametrize("obj", sorted(BACKFILLABLE_OBJS))
@pytest.mark.asyncio
async def test_backfill_idempotent(db_session, test_env, obj):
    """K5: re-running backfill on an already-backfilled tenant is a no-op —
    same grants, no error, no duplicate rows."""
    tenant_id, _ = await _seed_backfill_target_tenant(
        db_session, test_env, obj=obj
    )

    with patch.object(casbin_mod, "get_enforcer", return_value=test_env.enforcer):
        await backfill_perm_set_for_existing_tenants(db_session, obj)
        # Snapshot the post-backfill grants so we can detect drift after the
        # second run (active = valid_to IS NULL).
        before_rows = (
            await db_session.execute(
                select(RolePermission).where(
                    RolePermission.tenant_id == tenant_id,
                    RolePermission.valid_to.is_(None),
                )
            )
        ).scalars().all()
        before_ids = {r.id for r in before_rows}

        # K5: run it again. Must not raise, must report zero new grants
        # (everything is already there), must not create duplicate grant rows.
        second = await backfill_perm_set_for_existing_tenants(db_session, obj)
        assert second[tenant_id] == 0, "second run must add 0 grants"

        after_rows = (
            await db_session.execute(
                select(RolePermission).where(
                    RolePermission.tenant_id == tenant_id,
                    RolePermission.valid_to.is_(None),
                )
            )
        ).scalars().all()
        after_ids = {r.id for r in after_rows}
        assert before_ids == after_ids, "no new grant rows should appear"


@pytest.mark.parametrize("obj", sorted(BACKFILLABLE_OBJS))
@pytest.mark.asyncio
async def test_backfill_preserves_other_perms(db_session, test_env, obj):
    """K6: backfill touches ONLY ``<obj>``/``menu:<obj>``. The pre-existing
    other-obj grants survive unchanged — both before/after the backfill."""
    other_obj = _OTHER_OBJ
    tenant_id, _ = await _seed_backfill_target_tenant(
        db_session, test_env, obj=obj
    )

    with patch.object(casbin_mod, "get_enforcer", return_value=test_env.enforcer):
        # Pre-backfill: other-obj perms work for owner/admin/member; menu:agents
        # works for owner. (No ``<obj>`` perms yet.)
        for role in ("owner", "admin", "member"):
            ok = await permission_service.check(role, tenant_id, other_obj, "read")
            assert ok, f"{role} had {other_obj}:read before backfill"
        ok = await permission_service.check("owner", tenant_id, "menu", "agents")
        assert ok, "owner had menu:agents before backfill"

        await backfill_perm_set_for_existing_tenants(db_session, obj)

        # Post-backfill: the original perms still work AND ``<obj>`` perms work.
        for role in ("owner", "admin", "member"):
            ok = await permission_service.check(role, tenant_id, other_obj, "read")
            assert ok, f"{role} should still have {other_obj}:read after backfill"
        ok = await permission_service.check("owner", tenant_id, "menu", "agents")
        assert ok, "owner should still have menu:agents after backfill"
        # And a ``<obj>`` perm does work (backfill actually did something).
        ok = await permission_service.check("owner", tenant_id, obj, "read")
        assert ok, f"owner should have {obj}:read after backfill"


@pytest.mark.asyncio
async def test_backfill_rejects_unknown_obj(db_session):
    """D4 whitelist contract: passing an obj not in BACKFILLABLE_OBJS raises
    ValueError rather than silently no-op'ing. This guards non-script callers
    (tests / other services that import the function directly) — the script
    path is additionally guarded by argparse choices, but the function itself
    must fail loudly. (Not parametrized — a single fixed invalid obj.)"""
    with pytest.raises(ValueError):
        await backfill_perm_set_for_existing_tenants(db_session, "users")
