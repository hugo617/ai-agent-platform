"""Repositories for Group + GroupTenant.

Group is a platform-level entity (no ``tenant_id``), so ``GroupRepository``
extends ``BaseRepository`` directly — NOT ``TenantScopedRepository``. Reads
filter ``is_deleted=False`` manually.

``GroupTenant`` is a join table: attaching/detaching a store is an
insert/delete (no soft-delete state — the relation exists or it doesn't).
"""

from sqlalchemy import delete, exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Base
from app.models.group import Group, GroupTenant
from app.models.tenant import Tenant
from app.repositories.base import BaseRepository


class GroupRepository(BaseRepository[Group]):
    """Platform-level CRUD over groups (cross-tenant, soft-deleted)."""

    model = Group

    def __init__(self, db: AsyncSession) -> None:
        # BaseRepository.__init__ only stores self.db; call it for consistency.
        super().__init__(db)

    async def get(self, group_id: str) -> Group | None:
        """Fetch a live (non-deleted) group by id."""
        stmt = select(Group).where(Group.id == group_id, Group.is_deleted.is_(False))
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_all(self) -> list[Group]:
        """All live groups (super_admin view), newest first."""
        stmt = (
            select(Group)
            .where(Group.is_deleted.is_(False))
            .order_by(Group.sort_order, Group.created_at.desc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def list_for_tenant(self, tenant_id: str) -> list[Group]:
        """Groups a tenant (store) belongs to — reverse lookup via GroupTenant."""
        stmt = (
            select(Group)
            .join(GroupTenant, GroupTenant.group_id == Group.id)
            .where(GroupTenant.tenant_id == tenant_id, Group.is_deleted.is_(False))
            .order_by(Group.sort_order, Group.created_at.desc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_by_code(self, code: str) -> Group | None:
        """Live group by code (uniqueness check on create/update)."""
        stmt = select(Group).where(Group.code == code, Group.is_deleted.is_(False))
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()


class GroupTenantRepository(BaseRepository[GroupTenant]):
    """Join-table ops: attach/detach a tenant (store) to/from a group."""

    model = GroupTenant

    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db)

    async def list_for_group(self, group_id: str) -> list[GroupTenant]:
        stmt = select(GroupTenant).where(GroupTenant.group_id == group_id)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def exists(self, group_id: str, tenant_id: str) -> bool:
        stmt = select(
            exists().where(
                GroupTenant.group_id == group_id, GroupTenant.tenant_id == tenant_id
            )
        )
        result = await self.db.execute(stmt)
        return bool(result.scalar())

    async def attach(self, group_id: str, tenant_id: str) -> GroupTenant:
        link = GroupTenant(group_id=group_id, tenant_id=tenant_id)
        self.db.add(link)
        await self.db.flush()
        return link

    async def detach(self, group_id: str, tenant_id: str) -> bool:
        """Delete the link row; return whether a row was actually removed."""
        stmt = delete(GroupTenant).where(
            GroupTenant.group_id == group_id, GroupTenant.tenant_id == tenant_id
        )
        result = await self.db.execute(stmt)
        return (result.rowcount or 0) > 0

    async def tenant_exists(self, tenant_id: str) -> bool:
        """Does the referenced tenant row exist? (attach validation)"""
        stmt = select(exists().where(Tenant.id == tenant_id))
        result = await self.db.execute(stmt)
        return bool(result.scalar())


# Re-export Base for type hints in callers that need it.
__all__ = ["Base", "GroupRepository", "GroupTenantRepository"]
