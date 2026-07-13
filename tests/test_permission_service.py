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


# ---------------------------------------------------------------------------
# Unified catalogue integrity (permission-unified-model).
#
# The default perm lists are the single source of truth that both the casbin
# seed and the SCD2 seed read from. These tests pin the catalogue shape so a
# future edit can't silently drop a route-guarded action or re-coarsen the
# settings/api_tokens split.
# ---------------------------------------------------------------------------


def test_default_owner_perms_cover_full_catalogue():
    """owner holds every action in the unified catalogue (full-trust role)."""
    from app.services.permission_service import DEFAULT_OWNER_PERMS

    expected = {
        ("agents", "read"), ("agents", "create"), ("agents", "update"),
        ("agents", "delete"), ("agents", "export"),
        ("conversations", "read"), ("conversations", "create"),
        ("conversations", "update"), ("conversations", "delete"),
        ("conversations", "chat"),
        ("users", "read"), ("users", "create"), ("users", "update"), ("users", "delete"),
        ("roles", "read"), ("roles", "create"), ("roles", "update"), ("roles", "delete"),
        ("settings", "read"), ("settings", "update"),
        ("api_tokens", "read"), ("api_tokens", "create"), ("api_tokens", "delete"),
        ("customers", "read"), ("customers", "create"), ("customers", "update"),
        ("customers", "delete"), ("customers", "export"),
        ("wallet", "read"), ("wallet", "update"),
        ("billing", "read"),
    }
    assert set(DEFAULT_OWNER_PERMS) == expected


def test_settings_and_api_tokens_manage_was_split():
    """The coarse ``manage`` action is gone from settings/api_tokens.

    It was split into read/update (settings) and read/create/delete (api_tokens)
    so the matrix can express read-only settings or issue-but-not-revoke tokens.
    """
    from app.services.permission_service import (
        DEFAULT_ADMIN_PERMS,
        DEFAULT_OWNER_PERMS,
    )

    for perms in (DEFAULT_OWNER_PERMS, DEFAULT_ADMIN_PERMS):
        pairs = set(perms)
        assert ("settings", "manage") not in pairs
        assert ("api_tokens", "manage") not in pairs
        assert ("settings", "read") in pairs
        assert ("settings", "update") in pairs
        assert ("api_tokens", "read") in pairs
        assert ("api_tokens", "create") in pairs
        assert ("api_tokens", "delete") in pairs


def test_member_perms_have_no_settings_or_api_tokens():
    """member is read-only and never touches settings/api_tokens."""
    from app.services.permission_service import DEFAULT_MEMBER_PERMS

    for obj, _act in DEFAULT_MEMBER_PERMS:
        assert obj not in {"settings", "api_tokens"}


def test_cn_label_maps_cover_catalogue():
    """OBJ_CN/ACT_CN cover every object/action in the default catalogue."""
    from app.services.permission_service import (
        ACT_CN,
        DEFAULT_OWNER_PERMS,
        OBJ_CN,
    )

    objs = {obj for obj, _ in DEFAULT_OWNER_PERMS}
    acts = {act for _, act in DEFAULT_OWNER_PERMS}
    assert objs <= set(OBJ_CN), f"OBJ_CN missing: {objs - set(OBJ_CN)}"
    assert acts <= set(ACT_CN), f"ACT_CN missing: {acts - set(ACT_CN)}"


# ---------------------------------------------------------------------------
# Menu permission catalogue (permission-menu-view).
#
# DEFAULT_MENU_PERMS is the single source of truth for which nav items each
# system role sees. These tests pin the shape so a future edit can't silently
# hide a business menu from members or leak a management menu to them.
# ---------------------------------------------------------------------------

# The 10 business menus every full-trust role (owner/admin) sees.
_ALL_BUSINESS_MENUS = {
    "dashboard", "agents", "chat", "groups", "customers",
    "members", "users", "roles", "permissions", "settings",
}


def test_default_menu_perms_owner_and_admin_see_all_business_menus():
    """owner + admin see all 10 business menus; menu:tenants is NOT among them."""
    from app.services.permission_service import DEFAULT_MENU_PERMS

    assert set(DEFAULT_MENU_PERMS["owner"]) == _ALL_BUSINESS_MENUS
    assert set(DEFAULT_MENU_PERMS["admin"]) == _ALL_BUSINESS_MENUS
    # menu:tenants is platform-level — never seeded into any tenant role.
    assert "tenants" not in DEFAULT_MENU_PERMS["owner"]
    assert "tenants" not in DEFAULT_MENU_PERMS["admin"]
    assert "tenants" not in DEFAULT_MENU_PERMS["member"]


def test_default_menu_perms_member_only_sees_business_menus():
    """member sees only the 5 business menus (no management/settings menus)."""
    from app.services.permission_service import DEFAULT_MENU_PERMS

    member_menus = set(DEFAULT_MENU_PERMS["member"])
    assert member_menus == {
        "dashboard", "agents", "chat", "groups", "customers"
    }
    # management menus hidden from member
    assert member_menus.isdisjoint(
        {"members", "users", "roles", "permissions", "settings"}
    )


def test_menu_cn_covers_all_seeded_menu_codes():
    """MENU_CN has a Chinese label for every menu code in DEFAULT_MENU_PERMS."""
    from app.services.permission_service import DEFAULT_MENU_PERMS, MENU_CN

    all_codes: set[str] = set()
    for codes in DEFAULT_MENU_PERMS.values():
        all_codes.update(codes)
    missing = all_codes - set(MENU_CN)
    assert not missing, f"MENU_CN missing labels for: {missing}"
