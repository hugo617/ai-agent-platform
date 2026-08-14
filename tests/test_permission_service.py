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
# API token scope gate (api-token-fine-grained-scopes).
#
# These exercise the contextvar-reading branch of check(): when a request is
# authenticated by a restricted ahp_ token, check() must enforce the token's
# scope set BEFORE the super_admin/hq_staff bypass. JWT requests (no contextvar)
# must be untouched.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_skips_scope_gate_when_contextvar_none(enforcer):
    """JWT path (no ahp_ token) → contextvar is None → gate skipped entirely.

    This is the zero-regression guarantee: every existing non-ahp_ request must
    behave exactly as before. We assert it by confirming a super_admin check
    still short-circuits, and that the gate doesn't accidentally deny.
    """
    from app.api.token_context import current_token_ctx

    # Sanity: the contextvar really is None outside a request.
    assert current_token_ctx.get() is None

    svc = PermissionService()
    # super_admin bypass must work without any token context.
    allowed = await svc.check(
        MEMBER, TENANT, "users", "delete", platform_role="super_admin"
    )
    assert allowed is True


@pytest.mark.asyncio
async def test_check_full_mode_skips_scope_gate(enforcer):
    """A full-mode token's contextvar is present but the gate is skipped.

    Full mode = behaviour-equivalent to legacy tokens (inherit grantor's current
    perms). The gate only runs for restricted mode.
    """
    from app.api.token_context import TokenCtx, current_token_ctx

    ctx = TokenCtx(token_id="t", scopes=[], scope_mode="full")
    token_set = current_token_ctx.set(ctx)
    try:
        svc = PermissionService()
        # Even with empty scopes, full mode lets the super_admin bypass run.
        allowed = await svc.check(
            MEMBER, TENANT, "users", "delete", platform_role="super_admin"
        )
        assert allowed is True
    finally:
        current_token_ctx.reset(token_set)


@pytest.mark.asyncio
async def test_check_restricted_gate_runs_before_super_admin_bypass(enforcer):
    """Hard constraint #3: restricted gate precedes the super_admin bypass.

    A super_admin check with a restricted token scoped AWAY from the action
    must return False — the gate denies before the bypass runs.
    """
    from app.api.token_context import TokenCtx, current_token_ctx

    ctx = TokenCtx(
        token_id="t", scopes=["agents:read"], scope_mode="restricted"
    )
    token_set = current_token_ctx.set(ctx)
    try:
        svc = PermissionService()
        # super_admin but scoped to agents:read only → users:delete denied.
        allowed = await svc.check(
            MEMBER, TENANT, "users", "delete", platform_role="super_admin"
        )
        assert allowed is False, "restricted gate must run before super_admin bypass"
    finally:
        current_token_ctx.reset(token_set)


@pytest.mark.asyncio
async def test_check_restricted_gate_cleared_after_reset(enforcer):
    """contextvar.reset() restores the default None — no leakage between calls.

    This is the per-request isolation guarantee: after a request's contextvar
    is reset, subsequent checks behave as JWT-path (no gate).
    """
    from app.api.token_context import TokenCtx, current_token_ctx

    ctx = TokenCtx(
        token_id="t", scopes=["agents:read"], scope_mode="restricted"
    )
    token_set = current_token_ctx.set(ctx)
    current_token_ctx.reset(token_set)

    svc = PermissionService()
    # After reset, super_admin bypass must work again (gate skipped).
    allowed = await svc.check(
        MEMBER, TENANT, "users", "delete", platform_role="super_admin"
    )
    assert allowed is True


# ---------------------------------------------------------------------------
# CHECK_RULES registry snapshot (perm-check-bypass slice 01).
#
# check()'s bypass chain is an explicit ordered registry: the tuple order IS
# the evaluation order (single source of truth). These snapshot tests pin the
# chain shape so a reordered/edited/extended rule table fails CI instead of
# silently shifting permission boundaries. The exhaustive invariant tests
# (obj-domain disjointness, applies() boundaries, verdict short-circuit) are
# in the slice-02 section right below.
# ---------------------------------------------------------------------------


