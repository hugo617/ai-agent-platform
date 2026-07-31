"""Service-layer contract tests for ``MemberService``.

Direct tests of the SCD2 + casbin dual-write contract that ``MemberService``
(list / add / update_role / remove) executes. This isolates the membership
dual-write from ``UserService`` so a casbin sync drift bug can be located at
``MemberService`` rather than only surfaced indirectly through
``test_rbac_api.py`` / ``test_users_api.py`` HTTP tests.

Paradigm (plan-member-service-direct-tests.md §4 grill decisions):

- **D1 — only test externally observable contract.** Assert DB membership state
  (``memberships.current_role``) + casbin grouping state
  (``enforcer.has_role_for_user_in_domain``) + exception type/message. Never
  assert the call count or order of ``assign_role`` /
  ``set_role_for_user_in_domain`` (those are implementation details that change
  with refactors; testing them would lock the refactor down).
- **D2 — service-layer direct test.** Use the ``test_env`` fixture + ``factory``
  to build ``MemberService``, and ``patch.object(casbin_mod, "get_enforcer",
  return_value=test_env.enforcer)`` to inject the isolated enforcer. No HTTP
  round-trip (``test_rbac_api.py`` already covers happy paths end-to-end).
- **D3 — cover all 4 methods' contract + boundaries**: dual-write consistency
  (add adds / update old-gone-new-appears / remove all-gone), NotFoundError for
  non-members, BizError self-guard on remove, SCD2 history preservation
  (soft-delete, not physical delete), add's get_or_create path.
- **D4 — do not change member_service source.** Pure test addition. If a test
  surfaces a real bug, raise it as a separate bug-fix feature, not here.

Mirrors the contract-test pattern of ``test_principal.py`` (decision-table
branches, real DB + real casbin enforcer via ``patch.object``) and
``test_scd2_history.py`` (SCD2 history-preservation assertions that read raw
rows past the ``valid_to`` filter).
"""

from unittest.mock import patch

import pytest
from sqlalchemy import select

from app.core import casbin_enforcer as casbin_mod
from app.models.tenant import User, UserTenant
from app.repositories.tenant import UserTenantRepository
from app.schemas.user import MemberCreate, MemberUpdate
from app.services.errors import BizError, NotFoundError
from app.services.member_service import MemberService

pytestmark = pytest.mark.smoke


def _has_role(enforcer, user_id: str, role: str, tenant_id: str) -> bool:
    """Domain-aware role-membership assertion.

    casbin's Python SDK exposes ``has_role_for_user(user, role)`` WITHOUT a
    domain argument (it ignores the domain matchers in an RBAC-with-domains
    model), so the correct domain-aware check is membership in
    ``get_roles_for_user_in_domain(user, domain)``. Centralising it keeps the
    contract assertions readable and documents the SDK gap in one place.
    """
    return role in enforcer.get_roles_for_user_in_domain(user_id, tenant_id)


# ============================================================================
# Helper: run a service call with the test env's enforcer injected.
#
# permission_service reads the enforcer via ``_casbin_mod.get_enforcer()`` (see
# its docstring at permission_service.py L46 — "tests can monkeypatch"). Without
# this patch the global enforcer would point at the unrelated production SQLite
# URL and every casbin check would blow up. The patch must wrap the whole call
# so ``require`` (check), ``add_role_for_user_in_domain`` / ``set_role...`` /
# ``remove_user_from_tenant`` all see the same isolated enforcer.
# ============================================================================


def _enforcer_patch(test_env):
    return patch.object(casbin_mod, "get_enforcer", return_value=test_env.enforcer)


# ============================================================================
# list — contract
# ============================================================================


@pytest.mark.asyncio
async def test_list_returns_seeded_owner_membership(test_env, tenant_owner, db_session):
    """list returns the seeded owner membership as ``MemberRead``.

    ``test_env`` seeds one owner ``UserTenant`` for the tenant, so the owner's
    ``list`` MUST surface exactly that row. Pins the list → ``MemberRead``
    mapping (user_id / role / joined_at) and the seed precondition the other
    tests rely on.

    The plan's "empty tenant → []" branch is not asserted separately: a tenant
    owner cannot ``list`` a foreign tenant (``require("users", "read")`` is
    domain-scoped — the owner's ``users:read`` policy is seeded only for their
    own tenant), so "no members visible" is unreachable via the owner principal
    the service-layer seam exposes. The empty-list behaviour is the trivial
    list-comprehension over ``[]`` and is covered structurally by the seeded
    case above.
    """
    tenant_id = tenant_owner["tenant_id"]
    owner_id = tenant_owner["user_id"]

    service = MemberService(db_session)
    with _enforcer_patch(test_env):
        members = await service.list(owner_id, tenant_id)

    assert len(members) == 1
    owner_member = members[0]
    assert owner_member.user_id == owner_id
    assert owner_member.role == "owner"
    assert owner_member.email == "owner@example.com"
    assert owner_member.joined_at is not None


