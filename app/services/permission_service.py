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
        """Return True if ``user_id`` may perform ``act`` on ``obj`` in ``tenant_id``.

        Platform super admins bypass all permission checks.
        """

        if platform_role == "super_admin":
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

    # TODO: reserved — expose via a future /roles/permissions or permissions
    # inspection page. Not currently called by any endpoint.
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
        self, db: AsyncSession, tenant_id: str
    ) -> list[PermissionItem]:
        """All permission catalogue items for a tenant.

        Source: the ``permissions`` rows upserted by ``seed_tenant_defaults`` /
        ``grant`` (one row per ``<obj>:<act>`` unit). Tenant scoping happens in
        the query (is_deleted=False), per the multi-tenant rule.
        """
        rows = (
            await db.execute(
                select(Permission).where(
                    Permission.tenant_id == tenant_id,
                    Permission.is_deleted.is_(False),
                )
            )
        ).scalars().all()
        items: list[PermissionItem] = []
        for p in rows:
            obj, act = p.code.split(":", 1) if ":" in p.code else (p.code, "")
            items.append(
                PermissionItem(id=p.id, code=p.code, name=p.name, obj=obj, act=act)
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
        self, db: AsyncSession, tenant_id: str, obj: str, act: str
    ) -> str:
        """Insert a catalogue Permission row for ``(obj, act)`` if absent.

        ``code == "<obj>:<act>"`` (e.g. ``"agents:delete"``) so each row is a
        single permission unit and role_permissions can point at exactly the
        pair that casbin reasons about. Idempotent across re-seeds.
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
        perm = Permission(
            name=f"{obj} {act}",
            code=code,
            tenant_id=tenant_id,
            type="api",
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
# ---------------------------------------------------------------------------
DEFAULT_OWNER_PERMS: list[tuple[str, str]] = [
    ("agents", "read"), ("agents", "create"), ("agents", "update"), ("agents", "delete"),
    ("conversations", "read"), ("conversations", "create"), ("conversations", "chat"),
    ("users", "read"), ("users", "create"), ("users", "update"), ("users", "delete"),
    ("roles", "read"), ("roles", "create"), ("roles", "update"), ("roles", "delete"),
    ("organizations", "read"), ("organizations", "create"),
    ("organizations", "update"), ("organizations", "delete"),
    ("settings", "manage"),
]
DEFAULT_ADMIN_PERMS: list[tuple[str, str]] = [
    ("agents", "read"), ("agents", "create"), ("agents", "update"),
    ("conversations", "read"), ("conversations", "create"), ("conversations", "chat"),
    ("users", "read"), ("users", "create"), ("users", "update"),
    ("roles", "read"), ("organizations", "read"),
    ("settings", "manage"),
]
DEFAULT_MEMBER_PERMS: list[tuple[str, str]] = [
    ("agents", "read"),
    ("conversations", "read"), ("conversations", "create"), ("conversations", "chat"),
    ("roles", "read"), ("organizations", "read"),
]


permission_service = PermissionService()