def test_check_rules_order_snapshot():
    """Chain order pinned: scope gate first (the only DENY), then 4 bypasses."""
    from app.services.permission_service import CHECK_RULES

    assert [r.name for r in CHECK_RULES] == [
        "api_token_scope_gate",
        "super_admin",
        "hq_staff_read",
        "platform_writer",
        "group_admin_knowledge",
    ]
    # 闸门在链首(不变式:restricted token 即使 super_admin 签发也要先被
    # scope 收敛,这一顺序由下标 0 锁死)。
    assert CHECK_RULES[0].decision == "deny"


def test_check_rules_metadata_snapshot():
    """Every rule's declared applicability + verdict, pinned field by field."""
    from app.services.permission_service import CHECK_RULES

    by_name = {r.name: r for r in CHECK_RULES}
    assert set(by_name) == {
        "api_token_scope_gate",
        "super_admin",
        "hq_staff_read",
        "platform_writer",
        "group_admin_knowledge",
    }

    # ① API token scope gate:全域适用,restricted scope 之外的都不放行。
    assert by_name["api_token_scope_gate"].objs is None
    assert by_name["api_token_scope_gate"].acts is None
    assert by_name["api_token_scope_gate"].needs_db is False
    assert by_name["api_token_scope_gate"].decision == "deny"

    # ② super_admin:全域豁免。
    assert by_name["super_admin"].objs is None
    assert by_name["super_admin"].acts is None
    assert by_name["super_admin"].needs_db is False
    assert by_name["super_admin"].decision == "allow"

    # ③ hq_staff:全部 obj 的 read。
    assert by_name["hq_staff_read"].objs is None
    assert by_name["hq_staff_read"].acts == frozenset({"read"})
    assert by_name["hq_staff_read"].needs_db is False
    assert by_name["hq_staff_read"].decision == "allow"

    # ④ platform writer:仅 devices/bookings(跨租户写契约由 service body 执行)。
    assert by_name["platform_writer"].objs == frozenset({"devices", "bookings"})
    assert by_name["platform_writer"].acts is None
    assert by_name["platform_writer"].needs_db is False
    assert by_name["platform_writer"].decision == "allow"

    # ⑤ group_admin:仅 knowledge,且只有调用方传 db 才适用。
    assert by_name["group_admin_knowledge"].objs == frozenset({"knowledge"})
    assert by_name["group_admin_knowledge"].acts is None
    assert by_name["group_admin_knowledge"].needs_db is True
    assert by_name["group_admin_knowledge"].decision == "allow"


# ---------------------------------------------------------------------------
# CHECK_RULES exhaustive invariant tests (perm-check-bypass slice 02).
#
# The snapshot above pins the chain's SHAPE; these pin its SEMANTICS so an
# edit that keeps the metadata but shifts behaviour still fails CI:
#   * obj-domain disjointness — two ALLOW rules claiming the same obj would
#     silently decide which bypass wins by tuple order alone;
#   * applies() boundaries — applicability is computed from metadata and
#     NEVER by the predicate;
#   * verdict short-circuit — a hit rule returns its verdict without
#     consulting casbin; a miss continues down the chain to casbin.
# ---------------------------------------------------------------------------


def test_check_rules_allow_obj_domains_pairwise_disjoint():
    """不变式 4:ALLOW 型 rule 中声明 objs 的两两交集为 ∅。

    主守卫是上面的元数据快照(加规则/扩域必改快照);本断言是补充性
    保守约束 —— 捕获「两条声明 objs 的 ALLOW 规则意外重叠」这类未来
    friction。objs=None 的角色型全域豁免不属于 obj 域划分对象,由快照
    守卫,不在此列。
    """
    from itertools import combinations

    from app.services.permission_service import CHECK_RULES

    declared = [
        r.objs
        for r in CHECK_RULES
        if r.decision == "allow" and r.objs is not None
    ]
    # 数量快照:当前链上恰有两条(platform_writer / group_admin_knowledge)。
    # 若变为 1,combinations 退化为空断言(恒过);若 >2 也该有人审一眼。
    assert len(declared) == 2
    for a, b in combinations(declared, 2):
        assert a.isdisjoint(b), f"ALLOW rule obj domains overlap: {a} ∩ {b}"


