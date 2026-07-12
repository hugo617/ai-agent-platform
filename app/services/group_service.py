"""Group service — platform-level CRUD over cross-tenant business groups.

Permission model differs from tenant-scoped services:
- **Writes** (create/update/delete/attach/detach) are guarded at the API layer
  by ``require_super_admin()`` — only the platform super admin can reshape the
  org tree. The service does NOT re-check (avoids duplication).
- **Reads** (list/get) are open to any authenticated user. The service splits
  the view: super_admin sees every group; a tenant user sees only the groups
  their tenant belongs to (reverse lookup via GroupTenant).

``groups`` is intentionally absent from ``DEFAULT_*_PERMS`` — tenant roles have
no casbin grant for it, and reads don't consult casbin (they're gated by
authentication alone, then scoped by membership).
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.group import Group
from app.models.tenant import Tenant
from app.repositories.group import GroupRepository, GroupTenantRepository
from app.schemas.group import GroupCreate, GroupRead, GroupUpdate, TenantBrief
from app.services.errors import BizError, NotFoundError


class GroupService:
    OBJECT = "groups"

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = GroupRepository(db)
        self.links = GroupTenantRepository(db)

    # ------------------------------------------------------------- helpers

    async def _to_read(self, group: Group) -> GroupRead:
        """Build a GroupRead with tenant_ids + tenants expanded.

        Joins GroupTenant → Tenant to embed id+name for frontend rendering.
        Only iterates over the Group ORM columns (tenant_ids/tenants are
        service-populated, not ORM attributes).
        """
        links = await self.links.list_for_group(group.id)
        tenant_ids = [link.tenant_id for link in links]
        tenants: list[TenantBrief] = []
        if tenant_ids:
            rows = await self.db.execute(
                select(Tenant.id, Tenant.name).where(Tenant.id.in_(tenant_ids))
            )
            name_by_id = {tid: name for tid, name in rows.all()}
            tenants = [
                TenantBrief(id=tid, name=name_by_id.get(tid))
                for tid in tenant_ids
            ]
        data = {c.name: getattr(group, c.name) for c in group.__table__.columns}
        data["tenant_ids"] = tenant_ids
        data["tenants"] = tenants
        return GroupRead.model_validate(data)

    async def _get_live(self, group_id: str) -> Group:
        group = await self.repo.get(group_id)
        if group is None:
            raise NotFoundError(f"group {group_id} not found")
        return group

    async def _assert_code_unique(self, code: str | None, exclude_id: str | None) -> None:
        """Raise BizError if a *live* group already uses this code."""
        if not code:
            return
        existing = await self.repo.get_by_code(code)
        if existing is not None and existing.id != exclude_id:
            raise BizError(f"组织编码已存在: {code}")

    async def _validate_tenants_exist(self, tenant_ids: list[str]) -> None:
        """Raise NotFoundError if any referenced tenant does not exist."""
        if not tenant_ids:
            return
        rows = await self.db.execute(
            select(Tenant.id).where(Tenant.id.in_(tenant_ids))
        )
        found = {r for r in rows.scalars().all()}
        missing = [t for t in tenant_ids if t not in found]
        if missing:
            raise NotFoundError(f"门店不存在: {', '.join(missing)}")

    # ----------------------------------------------------------------- read

    async def list(
        self, tenant_id: str, platform_role: str | None = None
    ) -> list[GroupRead]:
        """super_admin → all groups; tenant user → only this tenant's groups."""
        if platform_role == "super_admin":
            groups = await self.repo.list_all()
        else:
            groups = await self.repo.list_for_tenant(tenant_id)
        return [await self._to_read(g) for g in groups]

    async def get(
        self, tenant_id: str, group_id: str, platform_role: str | None = None
    ) -> GroupRead:
        group = await self._get_live(group_id)
        # Tenant users (non-super_admin) can only read a group they belong to.
        if platform_role != "super_admin":
            belongs = await self.links.exists(group_id, tenant_id)
            if not belongs:
                raise NotFoundError(f"group {group_id} not found")
        return await self._to_read(group)

    # ---------------------------------------------------------------- write

    async def create(self, payload: GroupCreate) -> GroupRead:
        await self._assert_code_unique(payload.code, exclude_id=None)
        await self._validate_tenants_exist(payload.tenant_ids)
        group = Group(
            name=payload.name,
            code=payload.code,
            address=payload.address,
            description=payload.description,
            status=payload.status,
            sort_order=payload.sort_order,
        )
        await self.repo.add(group)
        for tid in payload.tenant_ids:
            await self.links.attach(group.id, tid)
        await self.db.commit()
        # Re-fetch so server defaults (created_at/updated_at) are loaded.
        fresh = await self.repo.get(group.id)
        assert fresh is not None  # just created, must exist
        return await self._to_read(fresh)

    async def update(self, group_id: str, payload: GroupUpdate) -> GroupRead:
        group = await self._get_live(group_id)
        data = payload.model_dump(exclude_unset=True)
        if "code" in data:
            await self._assert_code_unique(data["code"], exclude_id=group_id)
        for key, value in data.items():
            setattr(group, key, value)
        await self.db.flush()
        await self.db.commit()
        # Re-fetch: commit expires the ORM object, and reading its attributes
        # would otherwise trigger a lazy async load (MissingGreenlet).
        fresh = await self.repo.get(group_id)
        assert fresh is not None  # just updated, must exist
        return await self._to_read(fresh)

    async def delete(self, group_id: str) -> None:
        """Soft-delete a group. GroupTenant rows are left intact so a restored
        group keeps its memberships; they're filtered out via the group's
        is_deleted flag on read."""
        group = await self._get_live(group_id)
        group.is_deleted = True
        group.deleted_at = datetime.now(UTC)
        await self.db.flush()
        await self.db.commit()

    # --------------------------------------------------- tenant attach/detach

    async def attach_tenant(self, group_id: str, tenant_id: str) -> None:
        group = await self._get_live(group_id)
        if not await self.links.tenant_exists(tenant_id):
            raise NotFoundError(f"门店不存在: {tenant_id}")
        if await self.links.exists(group.id, tenant_id):
            raise BizError("门店已挂载到该组织")
        await self.links.attach(group.id, tenant_id)
        await self.db.commit()

    async def detach_tenant(self, group_id: str, tenant_id: str) -> None:
        # Validate the group exists (404 before "not attached" 404).
        await self._get_live(group_id)
        removed = await self.links.detach(group_id, tenant_id)
        if not removed:
            raise NotFoundError(f"门店 {tenant_id} 未挂载到组织 {group_id}")
        await self.db.commit()
