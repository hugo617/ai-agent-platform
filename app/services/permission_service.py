"""Permission service — the single wrapper around pycasbin.

This is where casbin's synchronous API is bridged into our async service layer
via ``run_in_threadpool``. Every permission check in the app goes through here,
keeping casbin usage in exactly one place (easy to test, easy to swap).

------------------ RBAC 双层职责「宪法」(改权限前必读) ------------------

    历史回溯看 SCD2 表;实时鉴权看 casbin;SCD2 当前态是 casbin 的同步源。

两张 SCD2 表(``user_tenants`` / ``role_permissions``)用 ``valid_from`` /
``valid_to`` 记录时间维度(``valid_to IS NULL`` = 当前生效)。casbin 永远只回答
「现在能不能做」,不存历史 —— 两者解耦。

写路径(所有改权限的入口都必须走这条链,业务代码绝不直接操作 valid_from/valid_to):

    管理员改权限
       ↓ 写 SCD2 表(关旧行 valid_to=now + 插新行 valid_to=NULL)   ← 历史在这里
       ↓ 用 SCD2 当前态同步 casbin                                 ← 实时鉴权用这个
       ↓ 写 system_logs(谁、何时、从 X 改成 Y)                    ← 审计底座

具体落点:
- 改成员角色 → ``UserTenantRepository.assign_role`` → ``set_role_for_user_in_domain``
- 改角色权限集 → ``RolePermissionRepository.grant/revoke`` → ``sync_role_permissions_to_casbin``
- 任意时间点还原看 SCD2 表的 ``member_role_at`` / ``permissions_at``

设计背景:``docs/auth-history-scd2-plan.md``;
``项目指南/02-后端架构/06-权限模型RBAC.md`` 的「权限变更的历史回溯(SCD2)」节。
"""

from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.token_context import current_token_ctx
from app.core import casbin_enforcer as _casbin_mod
from app.models.rbac import Permission, Role
from app.repositories.rbac import RolePermissionRepository, RoleRepository
from app.schemas.rbac import PermissionItem, PermissionMatrix, RoleRead


