"""Permission service — the single wrapper around pycasbin.

This is where casbin's synchronous API is bridged into our async service layer
via ``run_in_threadpool``. Every permission check in the app goes through here,
keeping casbin usage in exactly one place (easy to test, easy to swap).
"""

from fastapi.concurrency import run_in_threadpool

from app.core import casbin_enforcer as _casbin_mod


class PermissionService:
    """Encapsulates all casbin operations for multi-tenant RBAC.

    Reads the enforcer + lock via the module (``_casbin_mod``) rather than a
    direct import so tests can monkeypatch ``app.core.casbin_enforcer.get_enforcer``
    and have the change take effect here.
    """

    # ---------- enforcement ----------
    async def check(self, user_id: str, tenant_id: str, obj: str, act: str) -> bool:
        """Return True if ``user_id`` may perform ``act`` on ``obj`` in ``tenant_id``."""

        def _do() -> bool:
            e = _casbin_mod.get_enforcer()
            with _casbin_mod.enforcer_lock():
                return bool(e.enforce(user_id, tenant_id, obj, act))

        return await run_in_threadpool(_do)

    def require(self, user_id: str, tenant_id: str, obj: str, act: str):
        """Convenience: raise ``PermissionError`` if not allowed.

        Kept as a coroutine so callers can ``await service.require(...)``.
        """

        async def _require():
            if not await self.check(user_id, tenant_id, obj, act):
                raise PermissionError(f"denied: {user_id} cannot {act} {obj} in {tenant_id}")

        return _require()

    # ---------- roles ----------
    async def add_role_for_user_in_domain(self, user_id: str, role: str, tenant_id: str) -> None:
        def _do() -> None:
            e = _casbin_mod.get_enforcer()
            with _casbin_mod.enforcer_lock():
                e.add_role_for_user_in_domain(user_id, role, tenant_id)

        await run_in_threadpool(_do)

    async def get_roles_for_user_in_domain(self, user_id: str, tenant_id: str) -> list[str]:
        def _do() -> list[str]:
            e = _casbin_mod.get_enforcer()
            with _casbin_mod.enforcer_lock():
                return list(e.get_roles_for_user_in_domain(user_id, tenant_id))

        return await run_in_threadpool(_do)

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

    async def seed_tenant_defaults(self, tenant_id: str, owner_user_id: str) -> None:
        """Bootstrap a brand-new tenant with the owner role + default policies.

        Default policy matrix (role -> object -> action):
            owner  -> agents      -> (read|create|update|delete)
            owner  -> conversations -> (read|create|chat)
            member -> agents      -> read
            member -> conversations -> (read|create|chat)
        """
        await self.add_role_for_user_in_domain(owner_user_id, "owner", tenant_id)

        owner_perms = [
            ("agents", "read"),
            ("agents", "create"),
            ("agents", "update"),
            ("agents", "delete"),
            ("conversations", "read"),
            ("conversations", "create"),
            ("conversations", "chat"),
        ]
        member_perms = [
            ("agents", "read"),
            ("conversations", "read"),
            ("conversations", "create"),
            ("conversations", "chat"),
        ]

        for obj, act in owner_perms:
            await self.add_policy("owner", tenant_id, obj, act)
        for obj, act in member_perms:
            await self.add_policy("member", tenant_id, obj, act)


permission_service = PermissionService()
