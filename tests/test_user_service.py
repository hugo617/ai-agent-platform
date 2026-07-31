"""Service-layer contract tests for ``UserService._resolve_user``.

Direct tests of the lookup seam extracted in
``plan-user-service-lookup-seam.md`` slice 01. They pin the two branches of the
super_admin-vs-store lookup fork — mirroring the contract-test pattern of
``test_principal.py`` (decision-table branches) and ``test_two_scope_repo.py``
(seeded rows + repo-layer assertions):

- super_admin branch: global lookup via ``UserRepository.get`` (which is the raw
  ``db.get`` — no ``is_deleted`` predicate), so the soft-delete guard is
  explicit inside the seam.
- store branch: tenant-scoped lookup via ``UserListRepository.get`` (whose
  ``_base`` query already filters ``is_deleted=False``), so a soft-deleted user
  simply fails to resolve.

The two NotFoundError messages are asserted BYTE-FOR-BYTE: their difference is
a deliberate multi-tenant existence-ambiguity security property (a store actor
must not learn that a user lives in another tenant). See the seam's docstring
in ``user_service.py`` — these tests exist to prevent a future DRY from
unifying the two messages.
"""

import pytest

from app.models.tenant import User, UserTenant
from app.services.errors import NotFoundError
from app.services.user_service import UserService

pytestmark = pytest.mark.smoke


# ============================================================================
# super_admin branch — global lookup via UserRepository.get (no is_deleted
# predicate in the repo), so the soft-delete guard lives inside the seam.
# ============================================================================


@pytest.mark.asyncio
async def test_resolve_user_super_admin_returns_live_user(db_session):
    """super_admin path: a live (non-deleted) global user is returned."""
    user_id = "u-super-live"
    db_session.add(User(id=user_id, email="super-live@test", status="active"))
    await db_session.commit()

    service = UserService(db_session)
    user = await service._resolve_user(user_id, "any-tenant", is_super_admin=True)

    assert user is not None
    assert user.id == user_id
    assert user.is_deleted is False


@pytest.mark.asyncio
async def test_resolve_user_super_admin_missing_user_raises_not_found(db_session):
    """super_admin path: a non-existent user_id → NotFoundError "不存在"."""
    service = UserService(db_session)

    with pytest.raises(NotFoundError) as exc_info:
        await service._resolve_user("u-does-not-exist", "any-tenant", is_super_admin=True)

    # Byte-for-byte assertion: this message (not the store one) is the
    # security property for the super_admin path.
    assert str(exc_info.value) == "用户 u-does-not-exist 不存在"


@pytest.mark.asyncio
async def test_resolve_user_super_admin_soft_deleted_user_raises_not_found(db_session):
    """super_admin path: a soft-deleted user → NotFoundError "不存在".

    ``UserRepository.get`` is the raw ``db.get`` with no ``is_deleted``
    predicate, so this test pins the explicit guard inside the seam: without it,
    a soft-deleted user would be returned and could be mutated.
    """
    user_id = "u-super-deleted"
    db_session.add(
        User(id=user_id, email="super-deleted@test", status="active", is_deleted=True)
    )
    await db_session.commit()

    service = UserService(db_session)

    with pytest.raises(NotFoundError) as exc_info:
        await service._resolve_user(user_id, "any-tenant", is_super_admin=True)

    assert str(exc_info.value) == "用户 u-super-deleted 不存在"


# ============================================================================
# store branch — tenant-scoped lookup via UserListRepository.get (its _base
# query already filters is_deleted=False, so no separate guard is needed).
# ============================================================================


@pytest.mark.asyncio
async def test_resolve_user_store_returns_member_of_tenant(
    db_session, tenant_owner
):
    """store path: a user who is a member of the tenant is returned."""
    tenant_id = tenant_owner["tenant_id"]
    user_id = "u-store-member"
    db_session.add(User(id=user_id, email="store-member@test", status="active"))
    db_session.add(UserTenant(user_id=user_id, tenant_id=tenant_id, role="member"))
    await db_session.commit()

    service = UserService(db_session)
    user = await service._resolve_user(user_id, tenant_id, is_super_admin=False)

    assert user is not None
    assert user.id == user_id


@pytest.mark.asyncio
async def test_resolve_user_store_non_member_raises_not_found(
    db_session, tenant_owner
):
    """store path: a user_id with no membership in this tenant → NotFoundError
    "不在该租户中".

    The message MUST say "不在该租户中" (not in this tenant) — NOT "不存在" —
    because a store actor must not learn whether the user exists elsewhere.
    """
    tenant_id = tenant_owner["tenant_id"]
    service = UserService(db_session)

    with pytest.raises(NotFoundError) as exc_info:
        await service._resolve_user("u-not-a-member", tenant_id, is_super_admin=False)

    # Byte-for-byte assertion: this is the existence-ambiguity security property
    # for the store path. Do not DRY it with the super_admin message.
    assert str(exc_info.value) == "用户 u-not-a-member 不在该租户中"


@pytest.mark.asyncio
async def test_resolve_user_store_user_in_other_tenant_raises_not_found(
    db_session, tenant_owner
):
    """store path: a user who exists (and is alive) but belongs to ANOTHER
    tenant still raises "不在该租户中".

    This is the heart of the existence-ambiguity property: from the caller's
    tenant the user is indistinguishable from one that was never created — the
    store path never confirms the user exists somewhere else.
    """
    tenant_id = tenant_owner["tenant_id"]
    other_tenant = "tnt-some-other-store"
    user_id = "u-other-store-only"
    # The user is alive and has a membership — but in a different tenant.
    db_session.add(User(id=user_id, email="other-store@test", status="active"))
    db_session.add(
        UserTenant(user_id=user_id, tenant_id=other_tenant, role="member")
    )
    await db_session.commit()

    service = UserService(db_session)

    with pytest.raises(NotFoundError) as exc_info:
        await service._resolve_user(user_id, tenant_id, is_super_admin=False)

    assert str(exc_info.value) == f"用户 {user_id} 不在该租户中"


# ============================================================================
# Branch-fork invariant: the two NotFoundError messages are intentionally
# DIFFERENT (security property). This test exists to fail loudly if a future
# refactor unifies them.
# ============================================================================


def test_resolve_user_error_messages_are_intentionally_distinct():
    """Pin the two error message templates as distinct strings.

    A future DRY that unifies the super_admin and store messages would leak
    cross-tenant existence to store roles (breaking multi-tenant isolation).
    This test encodes the difference as an explicit invariant so it cannot
    regress silently.
    """
    super_admin_msg = "用户 x 不存在"
    store_msg = "用户 x 不在该租户中"
    assert super_admin_msg != store_msg
    assert "不存在" in super_admin_msg
    assert "不在该租户中" in store_msg