def test_check_rule_applies_boundaries_never_call_predicate():
    """D5/不变式 5:适用域由元数据统一计算 —— 谓词零调用。

    用「被调用即炸」的哨兵谓词直测 applies():objs/acts/needs_db 任一
    不过 → False;全过 → True;全程不触谓词(声明式适用域,不是谓词
    自己的 if —— 那会把边界逻辑藏进谓词,穷举断言就测不到了)。
    """
    from app.services.permission_service import CheckContext, CheckRule

    async def _boom(_ctx):
        raise AssertionError(
            "applies() must decide applicability without calling the predicate"
        )

    rule = CheckRule(
        name="probe",
        objs=frozenset({"knowledge"}),
        acts=frozenset({"read"}),
        needs_db=True,
        decision="allow",
        predicate=_boom,
    )

    def ctx(**over):
        base = dict(
            user_id="u",
            tenant_id="t",
            obj="knowledge",
            act="read",
            platform_role=None,
            db=object(),  # 非 None 即可 —— applies() 只判空,不使用句柄
            token_ctx=None,
        )
        base.update(over)
        return CheckContext(**base)

    # needs_db rule 在 db=None → 不适用(安全降级:继续链落 casbin)。
    assert rule.applies(ctx(db=None)) is False
    # objs 不匹配 → 不适用。
    assert rule.applies(ctx(obj="devices")) is False
    # acts 不匹配 → 不适用。
    assert rule.applies(ctx(act="delete")) is False
    # 全匹配 → 适用(谓词仍零调用 —— applies() 只读元数据)。
    assert rule.applies(ctx()) is True


def test_group_admin_rule_degrades_safely_without_db():
    """不变式 5 落到真实注册表:⑤ group_admin_knowledge(needs_db=True)
    在 db=None 时 applies=False → 不触发 bypass → 落 casbin。与重构前
    「不传 db 的调用点从不走 group_admin 分支」逐字等价。
    """
    from app.services.permission_service import CHECK_RULES, CheckContext

    rule = next(r for r in CHECK_RULES if r.name == "group_admin_knowledge")
    assert rule.needs_db is True
    assert (
        rule.applies(
            CheckContext(
                user_id="u",
                tenant_id="t",
                obj="knowledge",
                act="read",
                platform_role=None,
                db=None,
                token_ctx=None,
            )
        )
        is False
    )


def _patch_casbin_to_explode(monkeypatch):
    """让任何 casbin 触达都炸 —— 证明 rule 命中短路后根本没走到兜底。"""

    def _explode():
        raise AssertionError("casbin must not be consulted when a rule hits")

    monkeypatch.setattr(casbin_mod, "get_enforcer", _explode)


@pytest.mark.asyncio
async def test_deny_rule_hit_short_circuits_false_before_casbin(monkeypatch):
    """verdict 短路(①DENY):restricted token 的 scope 之外的动作 →
    check 返回 False 且不触 casbin —— 即使链上后方的 super_admin 本可
    豁免(闸门在链首,不变式 3 的运行时证据)。
    """
    from app.api.token_context import TokenCtx, current_token_ctx

    _patch_casbin_to_explode(monkeypatch)
    token_set = current_token_ctx.set(
        TokenCtx(token_id="t", scopes=["agents:read"], scope_mode="restricted")
    )
    try:
        svc = PermissionService()
        denied = await svc.check(
            MEMBER, TENANT, "users", "delete", platform_role="super_admin"
        )
        assert denied is False
    finally:
        current_token_ctx.reset(token_set)


@pytest.mark.asyncio
async def test_allow_rule_hit_short_circuits_true_before_casbin(monkeypatch):
    """verdict 短路(②ALLOW):无 token 上下文 + super_admin → True 且
    不触 casbin(ALLOW 命中同样短路,不是「放行到 casbin 再判」)。
    """
    from app.api.token_context import current_token_ctx

    assert current_token_ctx.get() is None  # JWT 路径,闸门不适用
    _patch_casbin_to_explode(monkeypatch)
    svc = PermissionService()
    allowed = await svc.check(
        MEMBER, TENANT, "users", "delete", platform_role="super_admin"
    )
    assert allowed is True