# ============================================================================
# add — dual-write consistency
# ============================================================================


@pytest.mark.asyncio
async def test_add_new_member_dual_writes_db_and_casbin(test_env, tenant_owner, db_session):
    """add(role=admin) on a brand-new user → DB ``current_role`` is admin AND
    casbin grouping binds (user, admin, tenant).

    This is the security property the dual-write exists for: if casbin drifts,
    the new member either gets no access (under-grant) or the wrong role
    (over-grant). The test pins BOTH stores landing on the same role.
    """
    tenant_id = tenant_owner["tenant_id"]
    owner_id = tenant_owner["user_id"]
    new_user = "u-add-admin"

    payload = MemberCreate(user_id=new_user, role="admin")
    service = MemberService(db_session)
    with _enforcer_patch(test_env):
        result = await service.add(owner_id, tenant_id, payload)

    # Return value is the membership view.
    assert result.user_id == new_user
    assert result.role == "admin"

    # DB side: the active membership row holds the new role.
    memberships = UserTenantRepository(db_session)
    assert (await memberships.current_role(new_user, tenant_id)).role == "admin"

    # Casbin side: the grouping policy binds the user to the role in this tenant.
    assert _has_role(test_env.enforcer, new_user, "admin", tenant_id)


@pytest.mark.asyncio
async def test_add_get_or_create_creates_missing_user(test_env, tenant_owner, db_session):
    """add with a ``user_id`` that has no ``User`` row → the user is created via
    ``UserRepository.get_or_create`` and the membership is established.

    This is the get_or_create path called out in plan §4 D3: the membership
    service must not assume the user already exists. We pass an ``email`` so the
    created user carries it (the field is nullable, but asserting it pins that
    ``get_or_create`` forwards the email, not just the id).
    """
    tenant_id = tenant_owner["tenant_id"]
    owner_id = tenant_owner["user_id"]
    new_user = "u-get-or-create"
    email = "created@example.com"

    assert (await db_session.get(User, new_user)) is None  # precondition: absent

    payload = MemberCreate(user_id=new_user, role="member", email=email)
    service = MemberService(db_session)
    with _enforcer_patch(test_env):
        await service.add(owner_id, tenant_id, payload)

    created = await db_session.get(User, new_user)
    assert created is not None
    assert created.email == email


# ============================================================================
# update_role — dual-write consistency + boundary
# ============================================================================


@pytest.mark.asyncio
async def test_update_role_dual_writes_db_and_casbin_old_role_gone_new_appears(
    test_env, tenant_owner, db_session
):
    """owner changes a member's role member→admin: DB ``current_role`` reflects
    admin AND casbin drops the old ``member`` grouping AND adds the new
    ``admin`` grouping.

    The two casbin assertions together are the contract: ``set_role_for_user_in_domain``
    MUST remove the prior role before adding the new one (a stale old role would
    be an over-grant — the user keeps both roles). We assert the old role is
    gone AND the new role is present, which is the externally observable form of
    "set, not add".
    """
    tenant_id = tenant_owner["tenant_id"]
    owner_id = tenant_owner["user_id"]
    target = "u-role-change"

    # Seed the target as a member first (add establishes both stores).
    service = MemberService(db_session)
    with _enforcer_patch(test_env):
        await service.add(owner_id, tenant_id, MemberCreate(user_id=target, role="member"))

    # Now change the role.
    with _enforcer_patch(test_env):
        result = await service.update_role(
            owner_id, tenant_id, target, MemberUpdate(role="admin")
        )

    assert result.role == "admin"

    # DB side.
    memberships = UserTenantRepository(db_session)
    assert (await memberships.current_role(target, tenant_id)).role == "admin"

    # Casbin side: old role gone, new role present.
    assert not _has_role(test_env.enforcer, target, "member", tenant_id)
    assert _has_role(test_env.enforcer, target, "admin", tenant_id)


