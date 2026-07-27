"""Contract tests for ``Principal.for_write`` / ``Principal.for_read``.

Mirrors the P0 helper contract test pattern in ``test_devices_api.py``
(``test_p0_helper_contract``) and the ``is_cross_tenant_viewer_contract`` test
in ``test_hq_platform_role.py``: import the real functions and assert their
boundaries, no mocks.

These tests pin the decision table from ``plan-principal-module.md`` §4.1:

- ``for_write`` 4 branches
  (platform writer + tenant_id / platform writer missing tenant_id /
   store role no tenant_id / store role carrying tenant_id).
- ``for_read`` 2 branches
  (panorama viewer / store-role scoped).

The store-role ``for_read`` branch touches the db via
``DataScopeService.resolve``, so it uses the ``db_session`` fixture; the rest
are pure-function contracts.
"""

from unittest.mock import patch

import pytest

from app.services.data_scope import ResolvedScope
from app.services.errors import BizError
from app.services.principal import (
    Principal,
    ReadAccess,
    RequireCall,
    WriteAccess,
)

# =============================================================
# for_write: 4-branch decision table (pure-function contract).
# =============================================================


@pytest.mark.asyncio
async def test_for_write_platform_writer_carries_payload_tenant():
    """Platform writer (super_admin / hq_staff) + payload_tenant_id → bypass.

    effective_tenant = payload_tenant_id, require = None. The service must
    skip the casbin require.
    """
    principal = Principal(db=None)  # db unused on the write path

    access = await principal.for_write(
        actor_id="u1",
        user_tenant_id="user-tnt",
        payload_tenant_id="payload-tnt",
        obj="bookings",
        act="create",
        platform_role="super_admin",
    )
    assert access == WriteAccess(
        effective_tenant="payload-tnt", require=None
    )

    access_hq = await principal.for_write(
        actor_id="u1",
        user_tenant_id="user-tnt",
        payload_tenant_id="payload-tnt",
        obj="bookings",
        act="create",
        platform_role="hq_staff",
    )
    assert access_hq == WriteAccess(
        effective_tenant="payload-tnt", require=None
    )


@pytest.mark.asyncio
async def test_for_write_platform_writer_missing_tenant_id_raises():
    """Platform writer without payload_tenant_id → BizError 400.

    Error message MUST match ``resolve_target_tenant`` byte-for-byte (plan §4.4
    contract §2): "平台角色跨店写必须指定目标门店(tenant_id)".
    """
    principal = Principal(db=None)

    with pytest.raises(BizError) as exc_info_super:
        await principal.for_write(
            actor_id="u1",
            user_tenant_id="user-tnt",
            payload_tenant_id=None,
            obj="bookings",
            act="create",
            platform_role="super_admin",
        )
    assert str(exc_info_super.value) == "平台角色跨店写必须指定目标门店(tenant_id)"

    with pytest.raises(BizError) as exc_info_hq:
        await principal.for_write(
            actor_id="u1",
            user_tenant_id="user-tnt",
            payload_tenant_id=None,
            obj="bookings",
            act="create",
            platform_role="hq_staff",
        )
    assert str(exc_info_hq.value) == "平台角色跨店写必须指定目标门店(tenant_id)"


@pytest.mark.asyncio
async def test_for_write_store_role_without_payload_tenant():
    """Store role (owner/admin/member/customer) without tenant_id → user_tenant.

    effective_tenant = user_tenant_id, require = RequireCall(obj, act) so the
    service runs the normal casbin require.
    """
    principal = Principal(db=None)

    for role in (None, "owner", "admin", "member", "customer"):
        access = await principal.for_write(
            actor_id="u1",
            user_tenant_id="user-tnt",
            payload_tenant_id=None,
            obj="bookings",
            act="create",
            platform_role=role,
        )
        assert access == WriteAccess(
            effective_tenant="user-tnt",
            require=RequireCall(obj="bookings", act="create"),
        ), f"role={role!r}"


@pytest.mark.asyncio
async def test_for_write_store_role_carrying_tenant_id_raises():
    """Store role carrying payload_tenant_id → BizError 400 (anti-forgery).

    Error message MUST match ``resolve_target_tenant`` byte-for-byte:
    "门店角色不可指定目标租户(tenant_id)".
    """
    principal = Principal(db=None)

    for role in (None, "owner", "admin", "member", "customer"):
        with pytest.raises(BizError) as exc_info:
            await principal.for_write(
                actor_id="u1",
                user_tenant_id="user-tnt",
                payload_tenant_id="payload-tnt",
                obj="bookings",
                act="create",
                platform_role=role,
            )
        assert str(exc_info.value) == "门店角色不可指定目标租户(tenant_id)", (
            f"role={role!r}"
        )


# =============================================================
# for_read: 2-branch decision table.
# =============================================================


@pytest.mark.asyncio
async def test_for_read_panorama_viewer():
    """Cross-tenant viewer (super_admin / hq_staff) → panorama branch.

    is_panorama=True, effective_tenant=None, scope=ResolvedScope("all"),
    require=None. This branch short-circuits before any db round-trip, so no
    db fixture is needed.
    """
    principal = Principal(db=None)

    for role in ("super_admin", "hq_staff"):
        access = await principal.for_read(
            actor_id="u1",
            user_tenant_id="user-tnt",
            obj="bookings",
            act="read",
            platform_role=role,
        )
        assert access == ReadAccess(
            effective_tenant=None,
            scope=ResolvedScope(scope="all"),
            require=None,
            is_panorama=True,
        ), f"role={role!r}"
        assert access.scope.scope == "all"
        assert access.scope.tenant_ids == []
        assert access.scope.owner_user_id is None


@pytest.mark.asyncio
async def test_for_read_store_role_scoped(db_session, test_env, tenant_owner):
    """Store role → DataScopeService.resolve drives the scope.

    is_panorama=False, effective_tenant=user_tenant_id, require=RequireCall,
    scope comes from the real DataScopeService. We assert the *shape* (the
    invariant) and delegate the scope-resolution correctness to
    ``test_data_scope.py`` — which exercises DataScopeService end-to-end via
    the customer HTTP path.

    Requires the test env's casbin enforcer to be patched in (same pattern as
    ``app_client`` in conftest.py): ``DataScopeService.resolve`` ultimately
    queries casbin via ``permission_service.get_roles_for_user_in_domain``,
    and without the patch the global enforcer would point at the unrelated
    production SQLite URL.
    """
    from contextlib import ExitStack

    from app.core import casbin_enforcer as casbin_mod

    principal = Principal(db=db_session)
    actor_id = tenant_owner["user_id"]
    tenant_id = tenant_owner["tenant_id"]

    with ExitStack() as stack:
        stack.enter_context(
            patch.object(
                casbin_mod, "get_enforcer", return_value=test_env.enforcer
            )
        )
        access = await principal.for_read(
            actor_id=actor_id,
            user_tenant_id=tenant_id,
            obj="bookings",
            act="read",
            platform_role=None,
        )

    assert access.is_panorama is False
    assert access.effective_tenant == tenant_id
    assert access.require == RequireCall(obj="bookings", act="read")
    # Scope shape: DataScopeService falls back to "tenant" when the seeded
    # owner has no Role row (see test_data_scope.py for that contract). The
    # Principal contract here is just "a real ResolvedScope flows through".
    assert isinstance(access.scope, ResolvedScope)
    assert access.scope.scope in {"all", "tenant", "group", "self"}
