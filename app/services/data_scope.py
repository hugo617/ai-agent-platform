"""Row-level data-scope resolution (权限重构系列 3/4).

A role carries a ``data_scope`` (all/tenant/group/self) that controls *which
data rows* a user holding that role can see. This service turns the current
request principal into a concrete :class:`ResolvedScope` that a Repository can
apply as a filter — it does **not** run the filter itself, keeping the
single-direction dependency (Service → Repository).

Resolution rules:

- ``super_admin`` / ``hq_staff`` bypass → ``all`` (no filter). This mirrors the
  bypass in ``permission_service.check`` and keeps platform viewers out of the
  tenant role system.
- Otherwise the user's tenant roles (casbin grouping policy → ``Role.code``) are
  looked up and the *widest* ``data_scope`` wins (all > group > tenant > self).
  So adding a narrower role never shrinks what a user could already see.
- ``group`` expands to the tenant_ids of every Group the caller's tenant belongs
  to; a tenant in no Group downgrades to ``tenant`` (sees only its own store).
- ``self`` resolves to ``created_by == user_id`` (the caller's own rows).

The Repository side (e.g. ``CustomerProfileRepository.list_for_scope``) consumes
the :class:`ResolvedScope` and builds the matching WHERE clause per domain.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.group import GroupRepository, GroupTenantRepository
from app.repositories.rbac import RoleRepository
from app.services.permission_service import (
    is_cross_tenant_viewer,
    permission_service,
)

# Wideness ordering for multi-role aggregation: the widest scope a user holds
# across all their roles wins (a self role must not shrink a tenant view).
_WIDTH: dict[str, int] = {"all": 4, "group": 3, "tenant": 2, "self": 1}
DEFAULT_SCOPE = "tenant"
_VALID_SCOPES = frozenset({"all", "tenant", "group", "self"})


@dataclass
class ResolvedScope:
    """The concrete data-scope result a Repository applies as a filter.

    - ``scope``: the effective level after aggregation/downgrade. A downstream
      downgrade of ``group`` → ``tenant`` is reflected here (NOT in the original
      role), so the Repository branches on the *effective* scope.
    - ``tenant_ids``: populated only for ``group`` (the sibling store ids).
    - ``owner_user_id``: populated only for ``self`` (the caller's user id).
    """

    scope: str
    tenant_ids: list[str] = field(default_factory=list)
    owner_user_id: str | None = None


class DataScopeService:
    """Resolve the current principal's effective row-level data scope."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def resolve(
        self,
        user_id: str,
        tenant_id: str,
        platform_role: str | None = None,
    ) -> ResolvedScope:
        # Platform viewers (super_admin / hq_staff) bypass the role system —
        # same gate as permission_service.check.
        if is_cross_tenant_viewer(platform_role):
            return ResolvedScope(scope="all")

        role_codes = await permission_service.get_roles_for_user_in_domain(
            user_id, tenant_id
        )
        scope = await self._widest_role_scope(tenant_id, role_codes)

        if scope == "group":
            tenant_ids = await self._resolve_group_tenants(tenant_id)
            if not tenant_ids:
                # Caller's tenant belongs to no Group → safe downgrade to tenant.
                return ResolvedScope(scope="tenant")
            return ResolvedScope(scope="group", tenant_ids=tenant_ids)

        if scope == "self":
            return ResolvedScope(scope="self", owner_user_id=user_id)

        # all / tenant → no extra payload; the Repository applies tenant filter
        # (tenant) or none (all) by its own convention.
        return ResolvedScope(scope=scope)

    async def _widest_role_scope(
        self, tenant_id: str, role_codes: list[str]
    ) -> str:
        """Pick the widest ``data_scope`` among the caller's tenant roles.

        Falls back to ``tenant`` when the user has no matching Role rows (e.g.
        the seeded UserTenant membership exists but the Role row was never
        created, as in the test harness) — ``tenant`` is the model default and
        the pre-feature behaviour, so it is the safe fallback.
        """
        if not role_codes:
            return DEFAULT_SCOPE
        roles = await RoleRepository(self.db).list_for_tenant(tenant_id)
        codes = set(role_codes)
        widest = 0
        for r in roles:
            if r.code not in codes:
                continue
            level = _WIDTH.get(r.data_scope)
            if level is not None and level > widest:
                widest = level
        if widest == 0:
            return DEFAULT_SCOPE
        # invert _WIDTH
        return next(s for s, w in _WIDTH.items() if w == widest)

    async def _resolve_group_tenants(self, tenant_id: str) -> list[str]:
        """All tenant_ids sharing any Group with ``tenant_id`` (incl. itself).

        A tenant may belong to several Groups; the union of their stores is the
        visible set. Returns an empty list when the tenant belongs to no Group
        (caller downgrades to ``tenant``).
        """
        groups = await GroupRepository(self.db).list_for_tenant(tenant_id)
        if not groups:
            return []
        gt_repo = GroupTenantRepository(self.db)
        tenant_ids: set[str] = {tenant_id}
        for g in groups:
            links = await gt_repo.list_for_group(g.id)
            tenant_ids.update(link.tenant_id for link in links)
        return sorted(tenant_ids)