@pytest.mark.asyncio
async def test_update_role_non_member_raises_not_found(test_env, tenant_owner, db_session):
    """update_role on a user who is not a member → NotFoundError, byte-for-byte.

    The message MUST be ``"user {id} is not a member of this tenant"`` — it is
    the contract the API exposes, and a future refactor that changes it would
    silently shift the API surface.
    """
    tenant_id = tenant_owner["tenant_id"]
    owner_id = tenant_owner["user_id"]
    stranger = "u-never-joined"

    service = MemberService(db_session)
    with pytest.raises(NotFoundError) as exc_info:
        with _enforcer_patch(test_env):
            await service.update_role(
                owner_id, tenant_id, stranger, MemberUpdate(role="admin")
            )

    assert str(exc_info.value) == f"user {stranger} is not a member of this tenant"


# ============================================================================
# remove — dual-write consistency + SCD2 history + self-guard + boundary
# ============================================================================


@pytest.mark.asyncio
async def test_remove_dual_writes_db_and_casbin_strips_all_roles(
    test_env, tenant_owner, db_session
):
    """remove → DB ``current_role`` returns None (no active membership) AND
    casbin holds NO role for the user in this tenant.

    ``remove_user_from_tenant`` strips every role the user held in the domain,
    so we assert against ``get_roles_for_user_in_domain`` being empty (not just
    the one role they joined with) — the contract is "access stops", not "one
    role removed".
    """
    tenant_id = tenant_owner["tenant_id"]
    owner_id = tenant_owner["user_id"]
    target = "u-remove-target"

    service = MemberService(db_session)
    with _enforcer_patch(test_env):
        await service.add(owner_id, tenant_id, MemberCreate(user_id=target, role="member"))

    # Confirm the precondition before removing.
    assert _has_role(test_env.enforcer, target, "member", tenant_id)

    with _enforcer_patch(test_env):
        result = await service.remove(owner_id, tenant_id, target)

    assert result is None  # remove returns None on success

    # DB side: no active membership.
    memberships = UserTenantRepository(db_session)
    assert await memberships.current_role(target, tenant_id) is None

    # Casbin side: no role of any kind remains.
    assert test_env.enforcer.get_roles_for_user_in_domain(target, tenant_id) == []


@pytest.mark.asyncio
async def test_remove_preserves_scd2_history_row(test_env, tenant_owner, db_session):
    """remove closes the active row (``valid_to`` set) but keeps it physically —
    SCD2 history is preserved, not a hard delete.

    We read the raw ``UserTenant`` rows (past the ``current_role`` valid_to
    filter) and assert: at least one closed row exists for (target, tenant)
    and every such row has ``valid_to`` set. This pins the soft-delete
    contract: a future change that turns remove into a physical delete would
    drop audit history and break this test loudly.
    """
    tenant_id = tenant_owner["tenant_id"]
    owner_id = tenant_owner["user_id"]
    target = "u-scd2-history"

    service = MemberService(db_session)
    with _enforcer_patch(test_env):
        await service.add(owner_id, tenant_id, MemberCreate(user_id=target, role="member"))
        await service.remove(owner_id, tenant_id, target)

    rows = list(
        (
            await db_session.execute(
                select(UserTenant).where(
                    UserTenant.user_id == target,
                    UserTenant.tenant_id == tenant_id,
                )
            )
        ).scalars().all()
    )
    assert len(rows) >= 1, "history row must be physically retained after remove"
    assert all(r.valid_to is not None for r in rows), "every retained row is closed"


@pytest.mark.asyncio
async def test_remove_self_guard_raises_biz_error(test_env, tenant_owner, db_session):
    """owner removing themselves → BizError("cannot remove yourself").

    The self-guard prevents a tenant from losing its last owner (and the actor
    from locking themselves out). The message is byte-for-byte pinned so a
    refactor cannot silently relax the wording.
    """
    tenant_id = tenant_owner["tenant_id"]
    owner_id = tenant_owner["user_id"]

    service = MemberService(db_session)
    with pytest.raises(BizError) as exc_info:
        with _enforcer_patch(test_env):
            await service.remove(owner_id, tenant_id, owner_id)

    assert str(exc_info.value) == "cannot remove yourself"


@pytest.mark.asyncio
async def test_remove_non_member_raises_not_found(test_env, tenant_owner, db_session):
    """remove on a non-member → NotFoundError (same message as update_role)."""
    tenant_id = tenant_owner["tenant_id"]
    owner_id = tenant_owner["user_id"]
    stranger = "u-never-joined-remove"

    service = MemberService(db_session)
    with pytest.raises(NotFoundError) as exc_info:
        with _enforcer_patch(test_env):
            await service.remove(owner_id, tenant_id, stranger)

    assert str(exc_info.value) == f"user {stranger} is not a member of this tenant"