class PermissionService:
    """Encapsulates all casbin operations for multi-tenant RBAC.

    Reads the enforcer + lock via the module (``_casbin_mod``) rather than a
    direct import so tests can monkeypatch ``app.core.casbin_enforcer.get_enforcer``
    and have the change take effect here.
    """

    # ---------- enforcement ----------
    async def check(
        self,
        user_id: str,
        tenant_id: str,
        obj: str,
        act: str,
        platform_role: str | None = None,
    ) -> bool:
        """Return True if ``user_id`` may perform ``act`` on ``obj`` in ``tenant_id`.

        Platform super admins bypass all permission checks. ``hq_staff``(总部
        业务员)is a cross-tenant read-only viewer: any ``read`` action is allowed,
        while writes fall through to the normal casbin path (no tenant-scoped
        policy → 403), so hq_staff is effectively read-only unless a store
        explicitly granted it a role.

        API token scope gate (api-token-fine-grained-scopes): when the request
        is authenticated by an ``ahp_`` token in ``restricted`` mode, the token
        may only do what its ``scopes`` allow — and the gate runs BEFORE the
        super_admin / hq_staff bypass, so even a super_admin-issued restricted
        token is bound by its scopes. Writes (update/delete/create) and
        conversational/export actions imply the ``read`` on the same object, so
        a token scoped to ``customers:update`` automatically satisfies a
        ``customers:read`` check. ``scope_mode="full"`` and the JWT path
        (``current_token_ctx is None``) skip this gate entirely.
        """
        # API token scope gate. Runs FIRST (before any bypass) so restricted
        # tokens — including super_admin-issued ones — stay bounded.
        ctx = current_token_ctx.get()
        if ctx is not None and ctx.scope_mode == "restricted":
            # The required scope set for this (obj, act). A token passes if it
            # holds ANY of these. The semantics (hard constraint #5):
            #   * Direct match: ``<obj>:<act>`` or the legacy ``<obj>:manage``.
            #   * Write implies read: a token scoped to ``<obj>:update`` can
            #     also do ``<obj>:read`` (someone who can edit can obviously
            #     view). Symmetrically, when the CALLER asks for a write act,
            #     the gate also accepts the explicit ``<obj>:read`` scope on
            #     the token (though that direction is unusual — it would let
            #     a read-only token perform writes, which we DON'T want, so
            #     it's NOT included; only the write→read direction holds).
            required = {f"{obj}:{act}", f"{obj}:manage"}
            # Read actions are also satisfied by any write/conversational/
            # export scope on the same object (write implies read).
            if act == "read":
                required |= {
                    f"{obj}:{w}" for w in ("create", "update", "delete", "chat", "export")
                }
            if not (set(ctx.scopes) & required):
                return False

        if platform_role == "super_admin":
            return True
        if platform_role == "hq_staff" and act == "read":
            return True

        def _do() -> bool:
            e = _casbin_mod.get_enforcer()
            with _casbin_mod.enforcer_lock():
                return bool(e.enforce(user_id, tenant_id, obj, act))

        return await run_in_threadpool(_do)

    async def require(
        self,
        user_id: str,
        tenant_id: str,
        obj: str,
        act: str,
        platform_role: str | None = None,
    ):
        """Convenience: raise ``PermissionError`` if not allowed.

        Kept as a coroutine so callers can ``await service.require(...)``.
        """

        if not await self.check(user_id, tenant_id, obj, act, platform_role=platform_role):
            raise PermissionError(
                f"无权限：{user_id} 不能在租户 {tenant_id} 中对 {obj} 执行 {act}"
            )

    # ---------- roles ----------
    async def add_role_for_user_in_domain(self, user_id: str, role: str, tenant_id: str) -> None:
        def _do() -> None:
            e = _casbin_mod.get_enforcer()
            with _casbin_mod.enforcer_lock():
                e.add_role_for_user_in_domain(user_id, role, tenant_id)

        await run_in_threadpool(_do)

    async def set_role_for_user_in_domain(
        self, user_id: str, role: str, tenant_id: str
    ) -> None:
        """Replace the user's role in a domain (drop prior roles, add the new one).

        Used when an admin changes a member's role: casbin's grouping policy is
        synchronised so the new role takes effect immediately.
        """

        def _do() -> None:
            e = _casbin_mod.get_enforcer()
            with _casbin_mod.enforcer_lock():
                for old in e.get_roles_for_user_in_domain(user_id, tenant_id):
                    e.delete_roles_for_user_in_domain(user_id, old, tenant_id)
                e.add_role_for_user_in_domain(user_id, role, tenant_id)

        await run_in_threadpool(_do)

    async def remove_user_from_tenant(self, user_id: str, tenant_id: str) -> None:
        """Strip every role a user holds in a domain (removes their access)."""

        def _do() -> None:
            e = _casbin_mod.get_enforcer()
            with _casbin_mod.enforcer_lock():
                for old in e.get_roles_for_user_in_domain(user_id, tenant_id):
                    e.delete_roles_for_user_in_domain(user_id, old, tenant_id)

        await run_in_threadpool(_do)

    async def get_roles_for_user_in_domain(self, user_id: str, tenant_id: str) -> list[str]:
        def _do() -> list[str]:
            e = _casbin_mod.get_enforcer()
            with _casbin_mod.enforcer_lock():
                return list(e.get_roles_for_user_in_domain(user_id, tenant_id))

        return await run_in_threadpool(_do)

    # Backs the ``permissions`` array on ``/auth/me`` (drives the frontend's
    # menu/button visibility). Returns casbin's flattened policy pairs.
    async def get_implicit_permissions_for_user(
        self, user_id: str, tenant_id: str
    ) -> list[list[str]]:
        def _do() -> list[list[str]]:
            e = _casbin_mod.get_enforcer()
            with _casbin_mod.enforcer_lock():
                return e.get_implicit_permissions_for_user(user_id, tenant_id)

        return await run_in_threadpool(_do)

    # ---------- policies ----------
    async def add_policy(self, sub: str, dom: str, obj: str, act: str) -> None:
        def _do() -> None:
            e = _casbin_mod.get_enforcer()
            with _casbin_mod.enforcer_lock():
                e.add_policy(sub, dom, obj, act)

        await run_in_threadpool(_do)

    async def seed_tenant_defaults(
        self,
        tenant_id: str,
        owner_user_id: str,
        db: AsyncSession | None = None,
    ) -> None:
        """Bootstrap a brand-new tenant with the owner role + default policies.

        Three things happen, kept in lockstep (the constitution: SCD2 current
        state is the casbin sync source):

          1. casbin: the owner is granted the ``owner`` role, and every
             default ``(role, obj, act)`` policy is added.
          2. ``permissions`` rows: one catalogue row per ``(obj, act)`` unit
             (``code == "<obj>:<act>"``), browsable in the admin UI.
          3. ``role_permissions`` SCD2 rows (only when ``db`` is given): each
             default grant is written as a current-state row, so the SCD2
             history source and casbin agree from day one.

        ``db`` is optional for backward compatibility (the casbin-only path used
        by tests); when omitted the SCD2 tables are not seeded.
        """
        await self.add_role_for_user_in_domain(owner_user_id, "owner", tenant_id)

        # Pre-resolve role ids (created by RbacService.seed_defaults) and
        # upsert the permission catalogue. Idempotent: grant() no-ops dupes.
        rp_repo = RolePermissionRepository(db) if db is not None else None
        role_ids: dict[str, str] = {}
        perm_ids: dict[str, str] = {}  # keyed by "<obj>:<act>"
        if db is not None:
            role_ids = await self._role_ids_by_code(db, tenant_id)

        for role_code, perms in (
            ("owner", DEFAULT_OWNER_PERMS),
            ("admin", DEFAULT_ADMIN_PERMS),
            ("member", DEFAULT_MEMBER_PERMS),
        ):
            for obj, act in perms:
                await self.add_policy(role_code, tenant_id, obj, act)
                if rp_repo is not None:
                    key = f"{obj}:{act}"
                    pid = perm_ids.get(key)
                    if pid is None:
                        pid = await self._upsert_permission(db, tenant_id, obj, act)
                        perm_ids[key] = pid
                    rid = role_ids.get(role_code)
                    if rid:
                        await rp_repo.grant(rid, pid, tenant_id)

        # Menu permissions (type="menu") — UX-layer menu/page visibility. Same
        # grant path as api perms (casbin policy + SCD2 + catalogue row) so the
        # matrix can grant/revoke them uniformly. ``menu:tenants`` is platform-
        # level and intentionally NOT seeded here — super_admin shows it via
        # bypass (see DEFAULT_MENU_PERMS docstring).
        for role_code, menu_codes in DEFAULT_MENU_PERMS.items():
            for menu_code in menu_codes:
                await self.add_policy(role_code, tenant_id, "menu", menu_code)
                if rp_repo is not None:
                    key = f"menu:{menu_code}"
                    pid = perm_ids.get(key)
                    if pid is None:
                        pid = await self._upsert_permission(
                            db, tenant_id, "menu", menu_code, perm_type="menu"
                        )
                        perm_ids[key] = pid
                    rid = role_ids.get(role_code)
                    if rid:
                        await rp_repo.grant(rid, pid, tenant_id)

    async def sync_role_permissions_to_casbin(
        self, db: AsyncSession, role_id: str, tenant_id: str
    ) -> None:
        """Rebuild a role's casbin ``(obj, act)`` policies from its SCD2 current state.

        Called after ``grant`` / ``revoke`` mutate ``role_permissions``: the SCD2
        current rows are the source of truth, and casbin is resynchronised so the
        change takes effect immediately for every user holding this role (the
        ``g`` grouping is untouched — only the role's ``p`` policies change).
        """
        role_code = await self._role_code_for(db, role_id, tenant_id)
        if role_code is None:
            return
        active = await RolePermissionRepository(db).current_permissions(role_id, tenant_id)
        # Resolve each active grant to its (obj, act) via the permission row.
        pairs: list[tuple[str, str]] = []
        for row in active:
            obj, act = await self._permission_obj_act(db, row.permission_id)
            if obj:
                pairs.append((obj, act))

        def _do() -> None:
            e = _casbin_mod.get_enforcer()
            with _casbin_mod.enforcer_lock():
                # Drop every existing (role, tenant, *, *) policy for this role.
                for pol in list(e.get_filtered_policy(0, role_code, tenant_id)):
                    e.remove_policy(pol)
                # Re-add from the SCD2 current state.
                for obj, act in sorted(set(pairs)):
                    e.add_policy(role_code, tenant_id, obj, act)

        await run_in_threadpool(_do)

    # ----------------------------------------------------- aggregated reads

    async def get_catalogue(
        self,
        db: AsyncSession,
        tenant_id: str,
        perm_type: str | None = None,
    ) -> list[PermissionItem]:
        """All permission catalogue items for a tenant.

        Source: the ``permissions`` rows upserted by ``seed_tenant_defaults`` /
        ``grant`` (one row per ``<obj>:<act>`` unit). Tenant scoping happens in
        the query (is_deleted=False), per the multi-tenant rule.

        ``perm_type`` optionally filters by ``Permission.type`` (``"api"`` or
        ``"menu"``); when None (default) all types are returned.

        Ordered by ``code`` so the matrix renders in a stable order without the
        frontend having to keep its own sort table.
        """
        stmt = select(Permission).where(
            Permission.tenant_id == tenant_id,
            Permission.is_deleted.is_(False),
        )
        if perm_type is not None:
            stmt = stmt.where(Permission.type == perm_type)
        rows = (await db.execute(stmt.order_by(Permission.code))).scalars().all()
        items: list[PermissionItem] = []
        for p in rows:
            obj, act = p.code.split(":", 1) if ":" in p.code else (p.code, "")
            if p.type == "menu":
                # menu perms: obj is always "menu"; the act (e.g. "agents")
                # should be labelled via MENU_CN, not ACT_CN.
                act_label = MENU_CN.get(act, act)
            else:
                act_label = ACT_CN.get(act, act)
            items.append(
                PermissionItem(
                    id=p.id,
                    code=p.code,
                    name=p.name,
                    obj=obj,
                    act=act,
                    obj_label=OBJ_CN.get(obj, obj),
                    act_label=act_label,
                    type=p.type,
                )
            )
        return items

    async def get_matrix(
        self, db: AsyncSession, tenant_id: str
    ) -> PermissionMatrix:
        """Aggregate the current role × permission matrix for a tenant.

        The granted state comes from ``current_permissions`` (SCD2 current rows);
        the matrix is True for every ``(role, permission)`` pair whose active
        grant row exists. Tenant scoping lives in the repositories.
        """
        roles = await RoleRepository(db).list_for_tenant(tenant_id)
        permissions = await self.get_catalogue(db, tenant_id)

        rp_repo = RolePermissionRepository(db)
        matrix: dict[str, dict[str, bool]] = {}
        for role in roles:
            active = await rp_repo.current_permissions(role.id, tenant_id)
            granted_ids = {row.permission_id for row in active}
            matrix[role.code] = {p.code: p.id in granted_ids for p in permissions}

        return PermissionMatrix(
            roles=[RoleRead.model_validate(r) for r in roles],
            permissions=permissions,
            matrix=matrix,
        )

    # ----------------------------------------------------------- seed helpers

    async def _upsert_permission(
        self,
        db: AsyncSession,
        tenant_id: str,
        obj: str,
        act: str,
        perm_type: str = "api",
    ) -> str:
        """Insert a catalogue Permission row for ``(obj, act)`` if absent.

        ``code == "<obj>:<act>"`` (e.g. ``"agents:delete"`` or ``"menu:agents"``)
        so each row is a single permission unit and role_permissions can point
        at exactly the pair that casbin reasons about. Idempotent across
        re-seeds. The ``name`` is a Chinese friendly label (e.g. ``"智能体-查看"``
        for api perms, ``"菜单-智能体"`` for menu perms) sourced from
        ``OBJ_CN``/``ACT_CN``/``MENU_CN`` so the catalogue is self-describing.

        ``perm_type`` selects the row's ``type`` column: ``"api"`` (the default,
        real backend authorization units like ``customers:read``) or
        ``"menu"`` (UX-layer menu visibility like ``menu:agents`` — see the
        ``DEFAULT_MENU_PERMS`` block below). Callers that grant ``("menu",
        <code>)`` pass ``perm_type="menu"`` explicitly (see ``grant_permission``).
        """
        code = f"{obj}:{act}"
        existing = (
            await db.execute(
                select(Permission).where(
                    Permission.tenant_id == tenant_id,
                    Permission.code == code,
                    Permission.is_deleted.is_(False),
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing.id
        if perm_type == "menu":
            # menu perms use MENU_CN for the act part ("菜单-智能体").
            name = f"{OBJ_CN.get(obj, obj)}-{MENU_CN.get(act, act)}"
        else:
            name = f"{OBJ_CN.get(obj, obj)}-{ACT_CN.get(act, act)}"
        perm = Permission(
            name=name,
            code=code,
            tenant_id=tenant_id,
            type=perm_type,
            is_system=True,
        )
        db.add(perm)
        await db.flush()
        return perm.id

    async def _permission_obj_act(
        self, db: AsyncSession, permission_id: str
    ) -> tuple[str, str]:
        """Resolve a permission's (obj, act) by splitting its ``code``."""
        code = (
            await db.execute(
                select(Permission.code).where(Permission.id == permission_id)
            )
        ).scalar_one_or_none()
        if not code or ":" not in code:
            return ("", "")
        obj, act = code.split(":", 1)
        return (obj, act)

    async def _role_ids_by_code(
        self, db: AsyncSession, tenant_id: str
    ) -> dict[str, str]:
        rows = (
            await db.execute(
                select(Role.code, Role.id).where(
                    Role.tenant_id == tenant_id,
                    Role.is_deleted.is_(False),
                )
            )
        ).all()
        return {code: rid for code, rid in rows}

    async def _role_code_for(
        self, db: AsyncSession, role_id: str, tenant_id: str
    ) -> str | None:
        return (
            await db.execute(
                select(Role.code).where(
                    Role.id == role_id,
                    Role.tenant_id == tenant_id,
                    Role.is_deleted.is_(False),
                )
            )
        ).scalar_one_or_none()


# ---------------------------------------------------------------------------
# Default permission matrix — the single source of truth for both the casbin
# seed and the role_permissions SCD2 seed. Keep in sync with the test fixtures
# (tests/conftest.py _make_casbin) and the doc table in
# 项目指南/02-后端架构/06-权限模型RBAC.md.
#
# Catalogue design (permission-unified-model, 2026-07-13):
#   * ``settings``/``api_tokens`` used to carry only a coarse ``manage`` action;
#     now split into read/update (settings) and read/create/delete (api_tokens)
#     so the matrix can express "read-only settings" or "issue but not revoke".
#   * ``conversations:delete``/``conversations:update`` are now seeded for owner
#     (they already had route guards but no role held them).
#   * ``agents:export``/``customers:export`` are reserved — no route yet, but
#     seeded so the matrix shows them and future export endpoints just work.
#   * ``export`` is reserved (no route yet) but seeded for owner/admin so the
#     matrix exposes the slot — grant/revoke keeps casbin in sync.
# ---------------------------------------------------------------------------
DEFAULT_OWNER_PERMS: list[tuple[str, str]] = [
    ("agents", "read"), ("agents", "create"), ("agents", "update"), ("agents", "delete"),
    ("agents", "export"),
    ("conversations", "read"), ("conversations", "create"), ("conversations", "update"),
    ("conversations", "delete"), ("conversations", "chat"),
    ("users", "read"), ("users", "create"), ("users", "update"), ("users", "delete"),
    ("roles", "read"), ("roles", "create"), ("roles", "update"), ("roles", "delete"),
    ("settings", "read"), ("settings", "update"),
    ("api_tokens", "read"), ("api_tokens", "create"), ("api_tokens", "delete"),
    ("customers", "read"), ("customers", "create"), ("customers", "update"), ("customers", "delete"),
    ("customers", "export"),
    ("wallet", "read"), ("wallet", "update"),
    ("billing", "read"),
    ("logs", "read"),
    # knowledge: no "update" act — documents have no edit path (delete +
    # recreate), so only read/create/delete are seeded. See knowledge_service.
    ("knowledge", "read"), ("knowledge", "create"), ("knowledge", "delete"),
    # devices (devices-crud-ui slice 02): owner full CRUD — mirrors customers.
    ("devices", "read"), ("devices", "create"), ("devices", "update"), ("devices", "delete"),
]
DEFAULT_ADMIN_PERMS: list[tuple[str, str]] = [
    ("agents", "read"), ("agents", "create"), ("agents", "update"), ("agents", "export"),
    ("conversations", "read"), ("conversations", "create"), ("conversations", "chat"),
    ("users", "read"), ("users", "create"), ("users", "update"),
    ("roles", "read"),
    ("settings", "read"), ("settings", "update"),
    ("api_tokens", "read"), ("api_tokens", "create"), ("api_tokens", "delete"),
    ("customers", "read"), ("customers", "create"), ("customers", "update"), ("customers", "export"),
    ("wallet", "read"), ("wallet", "update"),
    ("billing", "read"),
    ("logs", "read"),
    ("knowledge", "read"), ("knowledge", "create"),
    # devices (devices-crud-ui slice 02): admin writes, NO delete — mirrors
    # the customer convention (admin cannot delete business records).
    ("devices", "read"), ("devices", "create"), ("devices", "update"),
]
DEFAULT_MEMBER_PERMS: list[tuple[str, str]] = [
    ("agents", "read"),
    ("conversations", "read"), ("conversations", "create"), ("conversations", "chat"),
    ("roles", "read"),
    ("customers", "read"),
    ("billing", "read"),
    ("knowledge", "read"),
    # devices (devices-crud-ui slice 02): member read-only — mirrors customers.
    ("devices", "read"),
]

# ---------------------------------------------------------------------------
# Menu permissions (type="menu") — UX-layer menu/page visibility. These are the
# "can I see this nav item / enter this route" codes, as opposed to api perms
# which are the real backend authorization ("can I actually call this endpoint").
# Menu perms are the UX shadow of api perms: the frontend reads them via
# /me.permissions to decide nav/route visibility; the backend never enforces
# them (require_permission keeps checking api perms). A role may hold
# menu:customers without customers:read (sees the menu, gets 403 on the page) or
# vice versa — independent, though usually granted together.
#
# ``menu:tenants`` is platform-level (super_admin only) and intentionally NOT in
# any role's list: it is never seeded into a tenant, and the frontend shows it
# purely on platform_role === "super_admin" (super_admin bypasses everything, so
# it has no need for a menu perm row).
# ---------------------------------------------------------------------------
DEFAULT_MENU_PERMS: dict[str, list[str]] = {
    "owner": [
        "dashboard", "agents", "chat", "groups", "customers",
        "members", "users", "roles", "permissions", "settings", "knowledge",
        # devices (devices-crud-ui slice 02): owner sees the devices nav entry.
        "devices",
    ],
    "admin": [
        "dashboard", "agents", "chat", "groups", "customers",
        "members", "users", "roles", "permissions", "settings", "knowledge",
        # devices (devices-crud-ui slice 02): admin sees the devices nav entry.
        "devices",
    ],
    "member": [
        "dashboard", "agents", "chat", "groups", "customers", "knowledge",
        # devices (devices-crud-ui slice 02): member sees the devices nav entry
        # (page itself is read-only via api perms; the menu just unlocks entry).
        "devices",
    ],
}

# ---------------------------------------------------------------------------
# Chinese display labels — shared by ``_upsert_permission`` (seed writes them
# into Permission.name) and ``get_catalogue`` (returns them as obj_label /
# act_label). This is the single source of truth for friendly names so the
# frontend never hardcodes them again (removes the OBJ_LABELS/ACT_ORDER drift).
# ---------------------------------------------------------------------------
OBJ_CN: dict[str, str] = {
    "agents": "智能体",
    "conversations": "对话",
    "users": "用户",
    "roles": "角色",
    "settings": "设置",
    "api_tokens": "API令牌",
    "customers": "客户",
    "wallet": "钱包",
    "billing": "计费",
    "logs": "审计日志",
    "knowledge": "知识库",
    # devices (devices-crud-ui slice 02): catalogue label for the new perm set.
    "devices": "设备",
    "menu": "菜单",
}
ACT_CN: dict[str, str] = {
    "read": "查看",
    "create": "创建",
    "update": "编辑",
    "delete": "删除",
    "chat": "对话",
    "export": "导出",
    "manage": "管理",  # legacy, kept for backfill of old rows
}

# Chinese labels for the *menu code* part of a menu permission (the ``act`` of
# ``menu:<code>``). Used by ``_upsert_permission`` so menu perms get friendly
# names like "菜单-智能体" instead of "菜单-agents". Keys mirror the act half of
# the codes in ``DEFAULT_MENU_PERMS`` (and the frontend NAV_ITEMS paths).
MENU_CN: dict[str, str] = {
    "dashboard": "概览",
    "agents": "智能体",
    "chat": "对话",
    "groups": "组织",
    "customers": "客户",
    "members": "成员",
    "users": "用户",
    "roles": "角色",
    "permissions": "权限矩阵",
    "settings": "设置",
    "tenants": "门店",
    "knowledge": "知识库",
    # devices (devices-crud-ui slice 02): menu-code label for the new entry.
    "devices": "设备",
}


permission_service = PermissionService()


# Platform roles that can read across tenants (HQ viewers). Service layers use
# this to pick the cross-tenant query branch instead of hardcoding ``== "super_admin"``.
# Writes for hq_staff still fall through to casbin (→ 403 without a store role),
# so this helper is about *read* scope only.
CROSS_TENANT_VIEWER_ROLES: tuple[str, ...] = ("super_admin", "hq_staff")


def is_cross_tenant_viewer(platform_role: str | None) -> bool:
    """True if the role grants cross-tenant read access (super_admin or hq_staff)."""
    return platform_role in CROSS_TENANT_VIEWER_ROLES


# ---------------------------------------------------------------------------
# One-shot backfill for the devices permission set (devices-crud-ui slice 02).
#
# Why this lives here instead of in scripts/: the same path runs as a one-shot
# data migration (scripts/backfill_devices_perms.py) AND from the slice-02 test
# suite (tests/test_devices_api.py K chapter). Keeping the per-tenant logic in
# the service module means the test exercises the real production code path —
# the script is a thin async main() wrapper.
#
# Scope guardrail: this function ONLY touches ``(obj="devices", *)`` and
# ``(obj="menu", act="devices")`` rows. It never grants/revokes anything else,
# so re-running it after other permission work is always safe (idempotent and
# side-effect-bounded).
# ---------------------------------------------------------------------------
async def backfill_devices_perms_for_existing_tenants(db: AsyncSession) -> dict[str, int]:
    """Grant ``devices``/``menu:devices`` perms to every tenant's system roles.

    Walks the ``tenants`` table and, for each tenant, ensures owner/admin/member
    hold the devices-related entries from ``DEFAULT_*_PERMS`` plus the
    ``menu:devices`` entry from ``DEFAULT_MENU_PERMS``. Existing tenants created
    before devices-crud-ui shipped are missing these; new tenants get them via
    ``seed_tenant_defaults`` automatically.

    Idempotent at three layers:
      * ``PermissionService._upsert_permission`` returns the existing row id
        when the catalogue already has ``devices:<act>`` / ``menu:devices``;
      * ``RolePermissionRepository.grant`` no-ops on an already-active grant;
      * ``sync_role_permissions_to_casbin`` is a full rebuild from SCD2 current
        state, so re-syncing converges.

    Returns a stats dict (tenant_id → count of newly-granted role×permission
    pairs) for the one-shot script's report. The count is "rows newly added by
    this run" — re-running on an already-backfilled tenant yields 0 per pair.

    Only ``devices``/``menu:devices`` are touched. Other permissions
    (``customers:read``, ``wallet:read``, etc.) are left untouched, which is
    the K6 contract in the plan.
    """
    from app.models.tenant import Tenant  # local import to avoid module cycles
    from app.repositories.rbac import RolePermissionRepository

    service = PermissionService()
    rp_repo = RolePermissionRepository(db)

    # Snapshot existing (role_id, permission_id) active grants once per tenant
    # so we can count *new* grants without a second round-trip per pair. The
    # SCD2 "active" predicate (valid_to IS NULL) lives in the repository.
    tenants = (await db.execute(select(Tenant))).scalars().all()
    stats: dict[str, int] = {}

    for tenant in tenants:
        role_ids = await service._role_ids_by_code(db, tenant.id)
        # Pre-collect existing active grants per role (permission_id set) so
        # we can tell "new" from "already granted" without N round-trips.
        existing_per_role: dict[str, set[str]] = {}
        for role_code, rid in role_ids.items():
            active = await rp_repo.current_permissions(rid, tenant.id)
            existing_per_role[role_code] = {row.permission_id for row in active}

        new_count = 0

        # --- api perms: only (obj="devices", *) rows ------------------------
        for role_code, perms in (
            ("owner", DEFAULT_OWNER_PERMS),
            ("admin", DEFAULT_ADMIN_PERMS),
            ("member", DEFAULT_MEMBER_PERMS),
        ):
            rid = role_ids.get(role_code)
            if rid is None:
                # Tenant doesn't have this system role (rare: member never
                # created). Nothing to grant — skip cleanly.
                continue
            for obj, act in perms:
                if obj != "devices":
                    continue  # scope guardrail — never touch non-devices perms
                pid = await service._upsert_permission(db, tenant.id, obj, act)
                if pid not in existing_per_role[role_code]:
                    await rp_repo.grant(rid, pid, tenant.id)
                    new_count += 1
            # Casbin sync is per-role (sync_role_permissions_to_casbin is a
            # full rebuild from SCD2 current state — cheap and convergent).
            await service.sync_role_permissions_to_casbin(db, rid, tenant.id)

        # --- menu perms: only ("menu", "devices") --------------------------
        for role_code, menu_codes in DEFAULT_MENU_PERMS.items():
            rid = role_ids.get(role_code)
            if rid is None:
                continue
            for code in menu_codes:
                if code != "devices":
                    continue  # scope guardrail — only the devices menu entry
                await service.add_policy(role_code, tenant.id, "menu", code)
                pid = await service._upsert_permission(
                    db, tenant.id, "menu", code, perm_type="menu"
                )
                if pid not in existing_per_role[role_code]:
                    await rp_repo.grant(rid, pid, tenant.id)
                    new_count += 1
            await service.sync_role_permissions_to_casbin(db, rid, tenant.id)

        await db.flush()
        stats[tenant.id] = new_count

    return stats