@pytest.mark.asyncio
async def test_deny_rule_miss_continues_chain(enforcer):
    """①不命中的反向用例:restricted + scope 满足 → 不在闸门短路,链
    继续往后走。三段证据:

    - + super_admin → 落 ② ALLOW → True(链穿过了闸门到后续 rule);
    - + MEMBER(无 users 策略)→ 全链不命中 → casbin → False;
    - + OWNER(有 users:delete 策略)→ 全链不命中 → casbin → True。

    后两段真的触达 casbin(enforcer fixture 真种子),证明链走完了
    全程而非中途静默 False。
    """
    from app.api.token_context import TokenCtx, current_token_ctx

    token_set = current_token_ctx.set(
        TokenCtx(token_id="t", scopes=["users:delete"], scope_mode="restricted")
    )
    try:
        svc = PermissionService()
        # scope 满足(users:delete 直配)→ ①不命中 → ②命中 → True。
        bypassed = await svc.check(
            MEMBER, TENANT, "users", "delete", platform_role="super_admin"
        )
        assert bypassed is True
        # 无 bypass 可用 → 落 casbin 兜底:member 无策略 False…
        assert await svc.check(MEMBER, TENANT, "users", "delete") is False
        # …owner 有策略 True —— 两段都走了 casbin,链确实没断。
        assert await svc.check(OWNER, TENANT, "users", "delete") is True
    finally:
        current_token_ctx.reset(token_set)


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
        ("logs", "read"),
        ("knowledge", "read"), ("knowledge", "create"),
        ("knowledge", "delete"),
        # knowledge:distribute (knowledge-tiered slice 03): owner may push a
        # source doc to target stores. The catalogue integrity test pins this so
        # a future edit cannot silently drop the distribute perm.
        ("knowledge", "distribute"),
        # devices (devices-crud-ui slice 02): owner has full CRUD — mirrors
        # customers. The catalogue integrity test pins this so a future edit
        # cannot silently drop the devices perm set.
        ("devices", "read"), ("devices", "create"), ("devices", "update"),
        ("devices", "delete"),
        # bookings (device-booking slice 02): owner has full CRUD + cancel
        # (cancel reuses the delete perm — see bookings.py). Mirrors devices.
        ("bookings", "read"), ("bookings", "create"), ("bookings", "update"),
        ("bookings", "delete"),
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

# The business menus every full-trust role (owner/admin) sees. ``devices`` is
# added in devices-crud-ui slice 02 and ``bookings`` in device-booking slice 02,
# alongside the rest of the business surface.
_ALL_BUSINESS_MENUS = {
    "dashboard", "agents", "chat", "groups", "customers",
    "members", "users", "roles", "permissions", "settings", "knowledge",
    "devices", "bookings",
}


def test_default_menu_perms_owner_and_admin_see_all_business_menus():
    """owner + admin see all business menus; menu:tenants is NOT among them."""
    from app.services.permission_service import DEFAULT_MENU_PERMS

    assert set(DEFAULT_MENU_PERMS["owner"]) == _ALL_BUSINESS_MENUS
    assert set(DEFAULT_MENU_PERMS["admin"]) == _ALL_BUSINESS_MENUS
    # menu:tenants is platform-level — never seeded into any tenant role.
    assert "tenants" not in DEFAULT_MENU_PERMS["owner"]
    assert "tenants" not in DEFAULT_MENU_PERMS["admin"]
    assert "tenants" not in DEFAULT_MENU_PERMS["member"]


def test_default_menu_perms_member_only_sees_business_menus():
    """member sees only the business menus (no management/settings menus)."""
    from app.services.permission_service import DEFAULT_MENU_PERMS

    member_menus = set(DEFAULT_MENU_PERMS["member"])
    assert member_menus == {
        "dashboard", "agents", "chat", "groups", "customers", "knowledge",
        # devices (devices-crud-ui slice 02): member sees the nav entry — the
        # page itself is read-only via api perms; the menu just unlocks entry.
        "devices",
        # bookings (device-booking slice 02): member sees the nav entry — the
        # page itself is read-only via api perms; the menu just unlocks entry.
        "bookings",
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
