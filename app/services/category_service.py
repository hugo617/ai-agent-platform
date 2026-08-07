"""KnowledgeCategoryService — knowledge-tiered Feature B slice 01.

Category CRUD with scope↔role enforcement (plan G6): the role check is split
across two layers — ``require("knowledge", ...)`` handles the generic can-act
gate (owner/admin can write, member is read-only), and this service adds the
scope↔role binding on top:

  scope=platform → only super_admin
  scope=group    → only the group_admin of THAT group (HQ owner/admin)
  scope=store    → owner/admin of THAT store

Member fails at the ``require`` gate for any write act, so it never reaches the
scope check (the test ``test_service_member_cannot_create_any_scope`` pins this
without caring which layer raised).

The ``require`` calls pass ``db=self.db`` so the foundation's group_admin bypass
fires for knowledge reads/writes — a group_admin editing their group Category
would otherwise be blocked by casbin (no knowledge:create grant on the HQ
tenant). This mirrors the G1 fix the rest of Feature B applies to
KnowledgeService; this service is new so it opts in from day one.

Cross-field scope↔(group_id, tenant_id) binding is enforced HERE (not on the
schema) as a ``BizError`` → 400, because a pydantic ``model_validator`` raising
``ValueError`` breaks 422 JSON serialization — see ``BookingCreate`` docstring
and ``KnowledgeCategoryCreate`` docstring for the same hazard and convention.

The Repository layer is a pure data-access layer and must NOT import the
service layer (AGENTS.md 铁律 #1). ``is_cross_tenant_viewer`` lives in
``permission_service``, so this service computes it and hands the resulting
bool down to the repo as ``include_all_tenants``.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge_category import KnowledgeCategory
from app.repositories.group import GroupRepository
from app.repositories.knowledge_category import KnowledgeCategoryRepository
from app.schemas.document import (
    KnowledgeCategoryCreate,
    KnowledgeCategoryRead,
    KnowledgeCategoryUpdate,
)
from app.services.errors import BizError, NotFoundError
from app.services.permission_service import (
    is_cross_tenant_viewer,
    is_group_admin,
    permission_service,
)


def _to_read(cat: KnowledgeCategory) -> KnowledgeCategoryRead:
    return KnowledgeCategoryRead.model_validate(cat)


class KnowledgeCategoryService:
    """Tiered Category CRUD + three-tier visibility."""

    OBJECT = "knowledge"

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.cats = KnowledgeCategoryRepository(db)

    # ----------------------------------------------------------------- reads

    async def list(
        self,
        actor_id: str,
        tenant_id: str,
        platform_role: str | None = None,
    ) -> list[KnowledgeCategoryRead]:
        """List Categories visible to the caller (three-tier visibility).

        ``read`` is seeded for owner/admin/member, so every authenticated user
        passes the require gate. group_admin (derived) and super_admin get the
        wider views via the repo's role branches.
        """
        await permission_service.require(
            actor_id, tenant_id, self.OBJECT, "read",
            platform_role=platform_role, db=self.db,
        )
        group_id = await self._group_of(tenant_id)
        is_ga = (
            group_id is not None
            and await is_group_admin(self.db, actor_id, group_id)
        )
        # Computed here (not in the repo) so the repo never imports the service
        # layer (铁律 #1). The bool is the only role-context the repo needs.
        include_all = is_cross_tenant_viewer(platform_role)
        rows = await self.cats.list_visible(
            tenant_id=tenant_id,
            group_id=group_id,
            include_all_tenants=include_all,
            is_group_admin=is_ga,
        )
        return [_to_read(c) for c in rows]

    # ---------------------------------------------------------------- writes

    async def create(
        self,
        actor_id: str,
        tenant_id: str,
        payload: KnowledgeCategoryCreate,
        platform_role: str | None = None,
    ) -> KnowledgeCategoryRead:
        await permission_service.require(
            actor_id, tenant_id, self.OBJECT, "create",
            platform_role=platform_role, db=self.db,
        )
        self._check_scope_binding(payload.scope, payload.group_id, payload.tenant_id)
        await self._enforce_scope_role(
            actor_id, tenant_id, payload.scope,
            payload.group_id, payload.tenant_id, platform_role,
        )
        # Pre-check the partial unique index for a friendly BizError. The index
        # is the real guard; this is the UX layer.
        existing = await self.cats.find_active_in_scope(
            scope=payload.scope, name=payload.name,
            group_id=payload.group_id, tenant_id=payload.tenant_id,
        )
        if existing is not None:
            raise BizError(f"同级下已存在同名类目「{payload.name}」")

        cat = KnowledgeCategory(
            name=payload.name,
            scope=payload.scope,
            group_id=payload.group_id,
            tenant_id=payload.tenant_id,
            sort_order=payload.sort_order,
        )
        await self.cats.add(cat)
        await self.db.commit()
        await self.db.refresh(cat)
        return _to_read(cat)

    async def update(
        self,
        actor_id: str,
        tenant_id: str,
        category_id: str,
        payload: KnowledgeCategoryUpdate,
        platform_role: str | None = None,
    ) -> KnowledgeCategoryRead:
        # Reuse the "create" code as the write gate: plan G6 reuses existing
        # knowledge:read/create/delete codes (no new code), and "create" is the
        # write act owner/admin hold (member does not). There is no
        # knowledge:update code (documents have no edit path), so update and
        # delete both ride the create/delete write gates.
        await permission_service.require(
            actor_id, tenant_id, self.OBJECT, "create",
            platform_role=platform_role, db=self.db,
        )
        cat = await self._get_owned_or_403(
            actor_id, tenant_id, category_id, platform_role
        )
        # name change must not collide with another live row in the same scope.
        new_name = payload.name if payload.name is not None else cat.name
        if new_name != cat.name:
            clash = await self.cats.find_active_in_scope(
                scope=cat.scope, name=new_name,
                group_id=cat.group_id, tenant_id=cat.tenant_id,
            )
            if clash is not None and clash.id != cat.id:
                raise BizError(f"同级下已存在同名类目「{new_name}」")
            cat.name = new_name
        if payload.sort_order is not None:
            cat.sort_order = payload.sort_order
        await self.db.commit()
        await self.db.refresh(cat)
        return _to_read(cat)

    async def delete(
        self,
        actor_id: str,
        tenant_id: str,
        category_id: str,
        platform_role: str | None = None,
    ) -> None:
        await permission_service.require(
            actor_id, tenant_id, self.OBJECT, "delete",
            platform_role=platform_role, db=self.db,
        )
        cat = await self._get_owned_or_403(
            actor_id, tenant_id, category_id, platform_role
        )
        cat.is_deleted = True
        await self.db.commit()

    # ---------------------------------------------------- scope↔role helpers

    @staticmethod
    def _check_scope_binding(
        scope: str,
        group_id: str | None,
        tenant_id: str | None,
    ) -> None:
        """Cross-field binding: (scope, group_id, tenant_id) must be consistent.

        platform → both NULL  |  group → group_id set, tenant_id NULL
                   store  → tenant_id set, group_id NULL
        This can't live on the schema (see ``KnowledgeCategoryCreate`` docstring:
        a ``model_validator`` raising ``ValueError`` breaks JSON serialization
        of the 422 response), so it lives here as a ``BizError`` → 400, which
        serializes cleanly.
        """
        has_group = group_id is not None
        has_tenant = tenant_id is not None
        if scope == "platform":
            if has_group or has_tenant:
                raise BizError("scope=platform 不允许带 group_id 或 tenant_id")
        elif scope == "group":
            if not has_group:
                raise BizError("scope=group 必须带 group_id")
            if has_tenant:
                raise BizError("scope=group 不允许带 tenant_id")
        else:  # store
            if not has_tenant:
                raise BizError("scope=store 必须带 tenant_id")
            if has_group:
                raise BizError("scope=store 不允许带 group_id")

    async def _enforce_scope_role(
        self,
        actor_id: str,
        tenant_id: str,
        scope: str,
        group_id: str | None,
        cat_tenant_id: str | None,
        platform_role: str | None,
    ) -> None:
        """G6: who may create a Category of this scope.

        super_admin bypass in ``check`` already cleared the require, so we only
        re-check the scope binding for group/store. ``member`` never reaches
        here (create act failed at require).

        Note (AC6): a derived group_admin is NOT a super_admin, so creating
        scope=platform here raises — pinned by
        ``test_service_create_platform_category_by_group_admin_rejected``.
        """
        if platform_role == "super_admin":
            # super_admin may create any scope; no extra binding check.
            return
        if scope == "platform":
            # Only super_admin creates platform Categories. A group_admin is
            # NOT a super_admin, so it is refused here too.
            raise BizError("创建 scope=platform 类目需要超级管理员权限")
        if scope == "group":
            # Must be the group_admin of THAT group.
            if group_id is None or not await is_group_admin(self.db, actor_id, group_id):
                raise BizError("创建 scope=group 类目需要该集团的 group_admin 权限")
            return
        # scope == "store": must be owner/admin of THAT store.
        if cat_tenant_id is None:
            raise BizError("scope=store 类目缺少 tenant_id")
        if cat_tenant_id != tenant_id:
            # Writing into another store's Category is cross-tenant and refused.
            raise BizError("不能为其他门店创建类目")
        # The require gate already confirmed owner/admin on tenant_id (member
        # was rejected at create act). Nothing more to check.

    async def _get_owned_or_403(
        self,
        actor_id: str,
        tenant_id: str,
        category_id: str,
        platform_role: str | None,
    ) -> KnowledgeCategory:
        """Fetch a Category and confirm the caller may edit/delete it.

        super_admin/group_admin may edit their tier's Categories (group_admin
        only their own group); a store owner/admin may edit only their store's.
        Raises NotFoundError if the Category doesn't exist (so a cross-tier
        probe leaks no information).
        """
        cat = await self.cats.get(category_id)
        if cat is None:
            raise NotFoundError(f"类目 {category_id} 不存在")

        if platform_role == "super_admin":
            return cat
        if cat.scope == "group":
            if cat.group_id is None:
                raise NotFoundError(f"类目 {category_id} 不存在")
            if await is_group_admin(self.db, actor_id, cat.group_id):
                return cat
            raise NotFoundError(f"类目 {category_id} 不存在")
        if cat.scope == "store":
            if cat.tenant_id == tenant_id:
                return cat
            raise NotFoundError(f"类目 {category_id} 不存在")
        # scope == "platform": only super_admin (handled above) may edit.
        raise NotFoundError(f"类目 {category_id} 不存在")

    async def _group_of(self, tenant_id: str) -> str | None:
        """The group a tenant belongs to, if any (reverse lookup via GroupTenant)."""
        groups = await GroupRepository(self.db).list_for_tenant(tenant_id)
        return groups[0].id if groups else None
