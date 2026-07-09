"""Unit tests for ``PermissionService.check`` / ``require`` — the single RBAC chokepoint.

These tests target the pure permission logic directly (not the HTTP layer),
covering the branches that the API integration tests in
``test_user_permissions.py`` only exercise indirectly:

  * the ``super_admin`` short-circuit (returns True before touching casbin),
  * plain member → False on a ``users`` action (zero policies),
  * owner → True on ``users:delete`` (policy exists),
  * ``require()`` raising ``PermissionError`` on denial and returning None on success.

The enforcer is the same file-backed seed used by the conftest fixtures, but we
stand it up here via ``_make_casbin`` so the test is hermetic and independent
of the DB/http machinery.
"""

import pytest

from app.core import casbin_enforcer as casbin_mod
from app.services.permission_service import PermissionService

TENANT = "tnt-unit"
OWNER = "owner-unit"
MEMBER = "member-unit"


@pytest.fixture
def enforcer(monkeypatch):
    """A file-backed enforcer seeded with the default owner/admin/member matrix.

    Only the OWNER is bound to a role; member stays role-less so we can assert
    the "no policy → deny" path. Patched onto the casbin module so
    ``PermissionService.check`` picks it up.
    """
    from tests.conftest import _make_casbin

    e = _make_casbin(OWNER, TENANT)
    # Bind the member user explicitly so the casbin grouping exists.
    e.add_role_for_user_in_domain(MEMBER, "member", TENANT)
    monkeypatch.setattr(casbin_mod, "get_enforcer", lambda: e)
    return e


@pytest.mark.asyncio
async def test_super_admin_short_circuits_before_casbin(enforcer):
    """A super_admin returns True for ANY obj/act without consulting casbin."""
    svc = PermissionService()
    # Even nonsensical obj/act must pass — proves the bypass precedes enforce().
    assert await svc.check(OWNER, TENANT, "users", "delete", platform_role="super_admin")
    assert await svc.check(OWNER, TENANT, "anything", "nuke", platform_role="super_admin")


@pytest.mark.asyncio
async def test_member_denied_users_read(enforcer):
    """The member role has no ``users`` policies → check returns False."""
    svc = PermissionService()
    assert await svc.check(MEMBER, TENANT, "users", "read") is False


@pytest.mark.asyncio
async def test_owner_allowed_users_delete(enforcer):
    """The owner role seeds ``users:delete`` → check returns True."""
    svc = PermissionService()
    assert await svc.check(OWNER, TENANT, "users", "delete") is True


@pytest.mark.asyncio
async def test_member_allowed_agents_read(enforcer):
    """Members keep their non-management permissions (agents:read)."""
    svc = PermissionService()
    assert await svc.check(MEMBER, TENANT, "agents", "read") is True


@pytest.mark.asyncio
async def test_require_raises_on_denial(enforcer):
    """require() raises PermissionError when check() is False."""
    svc = PermissionService()
    with pytest.raises(PermissionError):
        await svc.require(MEMBER, TENANT, "users", "delete")


@pytest.mark.asyncio
async def test_require_returns_none_on_success(enforcer):
    """require() returns None (no raise) when check() is True."""
    svc = PermissionService()
    result = await svc.require(OWNER, TENANT, "users", "delete")
    assert result is None


@pytest.mark.asyncio
async def test_super_admin_require_bypasses(enforcer):
    """require() with super_admin never raises, even for member-like users."""
    svc = PermissionService()
    # MEMBER would normally be denied, but super_admin bypasses it.
    result = await svc.require(
        MEMBER, TENANT, "users", "delete", platform_role="super_admin"
    )
    assert result is None
